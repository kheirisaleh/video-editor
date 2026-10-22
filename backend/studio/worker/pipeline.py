import logging
import traceback

from sqlalchemy import update

from studio.config import Settings
from studio.db import session_scope
from studio.events import EventType, emit
from studio.media.ffmpeg import Cancelled
from studio.models import StepRun, StepStatus, Workflow, WorkflowStatus, utcnow
from studio.worker.context import StepContext
from studio.worker.steps import Step, StepError
from studio.worker.steps.ingest import IngestStep

log = logging.getLogger(__name__)

STEPS: list[Step] = [IngestStep()]


def step_names() -> list[str]:
    return [s.name for s in STEPS]


def ensure_step_rows(workflow: Workflow) -> None:
    existing = {s.name for s in workflow.steps}
    for position, name in enumerate(step_names()):
        if name not in existing:
            workflow.steps.append(StepRun(name=name, position=position))


def recover_interrupted() -> int:
    """Put workflows that were running when the worker died back into the queue."""
    with session_scope() as s:
        running = s.query(Workflow).filter_by(status=WorkflowStatus.RUNNING).all()
        for wf in running:
            wf.status = WorkflowStatus.QUEUED
            for step in wf.steps:
                if step.status == StepStatus.RUNNING:
                    step.status = StepStatus.PENDING
                    step.progress = 0.0
            emit(s, EventType.WORKFLOW, wf.id, status=wf.status, reason="worker restarted")
        return len(running)


def claim_next() -> str | None:
    with session_scope() as s:
        wf = (
            s.query(Workflow)
            .filter_by(status=WorkflowStatus.QUEUED)
            .order_by(Workflow.queued_at, Workflow.created_at)
            .first()
        )
        if wf is None:
            return None
        claimed = s.execute(
            update(Workflow)
            .where(Workflow.id == wf.id, Workflow.status == WorkflowStatus.QUEUED)
            .values(status=WorkflowStatus.RUNNING, started_at=utcnow(), error=None)
        ).rowcount
        if not claimed:
            return None
        emit(s, EventType.WORKFLOW, wf.id, status=WorkflowStatus.RUNNING)
        return wf.id


def run_workflow(settings: Settings, workflow_id: str) -> WorkflowStatus:
    with session_scope() as s:
        wf = s.get(Workflow, workflow_id)
        if wf is None:
            return WorkflowStatus.FAILED
        ensure_step_rows(wf)

    for step in STEPS:
        with session_scope() as s:
            row = s.query(StepRun).filter_by(workflow_id=workflow_id, name=step.name).one()
            if row.status in (StepStatus.DONE, StepStatus.SKIPPED):
                continue
            row.status = StepStatus.RUNNING
            row.progress = 0.0
            row.error = None
            row.message = None
            row.started_at = utcnow()
            row.finished_at = None
            s.get(Workflow, workflow_id).current_step = step.name  # type: ignore[union-attr]
            emit(
                s,
                EventType.STEP,
                workflow_id,
                name=step.name,
                status=StepStatus.RUNNING,
                progress=0.0,
            )

        ctx = StepContext(settings, workflow_id, step.name)
        try:
            ctx.check_cancel()
            result = step.run(ctx)
        except Cancelled:
            return _finish(workflow_id, step.name, WorkflowStatus.CANCELLED, StepStatus.PENDING)
        except StepError as exc:
            return _finish(
                workflow_id, step.name, WorkflowStatus.FAILED, StepStatus.FAILED, str(exc)
            )
        except Exception as exc:
            log.exception("step %s failed for %s", step.name, workflow_id)
            detail = "".join(traceback.format_exception_only(exc)).strip()
            return _finish(
                workflow_id,
                step.name,
                WorkflowStatus.FAILED,
                StepStatus.FAILED,
                f"internal error: {detail}",
            )

        with session_scope() as s:
            row = s.query(StepRun).filter_by(workflow_id=workflow_id, name=step.name).one()
            row.status = StepStatus.DONE
            row.progress = 1.0
            row.result = result
            row.message = None
            row.finished_at = utcnow()
            emit(
                s,
                EventType.STEP,
                workflow_id,
                name=step.name,
                status=StepStatus.DONE,
                progress=1.0,
                result=result,
            )

    return _finish(workflow_id, None, WorkflowStatus.DONE, None)


def _finish(
    workflow_id: str,
    step_name: str | None,
    status: WorkflowStatus,
    step_status: StepStatus | None,
    error: str | None = None,
) -> WorkflowStatus:
    with session_scope() as s:
        wf = s.get(Workflow, workflow_id)
        if wf is None:
            return status
        if step_name and step_status:
            row = s.query(StepRun).filter_by(workflow_id=workflow_id, name=step_name).one()
            row.status = step_status
            row.error = error
            row.finished_at = utcnow()
            if step_status == StepStatus.PENDING:
                row.progress = 0.0
            emit(
                s,
                EventType.STEP,
                workflow_id,
                name=step_name,
                status=step_status,
                error=error,
                progress=row.progress,
            )
        wf.status = status
        wf.error = error
        wf.finished_at = utcnow()
        wf.current_step = None
        wf.cancel_requested = False
        emit(s, EventType.WORKFLOW, workflow_id, status=status, error=error)
    return status
