"""Rule based planner that works without any AI model.

It follows the creator's reference style (hook, feature walk, call to action, about two
seconds per shot, hard cuts on the beat) using the footage analysis, the music beats and
the product text. It cannot see what a shot shows, so texts are not matched to the
content of each shot, and it cannot translate Persian. A language model planner replaces
it once a model is configured.
"""

import bisect
import math
import re
from dataclasses import dataclass, field

from studio.analysis.beats import BeatInfo
from studio.options import RenderOptions
from studio.planning.schema import EditPlan, PlanMusic, PlanSegment, PlanText
from studio.render.text import strip_emoji

PERSIAN = re.compile(r"[؀-ۿ]")
EMOJIS = ["✨", "🤍", "👀", "🥹"]
CTA = "Link below the video ✨"
MIN_SHOT = 1.2
TEXT_Y = 0.58
TEXT_Y_ALTERNATIVES = (0.72, 0.36)


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    position: float  # where in the min..max range the length should land
    shot: float
    style: str
    order: str


STRATEGIES = [
    Strategy("hook", "Short hook", 0.15, 2.0, "sans", "score"),
    Strategy("story", "Unboxing story", 0.85, 2.4, "sans", "chronological"),
    Strategy("vibe", "Soft vibe", 0.5, 1.8, "serif", "people"),
]


@dataclass
class ProductInfo:
    title: str
    text: str
    url: str
    prompt: str


@dataclass
class MusicChoice:
    music: PlanMusic
    beats: BeatInfo | None = None


@dataclass
class Candidate:
    clip_id: str
    clip_index: int
    start: float
    end: float
    score: float
    face_ratio: float
    subject_x: float
    source_ratio: float  # width / height of the source clip
    brightness: float = 125.0
    face_y: float | None = None

    @property
    def key(self) -> tuple[str, float]:
        return (self.clip_id, self.start)


