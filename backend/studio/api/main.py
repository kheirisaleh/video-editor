import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from studio import __version__
from studio.config import get_settings
from studio.db import init_db, session_scope
from studio.models import Workflow, WorkflowStatus
from studio.schemas import Health

from . import live, workflows


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    settings.ensure_dirs()
    init_db(settings.db_url)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Studio", version=__version__, lifespan=lifespan)
    app.include_router(workflows.router)
    app.include_router(live.router)

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        with session_scope() as s:
            queued = s.query(Workflow).filter_by(status=WorkflowStatus.QUEUED).count()
            running = s.query(Workflow).filter_by(status=WorkflowStatus.RUNNING).count()
        return Health(
            ok=True,
            ffmpeg=shutil.which("ffmpeg") is not None,
            version=__version__,
            queued=queued,
            running=running,
        )

    frontend = get_settings().frontend_dir
    if frontend and (frontend / "index.html").is_file():
        _mount_frontend(app, frontend)
    return app


def _mount_frontend(app: FastAPI, root: Path) -> None:
    """Serve the built PWA and fall back to index.html for client side routes."""
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    index = root / "index.html"
    root_resolved = root.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if path and candidate.is_relative_to(root_resolved) and candidate.is_file():
            headers = (
                {"Cache-Control": "no-cache"}
                if candidate.name in ("sw.js", "manifest.webmanifest")
                else None
            )
            return FileResponse(candidate, headers=headers)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
