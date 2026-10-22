import io
import shutil
import time
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image as PILImage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from studio import music as library
from studio.ai.client import AiError, Image, make_client
from studio.ai.settings import AiSettingsIn, AiSettingsOut, load_ai, public, save_ai
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


class Storage(BaseModel):
    uploads: int
    work: int
    exports: int
    music: int
    free: int
    total: int


class SettingsOut(BaseModel):
    defaults: RenderOptions
    emoji: str
    fonts: dict[str, str]
    storage: Storage


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@router.get("/settings", response_model=SettingsOut)
def get_app_settings(session: DbSession, settings: AppSettings) -> SettingsOut:
    disk = shutil.disk_usage(settings.data_dir)
    return SettingsOut(
        defaults=load_defaults(session),
        emoji=emoji_source(),
        fonts={k: Path(v["file"]).stem for k, v in STYLES.items()},
        storage=Storage(
            uploads=_size(settings.uploads_dir), work=_size(settings.work_dir),
            exports=_size(settings.exports_dir), music=_size(settings.music_dir),
            free=disk.free, total=disk.total,
        ),
    )  # fmt: skip


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


# AI ---------------------------------------------------------------------------------


class AiTestResult(BaseModel):
    ok: bool
    provider: str
    text_ok: bool = False
    vision_ok: bool = False
    seconds: float = 0.0
    detail: str = ""


@router.get("/settings/ai", response_model=AiSettingsOut)
def get_ai(session: DbSession) -> AiSettingsOut:
    return public(load_ai(session))


@router.put("/settings/ai", response_model=AiSettingsOut)
def put_ai(body: AiSettingsIn, session: DbSession) -> AiSettingsOut:
    if body.provider == "openai" and not body.base_url.strip():
        raise HTTPException(422, "the OpenAI compatible provider needs a base URL")
    return public(save_ai(session, body))


@router.post("/settings/ai/test", response_model=AiTestResult)
def test_ai(session: DbSession) -> AiTestResult:
    """Ask the configured model two tiny questions: one in text, one about an image."""
    settings = load_ai(session)
    if not settings.enabled:
        return AiTestResult(ok=False, provider="none", detail="no AI provider configured")
    started = time.monotonic()
    result = AiTestResult(ok=False, provider=settings.provider)
    try:
        client = make_client(settings)
        assert client is not None
        answer = client.json(
            system="You check connectivity. Translate the Persian text to English.",
            parts=["کرم آبرسان"],
            schema={"type": "object", "properties": {"english": {"type": "string"}},
                    "required": ["english"], "additionalProperties": False},
            max_tokens=2000,
        )  # fmt: skip
        result.text_ok = bool(str(answer.get("english", "")).strip())
        swatch = io.BytesIO()
        PILImage.new("RGB", (64, 64), (220, 30, 30)).save(swatch, format="JPEG")
        answer = client.json(
            system="Name the single main colour of the image in one lowercase English word.",
            parts=[Image(swatch.getvalue()), "Which colour is this?"],
            schema={"type": "object", "properties": {"color": {"type": "string"}},
                    "required": ["color"], "additionalProperties": False},
            vision=True, max_tokens=2000,
        )  # fmt: skip
        result.vision_ok = "red" in str(answer.get("color", "")).lower()
        result.ok = result.text_ok and result.vision_ok
        result.detail = (
            f"{client.name} works"
            if result.ok
            else "connected, but "
            + (
                "the vision model did not recognise a red image"
                if result.text_ok
                else "the text answer was empty"
            )
        )
    except AiError as exc:
        result.detail = str(exc)
    result.seconds = round(time.monotonic() - started, 1)
    return result
