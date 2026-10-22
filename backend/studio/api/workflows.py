import re
import shutil
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from studio.config import Settings, get_settings
from studio.db import get_session, session_scope
from studio.events import EventType, emit
from studio.models import Clip, StepStatus, Workflow, WorkflowStatus, new_id, utcnow
from studio.options import load_defaults, merge, workflow_options
from studio.schemas import (
    ClipOut,
    OutputOut,
    StepOut,
    WorkflowCreate,
    WorkflowOut,
    WorkflowSummary,
    WorkflowUpdate,
)
from studio.worker.pipeline import ensure_step_rows

router = APIRouter(prefix="/api")

DbSession = Annotated[Session, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".hevc"}
CHUNK = 1024 * 1024


def _get(session: Session, workflow_id: str) -> Workflow:
    wf = session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow not found")
    return wf


def _require(wf: Workflow, *allowed: WorkflowStatus) -> None:
    if wf.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"not possible while workflow is {wf.status}",
        )


def _queue_positions(session: Session) -> dict[str, int]:
    queued = (
        session.query(Workflow.id)
        .filter_by(status=WorkflowStatus.QUEUED)
        .order_by(Workflow.queued_at, Workflow.created_at)
        .all()
    )
    return {row.id: i for i, row in enumerate(queued, start=1)}


def _clip_out(clip: Clip) -> ClipOut:
    base = f"/api/clips/{clip.id}"
    return ClipOut(
        id=clip.id,
        position=clip.position,
        original_name=clip.original_name,
        size_bytes=clip.size_bytes,
        probe=clip.probe,
        thumbnail_url=f"{base}/thumbnail" if clip.thumbnail else None,
        proxy_url=f"{base}/proxy" if clip.proxy else None,
        original_url=f"{base}/original",
    )


def _progress(wf: Workflow) -> float:
    if not wf.steps:
        return 0.0
    return round(
        sum(1.0 if s.status == StepStatus.DONE else s.progress for s in wf.steps) / len(wf.steps), 4
    )


def _summary_fields(wf: Workflow, positions: dict[str, int]) -> dict:
    first = next((c for c in wf.clips if c.thumbnail), None)
    return {
        "id": wf.id,
        "title": wf.title,
        "status": wf.status,
        "current_step": wf.current_step,
        "progress": _progress(wf),
        "error": wf.error,
        "clip_count": len(wf.clips),
        "thumbnail_url": f"/api/clips/{first.id}/thumbnail" if first else None,
        "queue_position": positions.get(wf.id),
        "created_at": wf.created_at,
        "started_at": wf.started_at,
        "finished_at": wf.finished_at,
    }


def _workflow_out(session: Session, wf: Workflow) -> WorkflowOut:
    return WorkflowOut(
        **_summary_fields(wf, _queue_positions(session)),
        product_text=wf.product_text,
        product_url=wf.product_url,
        prompt=wf.prompt,
        clips=[_clip_out(c) for c in wf.clips],
        steps=[StepOut.model_validate(s) for s in wf.steps],
        outputs=_outputs(wf),
        options=workflow_options(session, wf.options),
    )


def _outputs(wf: Workflow) -> list[OutputOut]:
    render = next((s for s in wf.steps if s.name == "render"), None)
    if render is None or render.status != StepStatus.DONE or not render.result:
        return []
    base = f"/api/workflows/{wf.id}/files"
    return [
        OutputOut(
            index=o["index"],
            label=o["label"],
            duration=o["duration"],
            video_url=f"{base}/{o['video']}",
            silent_url=f"{base}/{o['silent']}" if o.get("silent") else None,
            cover_url=f"{base}/{o['cover']}",
            caption=o["caption"],
            music=o.get("music"),
            size_bytes=o["size_bytes"],
        )
        for o in render.result.get("outputs", [])
    ]


def _validated_options(session: Session, current: dict | None, overrides: dict | None) -> dict:
    """Snapshot of the defaults with the overrides applied, so later changes to the
    defaults do not alter a workflow that was already created."""
    base = merge(load_defaults(session), current)
    try:
        return merge(base, overrides).model_dump()
    except ValueError as exc:
        raise HTTPException(422, f"invalid options: {exc}") from exc


@router.get("/workflows", response_model=list[WorkflowSummary])
def list_workflows(
    session: DbSession,
    status_filter: Annotated[WorkflowStatus | None, Query(alias="status")] = None,
) -> list[WorkflowSummary]:
    q = session.query(Workflow)
    if status_filter:
        q = q.filter_by(status=status_filter)
    positions = _queue_positions(session)
    return [
        WorkflowSummary(**_summary_fields(wf, positions))
        for wf in q.order_by(Workflow.created_at.desc()).limit(200)
    ]


