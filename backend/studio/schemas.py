from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from studio.models import StepStatus, WorkflowStatus


class WorkflowCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    product_text: str = Field(default="", max_length=20_000)
    product_url: HttpUrl | None = None
    prompt: str = Field(default="", max_length=5_000)


class WorkflowUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    product_text: str | None = Field(default=None, max_length=20_000)
    product_url: HttpUrl | None = None
    prompt: str | None = Field(default=None, max_length=5_000)


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    original_name: str
    size_bytes: int
    probe: dict[str, Any] | None
    thumbnail_url: str | None
    proxy_url: str | None
    original_url: str


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: StepStatus
    progress: float
    message: str | None
    error: str | None
    result: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None


class WorkflowSummary(BaseModel):
    id: str
    title: str
    status: WorkflowStatus
    current_step: str | None
    progress: float
    error: str | None
    clip_count: int
    thumbnail_url: str | None
    queue_position: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class OutputOut(BaseModel):
    index: int
    label: str
    duration: float
    video_url: str
    silent_url: str | None
    cover_url: str
    caption: str
    music: str | None
    size_bytes: int


class WorkflowOut(WorkflowSummary):
    product_text: str
    product_url: str
    prompt: str
    clips: list[ClipOut]
    steps: list[StepOut]
    outputs: list[OutputOut]


class Health(BaseModel):
    ok: bool
    ffmpeg: bool
    version: str
    queued: int
    running: int
