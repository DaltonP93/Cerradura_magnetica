"""Live event stream for the monitoring screen."""
import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models import User, UserRole
from app.services.events import manager

router = APIRouter(tags=["monitoring"])


@router.websocket("/ws/events")
async def events_ws(
    websocket: WebSocket,
    token: str = Query(...),
    organization_id: int | None = Query(default=None),
):
    try:
        payload = decode_token(token, "access")
    except pyjwt.InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db = SessionLocal()
    try:
        user = db.get(User, int(payload["sub"]))
    finally:
        db.close()
    if user is None or not user.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if user.role == UserRole.SUPER_ADMIN:
        org_id = organization_id or user.organization_id
    else:
        org_id = user.organization_id
    if org_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(org_id, websocket)
    try:
        while True:
            # Keep the connection alive; clients may send pings, content is ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(org_id, websocket)