@router.post("/workflows", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(body: WorkflowCreate, session: DbSession) -> WorkflowOut:
    wf = Workflow(
        title=body.title.strip(),
        product_text=body.product_text.strip(),
        product_url=str(body.product_url) if body.product_url else "",
        prompt=body.prompt.strip(),
        options=_validated_options(session, None, body.options),
    )
    ensure_step_rows(wf)
    session.add(wf)
    session.flush()
    emit(session, EventType.WORKFLOW, wf.id, status=wf.status, created=True)
    return _workflow_out(session, wf)


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, session: DbSession) -> WorkflowOut:
    return _workflow_out(session, _get(session, workflow_id))


@router.patch("/workflows/{workflow_id}", response_model=WorkflowOut)
def update_workflow(workflow_id: str, body: WorkflowUpdate, session: DbSession) -> WorkflowOut:
    wf = _get(session, workflow_id)
    _require(
        wf,
        WorkflowStatus.DRAFT,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.DONE,
    )
    data = body.model_dump(exclude_unset=True)
    if "options" in data:
        wf.options = _validated_options(session, wf.options, data.pop("options"))
    for key, value in data.items():
        if key == "product_url":
            value = str(value) if value else ""
        setattr(wf, key, value.strip() if isinstance(value, str) else value)
    emit(session, EventType.WORKFLOW, wf.id, status=wf.status, updated=True)
    return _workflow_out(session, wf)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: str, session: DbSession, settings: AppSettings) -> None:
    wf = _get(session, workflow_id)
    _require(
        wf,
        WorkflowStatus.DRAFT,
        WorkflowStatus.QUEUED,
        WorkflowStatus.DONE,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    )
    session.delete(wf)
    emit(session, EventType.WORKFLOW, workflow_id, status="deleted")
    for root in (settings.uploads_dir, settings.work_dir, settings.exports_dir):
        shutil.rmtree(root / workflow_id, ignore_errors=True)


@router.put(
    "/workflows/{workflow_id}/clips", response_model=ClipOut, status_code=status.HTTP_201_CREATED
)
async def upload_clip(
    workflow_id: str,
    request: Request,
    settings: AppSettings,
    filename: Annotated[str, Query(min_length=1, max_length=500)],
) -> ClipOut:
    """Upload one clip as the raw request body, so large phone videos stream straight to disk.

    No database session is held open while the body streams in.
    """
    ext = Path(filename).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported file type {ext or '(none)'}"
        )

    def check() -> None:
        with session_scope() as session:
            _require(_get(session, workflow_id), WorkflowStatus.DRAFT)

    await run_in_threadpool(check)

    clip_id = new_id()
    stored = f"{clip_id}{ext}"
    target_dir = settings.uploads_dir / workflow_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / stored
    limit = settings.max_upload_mb * 1024 * 1024

    size = 0
    try:
        async with aiofiles.open(target, "wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"file larger than {settings.max_upload_mb} MB",
                    )
                await out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")

    def insert() -> ClipOut:
        with session_scope() as session:
            wf = _get(session, workflow_id)
            _require(wf, WorkflowStatus.DRAFT)
            clip = Clip(
                id=clip_id,
                position=max((c.position for c in wf.clips), default=-1) + 1,
                original_name=Path(filename).name,
                filename=stored,
                size_bytes=size,
            )
            wf.clips.append(clip)
            session.flush()
            emit(session, EventType.WORKFLOW, wf.id, status=wf.status, clip_added=clip.id)
            return _clip_out(clip)

    try:
        return await run_in_threadpool(insert)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


