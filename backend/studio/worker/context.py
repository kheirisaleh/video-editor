import logging
import time
from pathlib import Path
from typing import Any

from studio.config import Settings
from studio.db import session_scope
from studio.events import EventType, emit
from studio.media.ffmpeg import Cancelled
from studio.models import StepRun, Workflow

log = logging.getLogger(__name__)


class StepContext:
    """What a pipeline step gets to work with: paths, progress reporting and cancellation."""

    PROGRESS_INTERVAL = 0.5
    CANCEL_INTERVAL = 0.5

    def __init__(self, settings: Settings, workflow_id: str, step_name: str) -> None:
        self.settings = settings
        self.workflow_id = workflow_id
        self.step_name = step_name
        self._last_progress_at = 0.0
        self._last_progress = -1.0
        self._last_cancel_check = 0.0
        self._cancelled = False

    @property
    def upload_dir(self) -> Path:
        return self.settings.uploads_dir / self.workflow_id

    @property
    def work_dir(self) -> Path:
        path = self.settings.work_dir / self.workflow_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def export_dir(self) -> Path:
        path = self.settings.exports_dir / self.workflow_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def relative(self, path: Path) -> str:
        return path.relative_to(self.settings.data_dir).as_posix()

    def progress(self, fraction: float, message: str | None = None, force: bool = False) -> None:
        fraction = max(0.0, min(fraction, 1.0))
        now = time.monotonic()
        if not force and message is None:
            if now - self._last_progress_at < self.PROGRESS_INTERVAL:
                return
            if abs(fraction - self._last_progress) < 0.01:
                return
        self._last_progress_at = now
        self._last_progress = fraction
        with session_scope() as s:
            step = (
                s.query(StepRun).filter_by(workflow_id=self.workflow_id, name=self.step_name).one()
            )
            step.progress = fraction
            if message is not None:
                step.message = message
            payload: dict[str, Any] = {"name": self.step_name, "progress": round(fraction, 4)}
            if message is not None:
                payload["message"] = message
            emit(s, EventType.STEP, self.workflow_id, **payload)

    def log(self, message: str, level: str = "info") -> None:
        log.info("[%s/%s] %s", self.workflow_id, self.step_name, message)
        with session_scope() as s:
            emit(
                s,
                EventType.LOG,
                self.workflow_id,
                step=self.step_name,
                level=level,
                message=message,
            )

    def should_cancel(self) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if now - self._last_cancel_check < self.CANCEL_INTERVAL:
            return False
        self._last_cancel_check = now
        with session_scope() as s:
            wf = s.get(Workflow, self.workflow_id)
            self._cancelled = wf is None or wf.cancel_requested
        return self._cancelled

    def check_cancel(self) -> None:
        self._last_cancel_check = 0.0
        if self.should_cancel():
            raise Cancelled()
