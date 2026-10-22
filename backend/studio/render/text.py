"""Text overlays in the creator's style: white text, soft shadow, Apple style emoji.

FFmpeg's own text renderers cannot draw colour emoji, so overlays are drawn with Pillow
into transparent PNGs and composited by FFmpeg.

Fonts: TikTok Sans (TikTok's own text font) and Source Serif 4 SemiBold, which matched
the creator's reference videos best. Emoji: the Apple Color Emoji font if it is placed
in the data fonts folder, else the Apple emoji images from emoji-datasource-apple, else
Noto Color Emoji.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS_DIR = ASSETS / "fonts"

STYLES = {
    "sans": {"file": "TikTokSans.ttf", "weight": 500, "size": 50, "line": 1.16},
    "serif": {"file": "SourceSerif4.ttf", "weight": 600, "size": 54, "line": 1.12},
}

# TikTok covers the right edge with buttons and the bottom with the caption,
# so text stays inside this box (fractions of the frame).
SAFE_LEFT, SAFE_RIGHT = 0.11, 0.85
MAX_TEXT_WIDTH = SAFE_RIGHT - SAFE_LEFT

_EMOJI = re.compile(
    "(?:[\U0001f1e6-\U0001f1ff]{2}"
    "|[#*0-9]️?⃣"
    "|[©®‼⁉™ℹ↔-↪⌚-⏿Ⓜ▪-➿"
    "⤴⤵⬅-⭕〰〽㊗㊙\U0001f000-\U0001faff]"
    "[️\U0001f3fb-\U0001f3ff]*"
    "(?:‍[☀-➿\U0001f000-\U0001faff][️\U0001f3fb-\U0001f3ff]*)*)"
)


@dataclass(frozen=True)
class TextLook:
    style: str = "sans"
    color: tuple[int, int, int] = (255, 255, 255)


@lru_cache
def text_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    spec = STYLES[style]
    font = ImageFont.truetype(str(FONTS_DIR / spec["file"]), size)
    try:
        values = []
        for axis in font.get_variation_axes():
            name = axis.get("name", b"")
            name = (name.decode() if isinstance(name, bytes) else str(name)).lower()
            if name.startswith("weight"):
                values.append(spec["weight"])
            elif name.startswith("optical"):
                values.append(min(max(size / 2, axis["minimum"]), axis["maximum"]))
            else:
                values.append(axis.get("default", axis["minimum"]))
        font.set_variation_by_axes(values)
    except OSError:
        pass  # not a variable font
    return font


# Emoji sources ---------------------------------------------------------------------


def _codepoints(emoji: str) -> list[str]:
    return [f"{ord(c):x}" for c in emoji]


def _emoji_dirs() -> list[Path]:
    dirs = []
    if env := os.environ.get("STUDIO_EMOJI_DIR"):
        dirs.append(Path(env))
    if data := os.environ.get("STUDIO_DATA_DIR"):
        dirs.append(Path(data) / "emoji" / "apple")
    dirs.append(ASSETS / "emoji" / "apple")
    return [d for d in dirs if d.is_dir()]


@lru_cache
def _apple_font() -> ImageFont.FreeTypeFont | None:
    """The real Apple Color Emoji font, if the user copied it from a Mac."""
    candidates = []
    if data := os.environ.get("STUDIO_DATA_DIR"):
        candidates += [
            Path(data) / "fonts" / n for n in ("Apple Color Emoji.ttc", "AppleColorEmoji.ttc")
        ]
    for path in candidates:
        if path.is_file():
            for size in (160, 96, 64):
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    return None


@lru_cache
def _noto_font() -> ImageFont.FreeTypeFont | None:
    for path in (
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, 109)
    return None


def _from_font(font: ImageFont.FreeTypeFont, emoji: str) -> Image.Image | None:
    size = font.size
    canvas = Image.new("RGBA", (size * 3, size * 2), (0, 0, 0, 0))
    try:
        ImageDraw.Draw(canvas).text((0, 0), emoji, font=font, embedded_color=True)
    except OSError:
        return None
    box = canvas.getbbox()
    return canvas.crop(box) if box else None


def _from_images(emoji: str) -> Image.Image | None:
    points = _codepoints(emoji)
    names = [
        "-".join(points),
        "-".join(p for p in points if p != "fe0f"),
        "-".join([*points, "fe0f"]) if len(points) == 1 else "",
    ]
    for directory in _emoji_dirs():
        for name in names:
            if name and (directory / f"{name}.png").is_file():
                img = Image.open(directory / f"{name}.png").convert("RGBA")
                box = img.getbbox()
                return img.crop(box) if box else img
    return None


@lru_cache(maxsize=512)
def emoji_image(emoji: str, height: int) -> Image.Image | None:
    glyph = None
    apple = _apple_font()
    if apple is not None:
        glyph = _from_font(apple, emoji)
    if glyph is None:
        glyph = _from_images(emoji)
    if glyph is None and (noto := _noto_font()) is not None:
        glyph = _from_font(noto, emoji)
    if glyph is None:
        return None
    scale = height / glyph.height
    return glyph.resize((max(1, round(glyph.width * scale)), height), Image.LANCZOS)


def emoji_source() -> str:
    if _apple_font() is not None:
        return "Apple Color Emoji font"
    if _emoji_dirs():
        return "Apple emoji images"
    if _noto_font() is not None:
        return "Noto Color Emoji (Apple emoji not installed)"
    return "none (emoji are skipped)"


# Layout ---------------------------------------------------------------------------


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


def strip_emoji(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", text)).strip()


def _run_width(run: str, is_emoji: bool, font: ImageFont.FreeTypeFont, emoji_h: int) -> int:
    if is_emoji:
        img = emoji_image(run, emoji_h)
        return img.width + 6 if img else 0
    return int(round(font.getlength(run)))


def _line_width(line: str, font: ImageFont.FreeTypeFont, emoji_h: int) -> int:
    return sum(_run_width(r, e, font, emoji_h) for r, e in split_runs(line))


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int, emoji_h: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip()
            if _line_width(candidate, font, emoji_h) <= max_width or not line:
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
    """Even out two line texts and avoid a lonely word on the last line."""
    if len(lines) != 2:
        return lines
    words = " ".join(lines).split(" ")
    best = lines
    best_diff = abs(_line_width(lines[0], font, emoji_h) - _line_width(lines[1], font, emoji_h))
    for cut in range(1, len(words)):
        a, b = " ".join(words[:cut]), " ".join(words[cut:])
        wa, wb = _line_width(a, font, emoji_h), _line_width(b, font, emoji_h)
        if max(wa, wb) > max_width:
            continue
        # Prefer the first line slightly longer, like hand made captions.
        diff = abs(wa - wb) + (0 if wa >= wb else font.size)
        if diff < best_diff:
            best, best_diff = [a, b], diff
    return best


@dataclass
class Layout:
    lines: list[str]
    font: ImageFont.FreeTypeFont
    size: int
    line_h: int
    emoji_h: int
    top: int
    ascent: int


def layout(text: str, look: TextLook, frame_size: tuple[int, int], y_centre: float) -> Layout:
    width, height = frame_size
    spec = STYLES[look.style]
    size = int(spec["size"] * width / 1080)
    font = text_font(look.style, size)
    ascent, descent = font.getmetrics()
    line_h = int(size * spec["line"] + 0.5 * (ascent + descent - size))
    emoji_h = int(size * 1.02)
    lines = wrap(text, font, int(width * MAX_TEXT_WIDTH), emoji_h)
    top = int(height * y_centre - line_h * len(lines) / 2)
    return Layout(lines, font, size, line_h, emoji_h, top, ascent)


def render_text(
    text: str,
    look: TextLook | str,
    frame_size: tuple[int, int],
    y_centre: float,
    out: Path,
    visible: int | None = None,
    lay: Layout | None = None,
) -> Path:
    """Draw one overlay as a full frame transparent PNG.

    `visible` limits the number of characters drawn, for the typewriter reveal; the
    layout is computed from the full text so lines do not jump while typing.
    """
    if isinstance(look, str):
        look = TextLook(style=look)
    width, height = frame_size
    lay = lay or layout(text, look, frame_size, y_centre)
    centre_x = width * (SAFE_LEFT + SAFE_RIGHT) / 2

    layer = Image.new("RGBA", frame_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    emoji_pastes: list[tuple[Image.Image, tuple[int, int]]] = []
    budget = len(text) if visible is None else visible
    for i, line in enumerate(lay.lines):
        if budget <= 0:
            break
        runs = split_runs(line)
        x = centre_x - _line_width(line, lay.font, lay.emoji_h) / 2
        y = lay.top + i * lay.line_h
        for run, is_emoji in runs:
            if budget <= 0:
                break
            if is_emoji:
                img = emoji_image(run, lay.emoji_h)
                if img:
                    ey = int(y + lay.ascent - lay.emoji_h * 0.86)
                    emoji_pastes.append((img, (int(x + 3), ey)))
                    x += img.width + 6
                budget -= 1
            else:
                part = run[:budget]
                draw.text((x, y), part, font=lay.font, fill=(*look.color, 255))
                x += lay.font.getlength(run)
                budget -= len(run)
        budget -= 1  # the space that became a line break

    # Two soft shadows from the text shape: a tight one keeps letters readable on
    # white backgrounds, a wide one gives TikTok's soft glow.
    alpha = layer.getchannel("A")
    for img, pos in emoji_pastes:
        mask = Image.new("L", frame_size, 0)
        mask.paste(img.getchannel("A"), pos)
        alpha = Image.fromarray(np.maximum(np.asarray(alpha), np.asarray(mask) // 2))
    result = Image.new("RGBA", frame_size, (0, 0, 0, 0))
    for strength, blur in ((0.72, max(2, lay.size // 22)), (0.42, max(4, lay.size // 7))):
        shadow = Image.new("RGBA", frame_size, (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda a, s=strength: int(a * s)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
        offset = Image.new("RGBA", frame_size, (0, 0, 0, 0))
        offset.paste(shadow, (0, max(1, lay.size // 30)))
        result = Image.alpha_composite(result, offset)
    result = Image.alpha_composite(result, layer)
    for img, pos in emoji_pastes:
        result.alpha_composite(img, pos)
    result.save(out)
    return out


def typewriter_frames(
    text: str,
    look: TextLook,
    frame_size: tuple[int, int],
    y_centre: float,
    folder: Path,
    fps: int,
    seconds: float,
) -> int:
    """Render the reveal as numbered PNGs (0001.png ...). Returns the frame count."""
    folder.mkdir(parents=True, exist_ok=True)
    lay = layout(text, look, frame_size, y_centre)
    frames = max(int(seconds * fps), 2)
    total = len(text)
    for f in range(frames):
        visible = round(total * (f + 1) / frames)
        render_text(
            text, look, frame_size, y_centre, folder / f"{f + 1:04d}.png", visible=visible, lay=lay
        )
    return frames
