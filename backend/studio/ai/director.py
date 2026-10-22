"""The model as editor: choose the shots, their order and the overlay texts.

The model only decides; the planner keeps timing, beats, length range and readability.
"""

import math
from typing import Any

from pydantic import BaseModel, ValidationError

from studio.ai.client import AiClient, AiError
from studio.ai.product import ProductCard
from studio.ai.shots import ShotLabel
from studio.options import RenderOptions
from studio.planning.baseline import STRATEGIES, Candidate, Script

STRATEGY_BRIEF = {
    "hook": "Short hook: open on the single most eye catching moment (a reveal or the "
    "product in use), then the best 3 to 5 features, quick and punchy.",
    "story": "Unboxing story: follow the real order, closed box, opening, first look, "
    "details, then using it. Calm, a bit longer, more texts.",
    "vibe": "Soft vibe: mood first, the creator using and enjoying the product, fewer "
    "and softer texts, an emotional hook.",
}

SYSTEM = """You are the editor of short, voiceless TikTok product videos for a creator
who receives product samples and films them in a soft, cozy lifestyle aesthetic.

Her proven style, learned from her best performing videos:
* A hook in the first second: "POV: ..." lines or a relatable sentence, about 6 to 12
  words, for example "POV: your office chair is officially your favorite seat in the
  house 🧸🤍" or "Unboxing my new oral care essentials 🤍".
* Then one feature per shot, and the shot must show that feature while its text is on
  screen ("foldable armrests 👀" while a hand folds the armrest).
* Short casual English overlays, at most about 40 characters, sentence case, no
  hashtags, no prices, no exaggerated claims.
* Soft emojis such as 🤍 ✨ 🧸 👀 🥹 💛 🖤, at most one per text and on about every
  second text, matching the product's colour.
* Hard cuts of about two seconds; shorter videos with fewer, stronger texts perform
  far better than long spec lists.

You get the product card, the creator's idea (follow it when it is reasonable), and a
catalog of usable shots with what a vision model saw in each. For every requested
variant return:
* strategy: as requested.
* hook: the opening overlay.
* caption: one cozy sentence for the post caption (no hashtags).
* shots: the shots in playback order, each with an overlay text or null. The first
  shot carries the hook, so give it null. Put a feature text only on a shot whose
  content shows it; leave roughly every second shot without text so the video
  breathes. The last shot gets null, the app adds "Link below the video ✨" there.
  Never use a shot twice in one variant, avoid shots with problems, and avoid two
  shots from the same clip in a row unless the story needs it.

Use only shot ids from the catalog. Return about the requested number of shots."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "strategy": {"type": "string", "enum": [s.key for s in STRATEGIES]},
                    "hook": {"type": "string"},
                    "caption": {"type": "string"},
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": ["string", "null"]},
                            },
                            "required": ["id", "text"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["strategy", "hook", "caption", "shots"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["variants"],
    "additionalProperties": False,
}


class _Shot(BaseModel):
    id: str
    text: str | None = None


class _Variant(BaseModel):
    strategy: str
    hook: str
    caption: str = ""
    shots: list[_Shot]


def catalog(cands: list[Candidate], labels: dict[str, ShotLabel]) -> str:
    lines = []
    for c in sorted(cands, key=lambda c: (c.clip_index, c.start)):
        label = labels.get(c.id)
        parts = [
            c.id,
            f"clip {c.clip_index + 1}",
            f"{c.end - c.start:.1f}s",
            f"quality {c.score:.2f}",
        ]
        if c.face_ratio > 0.3:
            parts.append("face visible")
        if label:
            parts += [label.shot_type, f"appeal {label.appeal}/10", f'"{label.description}"']
            if label.feature:
                parts.append(f"shows: {label.feature}")
            if label.problem:
                parts.append(f"problem: {label.problem}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def write_scripts(
    client: AiClient,
    card: ProductCard,
    prompt: str,
    cands: list[Candidate],
    labels: dict[str, ShotLabel],
    options: RenderOptions,
) -> dict[str, Script]:
    strategies = STRATEGIES[: options.variants]
    requests = []
    for s in strategies:
        target = options.min_duration + (options.max_duration - options.min_duration) * s.position
        count = max(3, math.ceil(target / s.shot))
        requests.append(
            f"* {s.key}: about {target:.0f}s, about {count} shots. {STRATEGY_BRIEF[s.key]}"
        )

    emoji_rule = "" if options.emoji else "\nDo not use any emoji in hooks or texts."
    text_rule = "" if options.texts else "\nThe video has no overlays; still return a hook."
    features = "\n".join(f"* {f}" for f in card.features) or "(none)"
    user = (
        f"Product: {card.name} ({card.category})\nAudience: {card.audience}\n"
        f"Features:\n{features}\nSuggested emojis: {' '.join(card.emojis)}\n\n"
        f"Creator's idea: {card.idea or prompt or '(none)'}\n"
        + (f"Original idea text: {prompt}\n" if prompt and prompt != card.idea else "")
        + "\nVariants to write:\n"
        + "\n".join(requests)
        + emoji_rule
        + text_rule
        + f"\n\nShot catalog (id | clip | length | ...):\n{catalog(cands, labels)}"
    )

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            data = client.json(system=SYSTEM, parts=[user], schema=SCHEMA, max_tokens=8000)
            return _scripts(data, cands)
        except (AiError, ValidationError) as exc:
            last_error = exc
    raise AiError(f"the edit plan from the model was unusable: {last_error}")


def _scripts(data: dict[str, Any], cands: list[Candidate]) -> dict[str, Script]:
    known = {c.id for c in cands}
    scripts: dict[str, Script] = {}
    for raw in data.get("variants", []):
        variant = _Variant.model_validate(raw)
        seen: set[str] = set()
        shots = []
        for shot in variant.shots:
            if shot.id in known and shot.id not in seen:
                seen.add(shot.id)
                text = (shot.text or "").strip() or None
                shots.append((shot.id, text))
        if len(shots) >= 2 and variant.strategy not in scripts:
            scripts[variant.strategy] = Script(
                hook=variant.hook.strip(), shots=shots, caption=variant.caption.strip()
            )
    if not scripts:
        raise AiError("the model returned no usable variant")
    return scripts
