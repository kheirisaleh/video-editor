"""Rule based planner that works without any AI model.

It follows the creator's reference style (hook, feature walk, call to action, about two
seconds per shot) using only the footage analysis and the product text. It cannot see
what a shot shows, so texts are not matched to the content of each shot, and it cannot
translate Persian. A language model planner replaces it once a model is configured.
"""

import math
import re
from dataclasses import dataclass

from studio.planning.schema import EditPlan, PlanMusic, PlanSegment, PlanText

PERSIAN = re.compile(r"[؀-ۿ]")
EMOJIS = ["✨", "🤍", "👀", "🥹"]
CTA = "Link below the video ✨"
DISCLOSURE = "Pr sample, no payment received."


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    target: float
    shot: float
    max_texts: int
    style: str
    order: str


STRATEGIES = [
    Strategy("hook", "Short hook", 15.0, 2.0, 6, "sans", "score"),
    Strategy("story", "Unboxing story", 24.0, 2.4, 9, "sans", "chronological"),
    Strategy("vibe", "Soft vibe", 18.0, 1.8, 7, "serif", "people"),
]


@dataclass
class ProductInfo:
    title: str
    text: str
    url: str
    prompt: str


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


def candidates_from(analysis: dict) -> list[Candidate]:
    out = []
    for index, clip in enumerate(analysis["clips"]):
        ratio = clip.get("source_width", 9) / max(clip.get("source_height", 16), 1)
        for seg in clip["segments"]:
            out.append(
                Candidate(
                    clip["clip_id"],
                    index,
                    seg["start"],
                    seg["end"],
                    seg["score"],
                    seg["face_ratio"],
                    seg["subject_x"],
                    ratio,
                )
            )
    return out


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


def select_segments(cands: list[Candidate], strategy: Strategy, clip_count: int) -> list[Candidate]:
    if strategy.order == "chronological":
        pool = sorted(cands, key=lambda c: (c.clip_index, c.start))
    elif strategy.order == "people":
        pool = sorted(cands, key=lambda c: (c.face_ratio > 0.3, c.score), reverse=True)
    else:
        pool = sorted(cands, key=lambda c: c.score, reverse=True)

    needed = max(1, math.ceil(strategy.target / strategy.shot))
    per_clip = max(2, math.ceil(needed / max(clip_count, 1)) + 1)
    picked: list[Candidate] = []
    used: dict[str, int] = {}
    # Two passes: first respect variety, then fill up if the footage is short.
    for strict in (True, False):
        for c in pool:
            if len(picked) >= needed:
                break
            if c in picked:
                continue
            if strict and used.get(c.clip_id, 0) >= per_clip:
                continue
            picked.append(c)
            used[c.clip_id] = used.get(c.clip_id, 0) + 1

    if strategy.order == "chronological":
        picked.sort(key=lambda c: (c.clip_index, c.start))
    elif strategy.order == "people":
        picked = _avoid_repeats(sorted(picked, key=lambda c: c.score, reverse=True))
    else:
        picked = [picked[0], *_avoid_repeats(picked[1:])] if picked else picked
    return picked


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


def readable(text: str) -> float:
    return 0.9 + len(text) / 15.0


def build_plan(
    strategy: Strategy,
    cands: list[Candidate],
    clip_count: int,
    info: ProductInfo,
    music: PlanMusic | None,
) -> EditPlan:
    name, features, notes = product_features(info)
    chosen = select_segments(cands, strategy, clip_count)

    segments: list[PlanSegment] = []
    for i, c in enumerate(chosen):
        length = strategy.shot + (0.8 if i == 0 else 0.0)
        end = min(c.end, c.start + length)
        crop = c.subject_x if c.source_ratio > 0.6 else 0.5
        segments.append(
            PlanSegment(
                clip_id=c.clip_id,
                start=c.start,
                end=round(end, 3),
                crop_x=round(min(max(crop, 0.0), 1.0), 3),
            )
        )

    bounds = []
    t = 0.0
    for seg in segments:
        bounds.append((t, t + seg.duration))
        t += seg.duration
    total = t

    texts: list[PlanText] = []
    hook = hook_line(strategy, name)
    hook_end = max(readable(hook), bounds[0][1])
    texts.append(
        PlanText(
            text=hook,
            start=0.2,
            end=round(min(hook_end, total), 2),
            animation="typewriter" if strategy.style == "serif" else "fade",
        )
    )

    cta_start = bounds[-1][0] if len(bounds) > 1 else max(total - 2.0, 0.0)
    cursor = texts[0].end + 0.15
    feature_iter = iter(features[: max(strategy.max_texts - 2, 0)])
    emoji_index = 0
    for start, end in bounds[1:-1]:
        if start < cursor - 0.05:
            continue
        feature = next(feature_iter, None)
        if feature is None:
            break
        if emoji_index % 2 == 0:
            feature = f"{feature} {EMOJIS[emoji_index // 2 % len(EMOJIS)]}"
        emoji_index += 1
        text_end = min(max(end - 0.05, start + readable(feature)), cta_start - 0.1)
        if text_end - start < 1.0:
            break
        texts.append(PlanText(text=feature, start=round(start + 0.1, 2), end=round(text_end, 2)))
        cursor = text_end + 0.15
    texts.append(PlanText(text=CTA, start=round(cta_start + 0.1, 2), end=round(total, 2)))

    tag = re.sub(r"[^a-z0-9]", "", name.lower())[:30]
    hashtags = ["#tiktokmademebuyit", "#tiktokshopmademebuyit"]
    if tag:
        hashtags.insert(0, f"#{tag}")
    caption = f"{hook}\n{CTA}\n{' '.join(hashtags)}\n\n{DISCLOSURE}"

    if not features:
        notes.append(
            "No English feature list found in the product text, so only the hook "
            "and the call to action are shown."
        )
    return EditPlan(
        strategy=strategy.key,
        label=strategy.label,
        style=strategy.style,  # type: ignore[arg-type]
        segments=segments,
        texts=texts,
        music=music,
        caption=caption,
        notes=notes,
    )


def plan_variants(
    analysis: dict, info: ProductInfo, music_tracks: list[PlanMusic], count: int = 3
) -> list[EditPlan]:
    cands = candidates_from(analysis)
    if not cands:
        raise ValueError("no usable segments")
    clip_count = len(analysis["clips"])
    plans = []
    for i, strategy in enumerate(STRATEGIES[:count]):
        music = music_tracks[i % len(music_tracks)] if music_tracks else None
        plans.append(build_plan(strategy, cands, clip_count, info, music))
    return plans
