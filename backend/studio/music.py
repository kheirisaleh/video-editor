"""Music library: plain audio files in the data folder, with cached beat analysis."""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from studio.analysis.beats import BeatInfo, analyze_music

log = logging.getLogger(__name__)

MUSIC_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"}
CACHE_DIR = ".analysis"


def tracks(music_dir: Path) -> list[Path]:
    if not music_dir.is_dir():
        return []
    return sorted(
        (p for p in music_dir.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTENSIONS),
        key=lambda p: p.name.lower(),
    )


def find(music_dir: Path, name: str) -> Path | None:
    for path in tracks(music_dir):
        if path.name == name:
            return path
    return None


def beat_info(path: Path) -> BeatInfo | None:
    """Beat analysis, cached next to the track and refreshed when the file changes."""
    cache = path.parent / CACHE_DIR / f"{path.name}.json"
    stamp = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
    if cache.is_file():
        try:
            data = json.loads(cache.read_text())
            if data.get("stamp") == stamp:
                return BeatInfo(**data["info"])
        except (ValueError, TypeError, KeyError):
            pass
    try:
        info = analyze_music(path)
    except Exception:  # a broken file must not stop the workflow
        log.exception("beat analysis failed for %s", path.name)
        return None
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"stamp": stamp, "info": asdict(info)}))
    return info
