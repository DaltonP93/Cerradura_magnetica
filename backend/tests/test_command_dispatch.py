"""ACP_COMMAND_DISPATCH=bridge routes controller/door commands to the outbox."""
import pytest

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Controller, ControllerStatus, GatewayCommand, GatewayCommandType


@pytest.fixture
def bridge_mode():
    """Flip the process into bridge dispatch for the duration of a test."""
    settings = get_settings()
    original = settings.command_dispatch
    settings.command_dispatch = "bridge"
    try:
        yield
    finally:
        settings.command_dispatch = original


def _commands(type_: GatewayCommandType) -> list[GatewayCommand]:
    db = SessionLocal()
    try:
        return db.query(GatewayCommand).filter_by(type=type_).all()
    finally:
        db.close()


def test_open_door_enqueues_in_bridge_mode(client, operator_headers, admin_headers, controller_with_doors, bridge_mode):
    door = controller_with_doors["doors"][0]
    resp = client.post(f"/api/v1/doors/{door['id']}/open", headers=operator_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "queued" in resp.json()["message"].lower()

    # A command was queued and NO physical-open event was recorded.
    cmds = _commands(GatewayCommandType.OPEN_DOOR)
    assert len(cmds) == 1
    assert cmds[0].payload["door"] == door["number"]
    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 0


def test_ping_enqueues_and_leaves_status_untouched_in_bridge_mode(
    client, operator_headers, controller_with_doors, bridge_mode
):
    cid = controller_with_doors["id"]
    resp = client.post(f"/api/v1/controllers/{cid}/ping", headers=operator_headers)
    assert resp.status_code == 200
    assert len(_commands(GatewayCommandType.PING)) == 1

    db = SessionLocal()
    try:
        assert db.get(Controller, cid).status == ControllerStatus.UNKNOWN  # not flipped online
    finally:
        db.close()


def test_sync_permissions_enqueues_serializable_payload_in_bridge_mode(
    client, operator_headers, controller_with_doors, bridge_mode
):
    cid = controller_with_doors["id"]
    resp = client.post(f"/api/v1/controllers/{cid}/sync-permissions", headers=operator_headers)
    assert resp.status_code == 200
    cmds = _commands(GatewayCommandType.SYNC_PERMISSIONS)
    assert len(cmds) == 1
    assert "cards" in cmds[0].payload  # JSON-serializable payload stored


def test_direct_mode_still_opens_without_enqueue(client, operator_headers, admin_headers, controller_with_doors):
    """Default (direct) dispatch keeps the synchronous behaviour and events."""
    door = controller_with_doors["doors"][0]
    resp = client.post(f"/api/v1/doors/{door['id']}/open", headers=operator_headers)
    assert resp.status_code == 200 and resp.json()["success"] is True
    assert _commands(GatewayCommandType.OPEN_DOOR) == []  # nothing queued
    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 1  # opened synchronously and recorded
