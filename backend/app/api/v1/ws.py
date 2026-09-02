"""Live event stream for the monitoring screen.

The handshake authenticates the socket, and the connection is then held open
only while its session stays valid. Two mechanisms close an already-open
socket: an immediate in-process signal (``Connection.close_event``, fired by
logout / suspension / reuse detection) and a periodic revalidation against the
database that also catches revocations made in another worker or process.

Multi-worker note: the immediate signal only reaches sockets served by the same
process. A multi-worker deployment needs Redis Pub/Sub (or an equivalent bus)
to fan revocations out to every worker; the periodic revalidation bounds the
staleness in the meantime.
"""
import asyncio
import contextlib

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models import User, UserRole
from app.services.events import manager
from app.services.sessions import get_active_session, organization_active, session_is_live

router = APIRouter(tags=["monitoring"])
settings = get_settings()


def _authenticate(token: str, requested_org: int | None) -> tuple[int, str, int] | None:
    """Return (user_id, session_id, org_id) if the token grants a live session."""
    try:
        payload = decode_token(token, "access")
    except pyjwt.InvalidTokenError:
        return None
    session_id = payload.get("sid")
    if not session_id:
        return None
    db = SessionLocal()
    try:
        if get_active_session(db, session_id) is None:
            return None
        user = db.get(User, int(payload["sub"]))
        if user is None or not user.is_active or not organization_active(db, user):
            return None
        # Super admins may watch a chosen organization; everyone else is locked
        # to their own.
        if user.role == UserRole.SUPER_ADMIN:
            org_id = requested_org or user.organization_id
        else:
            org_id = user.organization_id
        return (user.id, session_id, org_id) if org_id is not None else None
    finally:
        db.close()


def _still_live(session_id: str) -> bool:
    db = SessionLocal()
    try:
        return session_is_live(db, session_id)
    finally:
        db.close()


@router.websocket("/ws/events")
async def events_ws(
    websocket: WebSocket,
    token: str = Query(...),
    organization_id: int | None = Query(default=None),
):
    identity = _authenticate(token, organization_id)
    if identity is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    user_id, session_id, org_id = identity

    conn = await manager.connect(websocket, org_id=org_id, user_id=user_id, session_id=session_id)
    try:
        while True:
            receive_task = asyncio.ensure_future(websocket.receive_text())
            close_task = asyncio.ensure_future(conn.close_event.wait())
            done, pending = await asyncio.wait(
                {receive_task, close_task},
                timeout=settings.ws_revalidate_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

            if conn.close_event.is_set():
                break  # revoked in-process (logout / suspension / reuse)
            if receive_task in done:
                if receive_task.exception() is not None:
                    break  # client disconnected
                continue  # client sent a ping/keepalive; ignore content
            # Timed out: revalidate against the database (cross-process safety net).
            if not _still_live(session_id):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(conn)
        with contextlib.suppress(Exception):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