@router.delete("/workflows/{workflow_id}/clips/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clip(workflow_id: str, clip_id: str, session: DbSession, settings: AppSettings) -> None:
    wf = _get(session, workflow_id)
    _require(wf, WorkflowStatus.DRAFT)
    clip = next((c for c in wf.clips if c.id == clip_id), None)
    if clip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clip not found")
    (settings.uploads_dir / workflow_id / clip.filename).unlink(missing_ok=True)
    wf.clips.remove(clip)
    emit(session, EventType.WORKFLOW, wf.id, status=wf.status, clip_removed=clip_id)


@router.post("/workflows/{workflow_id}/submit", response_model=WorkflowOut)
def submit_workflow(workflow_id: str, session: DbSession) -> WorkflowOut:
    wf = _get(session, workflow_id)
    _require(wf, WorkflowStatus.DRAFT)
    if not wf.clips:
        raise HTTPException(422, "upload at least one clip")
    if not wf.product_text and not wf.product_url:
        raise HTTPException(422, "product description or link is required")
    _enqueue(session, wf)
    return _workflow_out(session, wf)


@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowOut)
def cancel_workflow(workflow_id: str, session: DbSession) -> WorkflowOut:
    wf = _get(session, workflow_id)
    _require(wf, WorkflowStatus.QUEUED, WorkflowStatus.RUNNING)
    if wf.status == WorkflowStatus.QUEUED:
        wf.status = WorkflowStatus.CANCELLED
        wf.finished_at = utcnow()
        emit(session, EventType.WORKFLOW, wf.id, status=wf.status)
    else:
        wf.cancel_requested = True
        emit(session, EventType.WORKFLOW, wf.id, status=wf.status, cancel_requested=True)
    return _workflow_out(session, wf)


@router.post("/workflows/{workflow_id}/retry", response_model=WorkflowOut)
def retry_workflow(workflow_id: str, session: DbSession) -> WorkflowOut:
    """Queue again; steps that already finished are kept and not run twice."""
    wf = _get(session, workflow_id)
    _require(wf, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED)
    ensure_step_rows(wf)
    for step in wf.steps:
        if step.status in (StepStatus.FAILED, StepStatus.RUNNING):
            step.status = StepStatus.PENDING
            step.progress = 0.0
            step.error = None
    _enqueue(session, wf)
    return _workflow_out(session, wf)


@router.post("/workflows/{workflow_id}/rerun", response_model=WorkflowOut)
def rerun_workflow(
    workflow_id: str,
    session: DbSession,
    from_step: Annotated[str, Query(alias="from")] = "product",
) -> WorkflowOut:
    """Run again from a step, e.g. after changing options or connecting a model.

    Earlier steps keep their results, so footage is not prepared twice.
    """
    wf = _get(session, workflow_id)
    _require(wf, WorkflowStatus.DONE, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED)
    ensure_step_rows(wf)
    names = [s.name for s in sorted(wf.steps, key=lambda s: s.position)]
    if from_step not in names:
        raise HTTPException(422, f"unknown step {from_step}")
    for step in wf.steps:
        if names.index(step.name) >= names.index(from_step):
            step.status = StepStatus.PENDING
            step.progress = 0.0
            step.error = None
            step.message = None
            step.result = None
    _enqueue(session, wf)
    return _workflow_out(session, wf)


def _enqueue(session: Session, wf: Workflow) -> None:
    wf.status = WorkflowStatus.QUEUED
    wf.queued_at = utcnow()
    wf.error = None
    wf.finished_at = None
    wf.cancel_requested = False
    if not wf.title:
        wf.title = (wf.product_text or wf.product_url)[:60]
    session.flush()
    emit(
        session,
        EventType.WORKFLOW,
        wf.id,
        status=wf.status,
        queue_position=_queue_positions(session).get(wf.id),
    )


EXPORT_NAME = re.compile(r"^variant_\d+(_silent)?\.(mp4|jpg|txt)$")


@router.get("/workflows/{workflow_id}/files/{name}")
def export_file(
    workflow_id: str,
    name: str,
    settings: AppSettings,
    download: bool = False,
) -> FileResponse:
    if not EXPORT_NAME.match(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown file")
    path = settings.exports_dir / workflow_id / name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file missing")
    filename = f"{workflow_id}_{name}" if download else None
    return FileResponse(path, filename=filename, headers={"Cache-Control": "no-cache"})


def _clip_file(session: Session, settings: Settings, clip_id: str, kind: str) -> Path:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clip not found")
    if kind == "original":
        path = settings.uploads_dir / clip.workflow_id / clip.filename
    else:
        rel = clip.thumbnail if kind == "thumbnail" else clip.proxy
        if not rel:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{kind} not ready")
        path = settings.data_dir / rel
    resolved = path.resolve()
    if not resolved.is_relative_to(settings.data_dir.resolve()) or not resolved.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file missing")
    return resolved


@router.get("/clips/{clip_id}/{kind}")
def clip_file(clip_id: str, kind: str, session: DbSession, settings: AppSettings) -> FileResponse:
    if kind not in ("thumbnail", "proxy", "original"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown file kind")
    path = _clip_file(session, settings, clip_id, kind)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
