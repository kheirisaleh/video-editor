import asyncio
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from studio.db import session_scope
from studio.events import events_after, last_event_id

router = APIRouter(prefix="/api")

POLL_SECONDS = 0.4


def _load(after_id: int) -> list[dict]:
    with session_scope() as s:
        return [
            {
                "id": ev.id,
                "type": ev.type,
                "workflow_id": ev.workflow_id,
                "payload": ev.payload,
                "at": ev.created_at.isoformat() if isinstance(ev.created_at, datetime) else None,
            }
            for ev in events_after(s, after_id)
        ]


def _last() -> int:
    with session_scope() as s:
        return last_event_id(s)


@router.websocket("/live")
async def live(ws: WebSocket) -> None:
    """Stream events to the browser.

    The worker runs in another process and writes events into the database, so this
    endpoint tails the events table. Clients pass `after` to resume without gaps after
    a reconnect.
    """
    await ws.accept()
    after_param = ws.query_params.get("after")
    cursor = (
        int(after_param)
        if after_param and after_param.isdigit()
        else await run_in_threadpool(_last)
    )
    await ws.send_json({"type": "hello", "id": cursor})
    try:
        while True:
            batch = await run_in_threadpool(_load, cursor)
            for item in batch:
                await ws.send_json(item)
                cursor = item["id"]
            if not batch:
                await asyncio.sleep(POLL_SECONDS)
    except (WebSocketDisconnect, RuntimeError):
        return
