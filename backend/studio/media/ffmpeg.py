import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


class FFmpegError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def _binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FFmpegError(f"{name} not found on PATH")
    return path


def probe(path: Path) -> dict[str, Any]:
    """Return the relevant stream facts of a media file.

    Width and height are reported as displayed, so rotation metadata from phones
    is already applied.
    """
    cmd = [
        _binary("ffprobe"),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {proc.stderr.strip()[:500]}")
    data = json.loads(proc.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("file contains no video stream")
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    rotation = _rotation(video)
    width, height = int(video["width"]), int(video["height"])
    if rotation in (90, 270):
        width, height = height, width

    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    return {
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "rotation": rotation,
        "fps": _fps(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"),
        "video_codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "has_audio": audio is not None,
        "bitrate": int(data.get("format", {}).get("bit_rate") or 0),
        "hdr": hdr_kind(video),
        "color_transfer": video.get("color_transfer"),
        "orientation": "vertical"
        if height > width
        else "horizontal"
        if width > height
        else "square",
    }


def audio_duration(path: Path) -> float:
    """Duration of an audio file in seconds; raises FFmpegError if it is not readable."""
    cmd = [
        _binary("ffprobe"),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-select_streams",
        "a",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout)
    if not data.get("streams"):
        raise FFmpegError("file contains no audio stream")
    return round(float(data.get("format", {}).get("duration") or 0.0), 2)


HDR_TRANSFERS = {"arib-std-b67": "hlg", "smpte2084": "pq"}


def hdr_kind(stream: dict[str, Any]) -> str | None:
    """'hlg' or 'pq' for HDR video (iPhones record HLG by default), else None."""
    kind = HDR_TRANSFERS.get(str(stream.get("color_transfer") or ""))
    if kind:
        return kind
    for side in stream.get("side_data_list", []) or []:
        if "DOVI" in str(side.get("side_data_type", "")):
            return "hlg"  # Dolby Vision profile 8.4 from iPhones has an HLG base layer
    return None


def sdr_filter(hdr: str | None) -> str:
    """Filter chain that turns HDR into natural looking SDR (BT.709), or '' for SDR.

    Without it, HLG and PQ footage looks flat and grey once it is encoded as SDR.
    """
    if not hdr:
        return ""
    peak = 100 if hdr == "hlg" else 203
    return (
        f"zscale=t=linear:npl={peak},format=gbrpf32le,zscale=p=bt709,"
        "tonemap=tonemap=mobius:param=0.6:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
    )


def _rotation(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            return int(round(float(side["rotation"]))) % 360
    rotate = stream.get("tags", {}).get("rotate")
    return int(rotate) % 360 if rotate else 0


def _fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    try:
        return round(float(num) / float(den or 1), 3)
    except (ValueError, ZeroDivisionError):
        return 0.0


def thumbnail(
    src: Path, dst: Path, at_seconds: float, width: int = 360, hdr: str | None = None
) -> None:
    run(
        [
            "-ss",
            f"{max(at_seconds, 0):.3f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-vf",
            f"{sdr_filter(hdr)}scale={width}:-2",
            "-q:v",
            "4",
            str(dst),
        ]
    )


def make_proxy(
    src: Path,
    dst: Path,
    duration: float,
    height: int,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    hdr: str | None = None,
) -> None:
    """Low resolution, constant frame rate SDR copy used for fast analysis."""
    run(
        [
            "-i",
            str(src),
            "-vf",
            f"{sdr_filter(hdr)}scale=-2:'min({height},ih)':flags=bicubic,fps=30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(dst),
        ],
        duration=duration,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )


def run(
    args: list[str],
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Run ffmpeg, reporting progress (0..1) when the output duration is known."""
    cmd = [
        _binary("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-progress",
        "pipe:1",
        *args,
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if should_cancel and should_cancel():
                proc.kill()
                proc.wait()
                raise Cancelled()
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and duration and on_progress and value.isdigit():
                on_progress(min(int(value) / 1_000_000 / duration, 1.0))
        stderr = proc.stderr.read() if proc.stderr else ""
        if proc.wait() != 0:
            raise FFmpegError(f"ffmpeg failed: {stderr.strip()[-800:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
