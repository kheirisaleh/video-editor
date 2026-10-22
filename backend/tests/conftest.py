import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio.config import get_settings


@pytest.fixture(scope="session")
def sample_videos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("media")
    videos = {"vertical": (360, 640, 2), "horizontal": (640, 360, 1)}
    paths = {}
    for name, (w, h, seconds) in videos.items():
        path = root / f"{name}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30:duration={seconds}",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                str(path),
            ],
            check=True,
        )  # fmt: skip
        paths[name] = path
    return paths


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    from studio.api.main import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def hlg_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two seconds of 10 bit HEVC HLG, like an iPhone records by default."""
    path = tmp_path_factory.mktemp("hdr") / "IMG_HDR.MOV"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=2",
            "-vf", "zscale=tin=bt709:min=bt709:pin=bt709:rin=tv:t=arib-std-b67:m=bt2020nc:"
                   "p=bt2020:r=tv:npl=100,format=yuv420p10le",
            "-c:v", "libx265", "-x265-params",
            "log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc",
            "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
            "-tag:v", "hvc1", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path
