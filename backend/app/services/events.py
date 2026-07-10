"""Event recording and real-time fan-out to WebSocket subscribers."""
import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models import Event, EventType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket subscribers per organization and broadcasts events."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, org_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(org_id, set()).add(websocket)

    async def disconnect(self, org_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(org_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._connections.pop(org_id, None)

    async def broadcast(self, org_id: int, payload: dict) -> None:
        message = json.dumps(payload, default=str)
        async with self._lock:
            targets = list(self._connections.get(org_id, ()))
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 - a dead socket must not break the loop
                await self.disconnect(org_id, ws)


manager = ConnectionManager()

# Main event loop, captured at app startup. Sync endpoints run in worker
# threads where get_running_loop() fails, so broadcasts are handed to this
# loop via run_coroutine_threadsafe.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _event_payload(event: Event) -> dict:
    return {
        "kind": "event",
        "id": event.id,
        "type": event.type.value,
        "organization_id": event.organization_id,
        "controller_id": event.controller_id,
        "door_id": event.door_id,
        "cardholder_id": event.cardholder_id,
        "credential_id": event.credential_id,
        "message": event.message,
        "details": event.details,
        "occurred_at": event.occurred_at.isoformat() if isinstance(event.occurred_at, datetime) else event.occurred_at,
    }


def record_event(
    db: Session,
    *,
    organization_id: int,
    type: EventType,
    message: str,
    controller_id: int | None = None,
    door_id: int | None = None,
    cardholder_id: int | None = None,
    credential_id: int | None = None,
    details: dict | None = None,
) -> Event:
    """Persist an event and schedule its broadcast to live monitors."""
    event = Event(
        organization_id=organization_id,
        type=type,
        message=message,
        controller_id=controller_id,
        door_id=door_id,
        cardholder_id=cardholder_id,
        credential_id=credential_id,
        details=details,
    )
    db.add(event)
    db.flush()

    payload = _event_payload(event)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast(organization_id, payload))
    except RuntimeError:
        # Worker thread (sync endpoint): hand the broadcast to the main loop.
        if _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(organization_id, payload), _main_loop)
        else:
            logger.debug("No event loop available; skipping websocket broadcast")
    return event
