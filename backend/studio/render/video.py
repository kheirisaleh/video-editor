"""Render an edit plan into a TikTok ready MP4 with FFmpeg."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from studio.media import ffmpeg
from studio.planning.schema import EditPlan
from studio.render.text import render_text

WIDTH, HEIGHT, FPS = 1080, 1920, 30
# Gentle and natural, like the reference videos: a touch of contrast and warmth.
GRADE = "eq=contrast=1.03:saturation=1.05:gamma=1.01,colorbalance=rs=0.015:bs=-0.015"


@dataclass
class SourceClip:
    path: Path
    width: int
    height: int


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
    overlays: list[tuple[Path, float, float, str]],
    music: Path | None,
    out: Path,
) -> list[str]:
    args: list[str] = []
    filters: list[str] = []
    for i, seg in enumerate(plan.segments):
        src = sources[seg.clip_id]
        args += ["-ss", f"{seg.start:.3f}", "-t", f"{seg.end - seg.start:.3f}", "-i", str(src.path)]
        speed = f",setpts=PTS/{seg.speed}" if seg.speed != 1.0 else ""
        filters.append(
            f"[{i}:v]{crop_filter(src, seg.crop_x)},setsar=1,fps={FPS},{GRADE},"
            f"format=yuv420p{speed},setpts=PTS-STARTPTS[v{i}]"
        )
    n = len(plan.segments)
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[base]")

    total = plan.duration
    current = "base"
    for j, (png, start, end, animation) in enumerate(overlays):
        idx = n + j
        length = end - start
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", str(png)]
        fade_in = 0.12 if animation == "none" else 0.25
        filters.append(
            f"[{idx}:v]format=rgba,fade=t=in:st=0:d={fade_in}:alpha=1,"
            f"fade=t=out:st={max(length - 0.2, 0):.3f}:d=0.2:alpha=1,"
            f"setpts=PTS-STARTPTS+{start:.3f}/TB[t{j}]"
        )
        filters.append(f"[{current}][t{j}]overlay=0:0:eof_action=pass:format=auto[o{j}]")
        current = f"o{j}"
    filters.append(f"[{current}]format=yuv420p[vout]")

    audio_idx = n + len(overlays)
    if music is not None:
        start = plan.music.start if plan.music else 0.0
        args += ["-ss", f"{start:.3f}", "-i", str(music)]
        filters.append(
            f"[{audio_idx}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.4,afade=t=out:st={max(total - 1.2, 0):.3f}:d=1.2,"
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
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out),
    ]  # fmt: skip


def render_plan(
    plan: EditPlan,
    sources: dict[str, SourceClip],
    music: Path | None,
    out: Path,
    scratch: Path,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    overlays = []
    for k, text in enumerate(plan.texts):
        png = render_text(text.text, plan.style, (WIDTH, HEIGHT), text.y, scratch / f"text_{k}.png")
        overlays.append((png, text.start, text.end, text.animation))
    cmd = build_command(plan, sources, overlays, music, out)
    ffmpeg.run(cmd, duration=plan.duration, on_progress=on_progress, should_cancel=should_cancel)


def strip_audio(src: Path, out: Path) -> None:
    """Copy of the video with a silent track, for adding a trending sound inside TikTok."""
    ffmpeg.run([
        "-i", str(src), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart", str(out),
    ])  # fmt: skip


def cover(src: Path, out: Path, at: float = 0.6) -> None:
    ffmpeg.run(["-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(out)])
