from pathlib import Path

from PIL import Image

from studio.render.text import render_text, split_runs


def test_split_runs_keeps_emoji_sequences() -> None:
    assert split_runs("So cozy 🤍✨") == [("So cozy ", False), ("🤍", True), ("✨", True)]
    assert split_runs("hi 👍🏽 there") == [("hi ", False), ("👍🏽", True), (" there", False)]


def test_render_text_draws_centered_overlay(tmp_path: Path) -> None:
    out = render_text(
        "POV: your new favorite chair 🧸🤍", "sans", (540, 960), 0.5, tmp_path / "t.png"
    )
    img = Image.open(out)
    assert img.size == (540, 960)
    box = img.getbbox()
    assert box is not None
    left, top, right, bottom = box
    assert abs((left + right) / 2 - 270) < 30
    assert top > 300 and bottom < 660
