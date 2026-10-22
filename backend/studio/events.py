from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.models import Event


class EventType:
    WORKFLOW = "workflow"
    STEP = "step"
    LOG = "log"


def emit(session: Session, type_: str, workflow_id: str | None = None, **payload: Any) -> Event:
    ev = Event(workflow_id=workflow_id, type=type_, payload=payload)
    session.add(ev)
    session.flush()
    return ev


def events_after(session: Session, after_id: int, limit: int = 500) -> list[Event]:
    stmt = select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)
    return list(session.scalars(stmt))


def last_event_id(session: Session) -> int:
    ev = session.scalars(select(Event).order_by(Event.id.desc()).limit(1)).first()
    return ev.id if ev else 0
