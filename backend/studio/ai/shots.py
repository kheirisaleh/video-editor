"""Shot understanding: a vision model looks at frames of every candidate segment.

The labels tell the planner what each moment shows (box, unboxing, a feature being
demonstrated, the product in use), so overlay texts can match the picture and the
most appealing moment can open the video.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from studio.ai.client import AiClient, AiError, Image
from studio.ai.product import ProductCard

ShotType = Literal[
    "box",
    "unboxing",
    "product_reveal",
    "product_closeup",
    "detail",
    "hands_demo",
    "in_use",
    "person",
    "lifestyle",
    "other",
]


class ShotLabel(BaseModel):
    id: str
    description: str
    shot_type: ShotType = "other"
    feature: str | None = Field(default=None, description="product feature shown, verbatim")
    appeal: int = Field(default=5, ge=0, le=10)
    problem: str | None = None


LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "shot_type": {"type": "string", "enum": list(ShotType.__args__)},
                    "feature": {"type": ["string", "null"]},
                    "appeal": {"type": "integer"},
                    "problem": {"type": ["string", "null"]},
                },
                "required": ["id", "description", "shot_type", "feature", "appeal", "problem"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["shots"],
    "additionalProperties": False,
}

LABEL_SYSTEM = """You review raw phone footage for a short TikTok product video.

Each shot is shown as a few frames in time order. For every shot return:
* id: exactly as given.
* description: what happens, one short English sentence.
* shot_type: box (closed packaging), unboxing (opening, taking out), product_reveal
  (first full look), product_closeup, detail (a specific part), hands_demo (hands show
  how something works), in_use (the product being used), person (the creator, little
  product), lifestyle (room or mood), other.
* feature: if the shot clearly demonstrates one of the listed product features, copy
  that feature text exactly; otherwise null. Only match what is actually visible.
* appeal: 0 to 10, how well the shot would stop a viewer scrolling. Sharp, well lit,
  clear subject and a satisfying moment score high; blur, shake, clutter or nothing
  happening score low.
* problem: a real visual problem (blurry, dark, shaky, finger over lens, product cut
  off) or null."""


def extract_frames(
    proxy: Path, start: float, end: float, count: int = 3, width: int = 384
) -> list[Image]:
    frames = []
    length = max(end - start, 0.1)
    for k in range(count):
        t = start + length * (k + 0.5) / count
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(proxy), "-frames:v", "1",
             "-vf", f"scale={width}:-2", "-q:v", "4", "-f", "image2", "-c:v", "mjpeg", "-"],
            capture_output=True,
        )  # fmt: skip
        if out.returncode == 0 and out.stdout:
            frames.append(Image(out.stdout))
    return frames


def label_shots(
    client: AiClient,
    shots: list[dict[str, Any]],
    card: ProductCard,
    batch: int,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, ShotLabel]:
    """shots: dicts with id, proxy (Path), start, end. Returns labels by id."""
    labels: dict[str, ShotLabel] = {}
    features = "\n".join(f"* {f}" for f in card.features) or "(no feature list)"
    for i in range(0, len(shots), batch):
        if should_cancel and should_cancel():
            break
        group = shots[i : i + batch]
        parts: list[Any] = [
            f"Product: {card.name}\nFeatures:\n{features}\n\nThere are {len(group)} shots."
        ]
        for shot in group:
            frames = extract_frames(shot["proxy"], shot["start"], shot["end"])
            if not frames:
                continue
            parts.append(f"Shot {shot['id']} ({shot['end'] - shot['start']:.1f}s):")
            parts.extend(frames)
        data = client.json(
            system=LABEL_SYSTEM, parts=parts, schema=LABEL_SCHEMA, vision=True, max_tokens=6000
        )
        try:
            for item in data.get("shots", []):
                label = ShotLabel.model_validate(item)
                if label.feature and label.feature not in card.features:
                    label.feature = None
                label.appeal = max(0, min(label.appeal, 10))
                labels[label.id] = label
        except ValidationError as exc:
            raise AiError(f"the shot labels from the model were invalid: {exc}") from exc
        if on_progress:
            on_progress(min(i + batch, len(shots)) / len(shots))
    return labels
