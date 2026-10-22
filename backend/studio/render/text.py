"""Text overlays in the creator's style: white text, soft shadow, colour emoji.

FFmpeg's own text renderers cannot draw colour emoji, so overlays are drawn with Pillow
into transparent PNGs and composited by FFmpeg.
"""

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
EMOJI_BITMAP_SIZE = 109

STYLES = {
    "sans": {"file": "Inter.ttf", "weight": 500, "size": 52},
    "serif": {"file": "PlayfairDisplay.ttf", "weight": 600, "size": 56},
}

_EMOJI = re.compile(
    "(?:[\U0001f1e6-\U0001f1ff]{2}"
    "|[☀-➿⬀-⯿⌀-⏿\U0001f000-\U0001faff]"
    "[️\U0001f3fb-\U0001f3ff]*"
    "(?:‍[☀-➿\U0001f000-\U0001faff][️\U0001f3fb-\U0001f3ff]*)*)"
)


@lru_cache
def text_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    spec = STYLES[style]
    font = ImageFont.truetype(str(FONTS_DIR / spec["file"]), size)
    try:
        axes = font.get_variation_axes()
        values = []
        for axis in axes:
            name = axis.get("name", b"")
            name = name.decode() if isinstance(name, bytes) else str(name)
            if name.lower().startswith("weight"):
                values.append(spec["weight"])
            elif name.lower().startswith("optical"):
                values.append(min(max(size, axis["minimum"]), axis["maximum"]))
            else:
                values.append(axis.get("default", axis["minimum"]))
        font.set_variation_by_axes(values)
    except OSError:
        pass  # not a variable font
    return font


@lru_cache
def emoji_font_path() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
        str(FONTS_DIR / "NotoColorEmoji.ttf"),
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    if shutil.which("fc-match"):
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", "Noto Color Emoji"], capture_output=True, text=True
        ).stdout
        if "emoji" in out.lower() and Path(out).is_file():
            return out
    return None


@lru_cache(maxsize=256)
def emoji_image(emoji: str, height: int) -> Image.Image | None:
    path = emoji_font_path()
    if path is None:
        return None
    font = ImageFont.truetype(path, EMOJI_BITMAP_SIZE)
    canvas = Image.new("RGBA", (EMOJI_BITMAP_SIZE * 2, EMOJI_BITMAP_SIZE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((0, 0), emoji, font=font, embedded_color=True)
    box = canvas.getbbox()
    if box is None:
        return None
    glyph = canvas.crop(box)
    scale = height / glyph.height
    return glyph.resize((max(1, round(glyph.width * scale)), height), Image.LANCZOS)


def split_runs(text: str) -> list[tuple[str, bool]]:
    runs: list[tuple[str, bool]] = []
    pos = 0
    for m in _EMOJI.finditer(text):
        if m.start() > pos:
            runs.append((text[pos : m.start()], False))
        runs.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], False))
    return runs


def _run_width(run: str, is_emoji: bool, font: ImageFont.FreeTypeFont, emoji_h: int) -> int:
    if is_emoji:
        img = emoji_image(run, emoji_h)
        return img.width + 4 if img else 0
    return int(font.getlength(run))


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int, emoji_h: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            width = sum(_run_width(r, e, font, emoji_h) for r, e in split_runs(candidate))
            if width <= max_width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return _balance(lines, font, max_width, emoji_h)


def _balance(
    lines: list[str], font: ImageFont.FreeTypeFont, max_width: int, emoji_h: int
) -> list[str]:
    """Avoid a single lonely word on the last line, like CapCut does."""
    if len(lines) >= 2 and len(lines[-1].split()) == 1 and len(lines[-2].split()) > 2:
        words = lines[-2].split()
        moved = f"{words[-1]} {lines[-1]}"
        width = sum(_run_width(r, e, font, emoji_h) for r, e in split_runs(moved))
        if width <= max_width:
            lines[-2] = " ".join(words[:-1])
            lines[-1] = moved
    return lines


def render_text(
    text: str, style: str, frame_size: tuple[int, int], y_centre: float, out: Path
) -> Path:
    """Draw one overlay as a full frame transparent PNG."""
    width, height = frame_size
    size = int(STYLES[style]["size"] * width / 1080)
    font = text_font(style, size)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * 1.12)
    emoji_h = int(size * 1.0)
    lines = wrap(text, font, int(width * 0.8), emoji_h)

    layer = Image.new("RGBA", frame_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    block_h = line_h * len(lines)
    top = int(height * y_centre - block_h / 2)
    emoji_pastes: list[tuple[Image.Image, tuple[int, int]]] = []
    for i, line in enumerate(lines):
        runs = split_runs(line)
        line_w = sum(_run_width(r, e, font, emoji_h) for r, e in runs)
        x = (width - line_w) / 2
        y = top + i * line_h
        for run, is_emoji in runs:
            if is_emoji:
                img = emoji_image(run, emoji_h)
                if img:
                    emoji_pastes.append((img, (int(x + 2), int(y + (ascent - emoji_h) * 0.75 + 2))))
                    x += img.width + 4
            else:
                draw.text((x, y), run, font=font, fill=(255, 255, 255, 255))
                x += font.getlength(run)

    # Two soft shadows from the text shape: a tight one keeps the letters readable on
    # white backgrounds, a wide one gives TikTok's soft glow.
    alpha = layer.getchannel("A")
    result = Image.new("RGBA", frame_size, (0, 0, 0, 0))
    for strength, blur in ((0.75, max(2, size // 22)), (0.45, max(4, size // 7))):
        shadow = Image.new("RGBA", frame_size, (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda a, s=strength: int(a * s)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
        offset = Image.new("RGBA", frame_size, (0, 0, 0, 0))
        offset.paste(shadow, (0, max(1, size // 30)))
        result = Image.alpha_composite(result, offset)
    result = Image.alpha_composite(result, layer)
    for img, pos in emoji_pastes:
        result.alpha_composite(img, pos)
    result.save(out)
    return out
