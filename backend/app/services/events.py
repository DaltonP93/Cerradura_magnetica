"""Event recording and real-time fan-out to WebSocket subscribers."""
import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models import Event, EventType

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class Connection:
    """A live monitor socket plus the identity used to revoke it."""

    websocket: WebSocket
    org_id: int
    user_id: int
    session_id: str
    loop: asyncio.AbstractEventLoop
    close_event: asyncio.Event = field(default_factory=asyncio.Event)

    def signal_close(self) -> None:
        """Ask the socket's own loop to close it (safe from any thread)."""
        self.loop.call_soon_threadsafe(self.close_event.set)


class ConnectionManager:
    """Tracks WebSocket subscribers per organization and broadcasts events.

    Revocation may be triggered from synchronous request handlers running in a
    worker thread, so the registry is guarded by a plain threading.Lock and the
    close methods only *signal* each connection's event via
    ``loop.call_soon_threadsafe`` — the socket is actually closed on its own
    event loop by the WebSocket handler.
    """

    def __init__(self) -> None:
        self._by_org: dict[int, set[Connection]] = {}
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket, *, org_id: int, user_id: int, session_id: str) -> Connection:
        await websocket.accept()
        conn = Connection(
            websocket=websocket,
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            loop=asyncio.get_running_loop(),
        )
        with self._lock:
            self._by_org.setdefault(org_id, set()).add(conn)
        return conn

    def _remove(self, conn: Connection) -> None:
        with self._lock:
            conns = self._by_org.get(conn.org_id)
            if conns:
                conns.discard(conn)
                if not conns:
                    self._by_org.pop(conn.org_id, None)

    async def disconnect(self, conn: Connection) -> None:
        self._remove(conn)

    def _snapshot(self, org_id: int | None = None) -> list[Connection]:
        with self._lock:
            if org_id is not None:
                return list(self._by_org.get(org_id, ()))
            return [c for conns in self._by_org.values() for c in conns]

    # --- revocation signals (safe to call from sync worker threads) --------

    def close_session(self, session_id: str) -> int:
        matched = [c for c in self._snapshot() if c.session_id == session_id]
        for c in matched:
            c.signal_close()
        return len(matched)

    def close_user(self, user_id: int) -> int:
        matched = [c for c in self._snapshot() if c.user_id == user_id]
        for c in matched:
            c.signal_close()
        return len(matched)

    def close_org(self, org_id: int) -> int:
        matched = self._snapshot(org_id)
        for c in matched:
            c.signal_close()
        return len(matched)

    async def broadcast(self, org_id: int, payload: dict) -> None:
        message = json.dumps(payload, default=str)
        for conn in self._snapshot(org_id):
            try:
                await conn.websocket.send_text(message)
            except Exception:  # noqa: BLE001 - a dead socket must not break the loop
                self._remove(conn)


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
