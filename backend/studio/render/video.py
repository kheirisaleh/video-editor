"""Render an edit plan into a TikTok ready MP4 with FFmpeg."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from studio.media import ffmpeg
from studio.planning.schema import EditPlan
from studio.render.text import TextLook, render_text, typewriter_frames

WIDTH, HEIGHT, FPS = 1080, 1920, 30
# Gentle and natural, like the reference videos: a touch of contrast and warmth.
GRADE = "eq=contrast=1.03:saturation=1.05,colorbalance=rs=0.015:bs=-0.015"
TYPEWRITER_SECONDS_PER_CHAR = 0.035
FADE_IN, FADE_OUT = 0.22, 0.18

ENCODE = {
    "high": ["-preset", "slow", "-crf", "17"],
    "standard": ["-preset", "medium", "-crf", "19"],
}


@dataclass
class SourceClip:
    path: Path
    width: int
    height: int


@dataclass
class Overlay:
    start: float
    end: float
    still: Path | None = None
    frames: Path | None = None  # folder with 0001.png ... for an animated reveal
    frame_count: int = 0


def crop_filter(src: SourceClip, crop_x: float) -> str:
    """Scale to cover 1080x1920, then crop around the subject."""
    scale = max(WIDTH / src.width, HEIGHT / src.height)
    sw = max(WIDTH, math.ceil(src.width * scale / 2) * 2)
    sh = max(HEIGHT, math.ceil(src.height * scale / 2) * 2)
    x = int(min(max(crop_x * sw - WIDTH / 2, 0), sw - WIDTH))
    y = int((sh - HEIGHT) / 2)
    return f"scale={sw}:{sh}:flags=lanczos,crop={WIDTH}:{HEIGHT}:{x}:{y}"


def build_command(
    plan: EditPlan,
    sources: dict[str, SourceClip],
    overlays: list[Overlay],
    music: Path | None,
    out: Path,
    quality: str = "high",
) -> list[str]:
    args: list[str] = []
    filters: list[str] = []
    for i, seg in enumerate(plan.segments):
        src = sources[seg.clip_id]
        args += ["-ss", f"{seg.start:.3f}", "-t", f"{seg.end - seg.start:.3f}", "-i", str(src.path)]
        speed = f",setpts=PTS/{seg.speed}" if seg.speed != 1.0 else ""
        gamma = f",eq=gamma={seg.gamma:.3f}" if abs(seg.gamma - 1.0) > 0.005 else ""
        filters.append(
            f"[{i}:v]{crop_filter(src, seg.crop_x)},setsar=1,fps={FPS}{gamma},{GRADE},"
            f"format=yuv420p{speed},setpts=PTS-STARTPTS[v{i}]"
        )
    n = len(plan.segments)
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[base]")

    total = plan.duration
    current = "base"
    for j, ov in enumerate(overlays):
        idx = n + j
        length = ov.end - ov.start
        if ov.frames is not None:
            reveal = ov.frame_count / FPS
            args += ["-framerate", str(FPS), "-i", str(ov.frames / "%04d.png")]
            hold = max(length - reveal, 0.0)
            source = f"[{idx}:v]format=rgba,tpad=stop_mode=clone:stop_duration={hold:.3f}"
        else:
            args += [
                "-loop",
                "1",
                "-framerate",
                str(FPS),
                "-t",
                f"{length:.3f}",
                "-i",
                str(ov.still),
            ]
            source = f"[{idx}:v]format=rgba,fade=t=in:st=0:d={FADE_IN}:alpha=1"
        filters.append(
            f"{source},fade=t=out:st={max(length - FADE_OUT, 0):.3f}:d={FADE_OUT}:alpha=1,"
            f"trim=duration={length:.3f},setpts=PTS-STARTPTS+{ov.start:.3f}/TB[t{j}]"
        )
        filters.append(f"[{current}][t{j}]overlay=0:0:eof_action=pass:format=auto[o{j}]")
        current = f"o{j}"
    filters.append(f"[{current}]format=yuv420p[vout]")

    audio_idx = n + len(overlays)
    if music is not None:
        start = plan.music.start if plan.music else 0.0
        fade_out = min(1.2, total / 4)
        args += ["-ss", f"{start:.3f}", "-i", str(music)]
        filters.append(
            f"[{audio_idx}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.05,"
            f"afade=t=out:st={max(total - fade_out, 0):.3f}:d={fade_out:.3f},"
            f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[aout]"
        )
    else:
        args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filters.append(f"[{audio_idx}:a]anull[aout]")

    return [
        *args,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", *ENCODE.get(quality, ENCODE["high"]),
        "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-g", str(FPS * 2), "-bf", "2",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out),
    ]  # fmt: skip


def prepare_overlays(plan: EditPlan, scratch: Path) -> list[Overlay]:
    look = TextLook(style=plan.style)
    overlays = []
    for k, text in enumerate(plan.texts):
        length = text.end - text.start
        if text.animation == "typewriter":
            reveal = min(len(text.text) * TYPEWRITER_SECONDS_PER_CHAR, length * 0.5, 1.6)
            folder = scratch / f"text_{k}"
            count = typewriter_frames(text.text, look, (WIDTH, HEIGHT), text.y, folder, FPS, reveal)
            overlays.append(Overlay(text.start, text.end, frames=folder, frame_count=count))
        else:
            png = render_text(text.text, look, (WIDTH, HEIGHT), text.y, scratch / f"text_{k}.png")
            overlays.append(Overlay(text.start, text.end, still=png))
    return overlays


def render_plan(
    plan: EditPlan,
    sources: dict[str, SourceClip],
    music: Path | None,
    out: Path,
    scratch: Path,
    quality: str = "high",
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    overlays = prepare_overlays(plan, scratch)
    cmd = build_command(plan, sources, overlays, music, out, quality)
    ffmpeg.run(cmd, duration=plan.duration, on_progress=on_progress, should_cancel=should_cancel)


def strip_audio(src: Path, out: Path) -> None:
    """Copy of the video with a silent track, for adding a trending sound inside TikTok."""
    ffmpeg.run([
        "-i", str(src), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart", str(out),
    ])  # fmt: skip


def cover(src: Path, out: Path, at: float = 0.6) -> None:
    ffmpeg.run(["-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(out)])
