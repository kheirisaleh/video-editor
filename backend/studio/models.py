import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from studio.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class WorkflowStatus(enum.StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="")
    product_text: Mapped[str] = mapped_column(Text, default="")
    product_url: Mapped[str] = mapped_column(String(2000), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(String(16), default=WorkflowStatus.DRAFT)
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    clips: Mapped[list["Clip"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", order_by="Clip.position"
    )
    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", order_by="StepRun.position"
    )


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(default=0)
    original_name: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(default=0)
    probe: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    thumbnail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    proxy: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="clips")


class StepRun(Base):
    __tablename__ = "step_runs"
    __table_args__ = (UniqueConstraint("workflow_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(default=0)
    status: Mapped[StepStatus] = mapped_column(String(16), default=StepStatus.PENDING)
    progress: Mapped[float] = mapped_column(default=0.0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    workflow: Mapped[Workflow] = relationship(back_populates="steps")


class Event(Base):
    """Append only log of everything that happens, streamed to the UI over WebSocket."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