@dataclass
class Shot:
    cand: Candidate
    start: float
    end: float
    at: float = 0.0  # position in the final video

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass
class Draft:
    shots: list[Shot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(s.length for s in self.shots)


def candidates_from(analysis: dict) -> list[Candidate]:
    out = []
    for index, clip in enumerate(analysis["clips"]):
        ratio = clip.get("source_width", 9) / max(clip.get("source_height", 16), 1)
        for seg in clip["segments"]:
            out.append(Candidate(
                clip["clip_id"], index, seg["start"], seg["end"], seg["score"],
                seg["face_ratio"], seg["subject_x"], ratio,
                seg.get("brightness", 125.0), seg.get("face_y"),
            ))  # fmt: skip
    return out


# Product text ---------------------------------------------------------------------


def product_features(info: ProductInfo) -> tuple[str, list[str], list[str]]:
    """Return product name, short feature lines and notes for the user."""
    notes: list[str] = []
    raw = info.text
    if PERSIAN.search(raw) or PERSIAN.search(info.title):
        notes.append(
            "Persian product text needs a language model to become English overlays; "
            "only generic texts were used."
        )
        raw = PERSIAN.sub(" ", raw)
    # Lines and sentences first; commas only split lines that are too long for one overlay.
    parts = []
    for line in re.split(r"[\n;•]|\.(?=\s|$)", raw):
        parts.extend(re.split(r",(?!\d)", line) if len(line.strip()) > 48 else [line])
    features: list[str] = []
    for part in parts:
        clean = re.sub(r"\s+", " ", part).strip(" -–:+")
        if 3 <= len(clean) <= 48 and re.search(r"[A-Za-z0-9]", clean):
            features.append(clean[0].upper() + clean[1:])
    name = info.title.strip() if info.title and not PERSIAN.search(info.title) else ""
    if not name and features:
        name = features.pop(0)
    features = [f for f in features if f.lower() != name.lower()]
    if info.prompt:
        notes.append(
            "Your idea prompt is used by the language model planner, "
            "the rule based planner ignores it."
        )
    return name or "new favorite", features, notes


def hook_line(strategy: Strategy, name: str) -> str:
    lower = name[0].lower() + name[1:] if name else name
    return {
        "hook": f"POV: you found your new favorite {lower} 🤍",
        "story": f"Unboxing my new {lower} ✨",
        "vibe": f"The {lower} I didn't know I needed 🥹",
    }[strategy.key]


def readable(text: str) -> float:
    """Seconds a viewer needs to read an overlay."""
    return 0.9 + len(text) / 15.0


# Shot selection -------------------------------------------------------------------


def ordered_pool(cands: list[Candidate], strategy: Strategy) -> list[Candidate]:
    if strategy.order == "chronological":
        return sorted(cands, key=lambda c: (c.clip_index, c.start))
    if strategy.order == "people":
        return sorted(cands, key=lambda c: (c.face_ratio > 0.3, c.score), reverse=True)
    return sorted(cands, key=lambda c: c.score, reverse=True)


def choose(pool: list[Candidate], needed: int, clip_count: int) -> list[Candidate]:
    """Pick candidates with variety: no clip dominates unless the footage is short."""
    per_clip = max(2, math.ceil(needed / max(clip_count, 1)) + 1)
    picked: list[Candidate] = []
    used: dict[str, int] = {}
    for strict in (True, False):
        for c in pool:
            if len(picked) >= needed:
                break
            if c in picked or (strict and used.get(c.clip_id, 0) >= per_clip):
                continue
            picked.append(c)
            used[c.clip_id] = used.get(c.clip_id, 0) + 1
    return picked


def arrange(picked: list[Candidate], strategy: Strategy) -> list[Candidate]:
    if strategy.order == "chronological":
        return sorted(picked, key=lambda c: (c.clip_index, c.start))
    if strategy.order == "people":
        return _avoid_repeats(sorted(picked, key=lambda c: c.score, reverse=True))
    return [picked[0], *_avoid_repeats(picked[1:])] if picked else picked


def _avoid_repeats(items: list[Candidate]) -> list[Candidate]:
    """Reorder so the same clip does not appear twice in a row when avoidable."""
    result: list[Candidate] = []
    rest = list(items)
    while rest:
        prev = result[-1].clip_id if result else None
        nxt = next((c for c in rest if c.clip_id != prev), rest[0])
        rest.remove(nxt)
        result.append(nxt)
    return result


def _nearest_beat(beats: list[float], target: float, lo: float, hi: float) -> float | None:
    """Beat closest to target inside [lo, hi]."""
    i = bisect.bisect_left(beats, lo - 1e-6)
    best = None
    while i < len(beats) and beats[i] <= hi + 1e-6:
        if best is None or abs(beats[i] - target) < abs(best - target):
            best = beats[i]
        i += 1
    return best


def build_timeline(
    order: list[Candidate],
    strategy: Strategy,
    target: float,
    maximum: float,
    beats: list[float] | None,
    min_shot: float = MIN_SHOT,
) -> Draft:
    """Lay shots end to end; every cut lands on a beat when beats are given."""
    draft = Draft()
    t = 0.0
    for i, cand in enumerate(order):
        remaining = target - t
        if remaining < min_shot * 0.8 and draft.shots:
            break
        desired = strategy.shot + (0.6 if i == 0 else 0.0)
        avail = cand.end - cand.start
        if avail < min_shot:
            continue
        longest = min(avail, maximum - t)
        if longest < min_shot:
            break
        desired = min(desired, longest)
        # Do not leave a sliver at the end: stretch into the remaining time.
        if 0 < remaining - desired < min_shot:
            desired = min(remaining, longest)
        length = desired
        if beats:
            beat = _nearest_beat(beats, t + desired, t + min_shot, t + longest)
            if beat is not None:
                length = beat - t
        # Centre the shot inside the analysed window, where the scores were measured.
        start = cand.start + max(0.0, (avail - length) / 2) * 0.5
        draft.shots.append(Shot(cand, round(start, 3), round(start + length, 3), round(t, 3)))
        t += length
    return draft


def stretch_to_minimum(draft: Draft, minimum: float) -> None:
    """Lengthen shots inside their analysed windows until the minimum is reached."""
    missing = minimum - draft.total
    for shot in sorted(draft.shots, key=lambda s: s.cand.score, reverse=True):
        if missing <= 0.01:
            break
        room = shot.cand.end - shot.end
        grow = min(room, missing)
        if grow > 0:
            shot.end = round(shot.end + grow, 3)
            missing -= grow
    t = 0.0
    for shot in draft.shots:
        shot.at = round(t, 3)
        t += shot.length


# Text placement and exposure -------------------------------------------------------


def text_y(shots: list[Shot], start: float, end: float) -> float:
    """Keep text off faces: pick the first position far enough from every face."""
    faces = [
        s.cand.face_y
        for s in shots
        if s.cand.face_y is not None and s.at < end and s.at + s.length > start
    ]
    for y in (TEXT_Y, *TEXT_Y_ALTERNATIVES):
        if all(abs(y - f) >= 0.17 for f in faces):
            return y
    return TEXT_Y_ALTERNATIVES[0]


def exposure_gammas(shots: list[Shot]) -> list[float]:
    """Gentle gamma per shot so bright and dark clips look like one video."""
    values = [min(max(s.cand.brightness, 20.0), 235.0) for s in shots]
    target = min(max(sorted(values)[len(values) // 2], 110.0), 145.0)
    gammas = []
    for v in values:
        g = math.log(v / 255.0) / math.log(target / 255.0)
        g = 1.0 + (g - 1.0) * 0.6
        gammas.append(round(min(max(g, 0.8), 1.3), 3))
    return gammas


# Plan ------------------------------------------------------------------------------


def build_plan(
    strategy: Strategy,
    cands: list[Candidate],
    clip_count: int,
    info: ProductInfo,
    options: RenderOptions,
    music: MusicChoice | None,
) -> EditPlan:
    name, features, notes = product_features(info)
    minimum, maximum = options.min_duration, options.max_duration
    target = minimum + (maximum - minimum) * strategy.position

    beats: list[float] | None = None
    plan_music: PlanMusic | None = None
    if music is not None:
        start = 0.0
        if music.beats and music.beats.beats:
            # Start the music on a downbeat once the intro is over.
            downbeats = music.beats.downbeats or music.beats.beats
            start = next((b for b in downbeats if b >= music.beats.intro_end - 0.05), downbeats[0])
            if options.beat_sync:
                beats = [round(b - start, 3) for b in music.beats.beats if b > start + 0.3]
        plan_music = music.music.model_copy(update={"start": round(start, 3)})

    pool = ordered_pool(cands, strategy)
    needed = max(2, math.ceil(maximum / MIN_SHOT))
    order = arrange(choose(pool, needed, clip_count), strategy)
    draft = build_timeline(order, strategy, target, maximum, beats)
    if not draft.shots:
        # Only very short clips: accept shorter shots rather than failing.
        draft = build_timeline(order, strategy, target, maximum, beats, min_shot=0.5)
    if not draft.shots:
        raise ValueError("the footage is too short to edit (every usable moment is under 0.5s)")
    if draft.total < minimum:
        stretch_to_minimum(draft, minimum)
        if draft.total < minimum - 0.05:
            draft.notes.append(
                f"Not enough usable footage for the minimum length: "
                f"{draft.total:.1f}s instead of {minimum:.0f}s."
            )
    notes.extend(draft.notes)

    gammas = exposure_gammas(draft.shots)
    segments = []
    for shot, gamma in zip(draft.shots, gammas, strict=True):
        crop = shot.cand.subject_x if shot.cand.source_ratio > 0.6 else 0.5
        segments.append(PlanSegment(
            clip_id=shot.cand.clip_id, start=shot.start, end=shot.end,
            crop_x=round(min(max(crop, 0.0), 1.0), 3), gamma=gamma,
        ))  # fmt: skip

    total = draft.total
    style = strategy.style if options.text_style == "auto" else options.text_style
    texts = (
        overlay_texts(strategy, draft.shots, total, name, features, options, style)
        if options.texts
        else []
    )
    if options.texts and not features:
        notes.append(
            "No English feature list found in the product text, so only the hook "
            "and the call to action are shown."
        )

    hook = hook_line(strategy, name)
    tag = re.sub(r"[^a-z0-9]", "", name.lower())[:30]
    hashtags = [f"#{tag}"] if tag and tag != "newfavorite" else []
    hashtags += [h for h in options.hashtags if h.lower() != f"#{tag}"]
    caption_lines = [hook]
    if options.call_to_action:
        caption_lines.append(CTA)
    if hashtags:
        caption_lines.append(" ".join(hashtags))
    caption = "\n".join(caption_lines)
    if options.disclosure.strip():
        caption += f"\n\n{options.disclosure.strip()}"

    return EditPlan(
        strategy=strategy.key, label=strategy.label, style=style,  # type: ignore[arg-type]
        segments=segments, texts=texts, music=plan_music, caption=caption, notes=notes,
    )  # fmt: skip


def overlay_texts(
    strategy: Strategy,
    shots: list[Shot],
    total: float,
    name: str,
    features: list[str],
    options: RenderOptions,
    style: str,
) -> list[PlanText]:
    def clean(text: str) -> str:
        return text if options.emoji else strip_emoji(text)

    bounds = [(s.at, s.at + s.length) for s in shots]
    texts: list[PlanText] = []

    hook = clean(hook_line(strategy, name))
    hook_end = min(max(readable(hook), bounds[0][1]), total)
    texts.append(PlanText(
        text=hook, start=0.15, end=round(hook_end, 2),
        y=text_y(shots, 0.15, hook_end),
        animation="typewriter" if style == "serif" else "fade",
    ))  # fmt: skip

    has_cta = options.call_to_action and len(bounds) > 1
    cta_start = bounds[-1][0] if has_cta else total
    cursor = texts[0].end + 0.15
    emoji_index = 0
    feature_iter = iter(features)
    for start, end in bounds[1:-1] if has_cta else bounds[1:]:
        if start < cursor - 0.05:
            continue
        feature = next(feature_iter, None)
        if feature is None:
            break
        if emoji_index % 2 == 0:
            feature = f"{feature} {EMOJIS[emoji_index // 2 % len(EMOJIS)]}"
        emoji_index += 1
        feature = clean(feature)
        text_end = min(max(end - 0.05, start + readable(feature)), cta_start - 0.1)
        if text_end - start < 1.0:
            break
        texts.append(PlanText(
            text=feature, start=round(start + 0.1, 2), end=round(text_end, 2),
            y=text_y(shots, start, text_end),
        ))  # fmt: skip
        cursor = text_end + 0.15
    if has_cta:
        cta = clean(CTA)
        texts.append(PlanText(
            text=cta, start=round(cta_start + 0.1, 2), end=round(total, 2),
            y=text_y(shots, cta_start, total),
        ))  # fmt: skip
    return texts


def plan_variants(
    analysis: dict, info: ProductInfo, options: RenderOptions, music: list[MusicChoice]
) -> list[EditPlan]:
    cands = candidates_from(analysis)
    if not cands:
        raise ValueError("no usable segments")
    clip_count = len(analysis["clips"])
    plans = []
    for i, strategy in enumerate(STRATEGIES[: options.variants]):
        choice = music[i % len(music)] if music else None
        plans.append(build_plan(strategy, cands, clip_count, info, options, choice))
    return plans
