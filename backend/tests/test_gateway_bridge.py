"""Bridge-facing gateway API: registration, mTLS-fingerprint auth, claim/ack."""
import pytest

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Controller, GatewayBridge, GatewayCommandType
from app.services import gateway_outbox

HEADER = get_settings().bridge_cert_header


@pytest.fixture
def org_a_setup(seeded):
    """A controller and a registered active bridge (fingerprint 'aabbccdd') in org A."""
    db = SessionLocal()
    try:
        ctrl = Controller(organization_id=seeded["org_a"], name="Board", serial_number="900000001")
        db.add(ctrl)
        db.flush()
        bridge = GatewayBridge(
            organization_id=seeded["org_a"], name="Bridge A",
            cert_fingerprint="aabbccdd", is_active=True,
        )
        db.add(bridge)
        db.commit()
        return {"org_a": seeded["org_a"], "org_b": seeded["org_b"], "controller_id": ctrl.id}
    finally:
        db.close()


def _enqueue(org_id, controller_id, key="k-1"):
    db = SessionLocal()
    try:
        cmd = gateway_outbox.enqueue(
            db, organization_id=org_id, controller_id=controller_id,
            type=GatewayCommandType.OPEN_DOOR, idempotency_key=key, payload={"door": 1},
        )
        db.commit()
        return cmd.id
    finally:
        db.close()


# --- Admin registration ---
def test_admin_registers_bridge_and_normalizes_fingerprint(client, admin_headers):
    resp = client.post(
        "/api/v1/gateway/bridges",
        json={"name": "Sucursal Centro", "cert_fingerprint": "AA:BB:CC:DD"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cert_fingerprint"] == "aabbccdd"

    dup = client.post(
        "/api/v1/gateway/bridges",
        json={"name": "Otra", "cert_fingerprint": "aabbccdd"},
        headers=admin_headers,
    )
    assert dup.status_code == 409


def test_operator_cannot_register_bridge(client, operator_headers):
    resp = client.post(
        "/api/v1/gateway/bridges",
        json={"name": "X", "cert_fingerprint": "1234abcd"},
        headers=operator_headers,
    )
    assert resp.status_code == 403


# --- Bridge auth ---
def test_claim_requires_cert_header(client, org_a_setup):
    resp = client.post("/api/v1/gateway/commands/claim", json={"worker_token": "w1"})
    assert resp.status_code == 401


def test_claim_rejects_unknown_fingerprint(client, org_a_setup):
    resp = client.post(
        "/api/v1/gateway/commands/claim",
        json={"worker_token": "w1"},
        headers={HEADER: "deadbeef"},
    )
    assert resp.status_code == 401


# --- Claim / ack happy path ---
def test_bridge_claims_and_acks_command(client, org_a_setup):
    command_id = _enqueue(org_a_setup["org_a"], org_a_setup["controller_id"])

    claimed = client.post(
        "/api/v1/gateway/commands/claim",
        json={"worker_token": "w1", "limit": 5},
        headers={HEADER: "AA:BB:CC:DD"},  # normalizes to the registered fingerprint
    )
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert len(body) == 1
    assert body[0]["id"] == command_id
    assert body[0]["status"] == "leased"

    acked = client.post(
        f"/api/v1/gateway/commands/{command_id}/ack",
        json={"worker_token": "w1", "success": True, "result": {"opened": True}},
        headers={HEADER: "aabbccdd"},
    )
    assert acked.status_code == 200
    assert acked.json()["status"] == "succeeded"

    # Idempotent: a second ack still reports succeeded.
    again = client.post(
        f"/api/v1/gateway/commands/{command_id}/ack",
        json={"worker_token": "w1", "success": False, "error": "late"},
        headers={HEADER: "aabbccdd"},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "succeeded"


def test_ack_wrong_worker_conflicts(client, org_a_setup):
    command_id = _enqueue(org_a_setup["org_a"], org_a_setup["controller_id"])
    client.post(
        "/api/v1/gateway/commands/claim",
        json={"worker_token": "w1"}, headers={HEADER: "aabbccdd"},
    )
    resp = client.post(
        f"/api/v1/gateway/commands/{command_id}/ack",
        json={"worker_token": "intruder", "success": True},
        headers={HEADER: "aabbccdd"},
    )
    assert resp.status_code == 409


def test_bridge_cannot_touch_other_org_commands(client, org_a_setup):
    """A command in org B is invisible/unackable to org A's bridge."""
    db = SessionLocal()
    try:
        ctrl_b = Controller(organization_id=org_a_setup["org_b"], name="B", serial_number="900000002")
        db.add(ctrl_b)
        db.commit()
        ctrl_b_id = ctrl_b.id
    finally:
        db.close()
    other_command = _enqueue(org_a_setup["org_b"], ctrl_b_id, key="kb-1")

    # org A's bridge claims: sees nothing from org B.
    claimed = client.post(
        "/api/v1/gateway/commands/claim",
        json={"worker_token": "w1"}, headers={HEADER: "aabbccdd"},
    )
    assert claimed.status_code == 200
    assert claimed.json() == []

    # And cannot ack org B's command by id.
    resp = client.post(
        f"/api/v1/gateway/commands/{other_command}/ack",
        json={"worker_token": "w1", "success": True},
        headers={HEADER: "aabbccdd"},
    )
    assert resp.status_code == 404
