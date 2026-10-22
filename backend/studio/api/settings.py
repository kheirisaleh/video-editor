from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from studio import music as library
from studio.config import Settings, get_settings
from studio.db import get_session
from studio.media.ffmpeg import FFmpegError, audio_duration
from studio.options import RenderOptions, load_defaults, save_defaults
from studio.render.text import FONTS_DIR, STYLES, emoji_source

router = APIRouter(prefix="/api")

DbSession = Annotated[Session, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
MAX_MUSIC_MB = 50


class Track(BaseModel):
    name: str
    title: str
    duration: float
    size_bytes: int
    tempo: float | None
    url: str


class SettingsOut(BaseModel):
    defaults: RenderOptions
    emoji: str
    fonts: dict[str, str]


@router.get("/settings", response_model=SettingsOut)
def get_app_settings(session: DbSession) -> SettingsOut:
    return SettingsOut(
        defaults=load_defaults(session),
        emoji=emoji_source(),
        fonts={k: Path(v["file"]).stem for k, v in STYLES.items()},
    )


@router.put("/settings/defaults", response_model=RenderOptions)
def put_defaults(body: RenderOptions, session: DbSession) -> RenderOptions:
    save_defaults(session, body)
    return body


def _track(path: Path) -> Track:
    try:
        duration = audio_duration(path)
    except FFmpegError:
        duration = 0.0
    info = library.beat_info(path)
    return Track(
        name=path.name,
        title=path.stem,
        duration=duration,
        size_bytes=path.stat().st_size,
        tempo=info.tempo if info else None,
        url=f"/api/music/{path.name}",
    )


@router.get("/fonts/{name}")
def font_file(name: str) -> FileResponse:
    """The overlay fonts, so the options page can preview them."""
    allowed = {spec["file"] for spec in STYLES.values()}
    if name not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "font not found")
    return FileResponse(FONTS_DIR / name, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/music", response_model=list[Track])
def list_music(settings: AppSettings) -> list[Track]:
    return [_track(p) for p in library.tracks(settings.music_dir)]


@router.put("/music", response_model=Track, status_code=status.HTTP_201_CREATED)
async def upload_music(
    request: Request,
    settings: AppSettings,
    filename: Annotated[str, Query(min_length=1, max_length=200)],
) -> Track:
    name = Path(filename).name
    if Path(name).suffix.lower() not in library.MUSIC_EXTENSIONS or name.startswith("."):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported audio file")
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    target = settings.music_dir / name
    partial = settings.music_dir / f".{name}.part"
    size = 0
    try:
        async with aiofiles.open(partial, "wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_MUSIC_MB * 1024 * 1024:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"file larger than {MAX_MUSIC_MB} MB",
                    )
                await out.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
        try:
            await run_in_threadpool(audio_duration, partial)
        except FFmpegError as exc:
            raise HTTPException(422, "not a readable audio file") from exc
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return await run_in_threadpool(_track, target)


@router.get("/music/{name}")
def music_file(name: str, settings: AppSettings) -> FileResponse:
    path = library.find(settings.music_dir, name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "track not found")
    return FileResponse(path)


@router.delete("/music/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_music(name: str, settings: AppSettings) -> None:
    path = library.find(settings.music_dir, name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "track not found")
    path.unlink()
    (path.parent / library.CACHE_DIR / f"{path.name}.json").unlink(missing_ok=True)
