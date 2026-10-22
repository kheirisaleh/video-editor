import subprocess
from pathlib import Path

import numpy as np

from studio.media.ffmpeg import probe, sdr_filter


def frame(src: Path, vf: str) -> np.ndarray:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(src), "-frames:v", "1",
         "-vf", f"{vf}scale=90:160", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    return np.frombuffer(out, np.uint8).reshape(160, 90, 3).astype(float)


def test_probe_detects_iphone_hdr(hlg_video: Path, sample_videos: dict[str, Path]) -> None:
    info = probe(hlg_video)
    assert info["hdr"] == "hlg"
    assert info["video_codec"] == "hevc"
    assert probe(sample_videos["vertical"])["hdr"] is None


def test_hdr_is_converted_to_natural_sdr(hlg_video: Path) -> None:
    converted = frame(hlg_video, sdr_filter("hlg"))
    naive = frame(hlg_video, "format=yuv420p,")

    def saturation(a: np.ndarray) -> float:
        return float((a.max(2) - a.min(2)).mean())

    # Without conversion HLG looks grey; the conversion restores colour and contrast.
    assert saturation(converted) > saturation(naive) * 1.4
    assert converted.std() > naive.std()
    assert sdr_filter(None) == ""
