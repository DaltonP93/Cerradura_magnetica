"""Automatic card revocation to the bridge outbox.

Deactivating or deleting a credential must reach the offline board caches, not
just the DB row. In ``bridge`` dispatch that means a ``REVOKE_CARD`` command is
enqueued for every controller in the organization; in ``direct`` dispatch the
online access engine already denies the card, so nothing is queued.
"""
import pytest

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_token
from app.models import GatewayBridge, GatewayCommand, GatewayCommandType


@pytest.fixture
def bridge_mode():
    settings = get_settings()
    original = settings.command_dispatch
    settings.command_dispatch = "bridge"
    yield
    settings.command_dispatch = original


def _controller(client, headers, serial):
    resp = client.post(
        "/api/v1/controllers",
        json={"name": f"Board {serial}", "serial_number": serial},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _holder_with_card(client, headers, card):
    holder = client.post(
        "/api/v1/cardholders",
        json={"first_name": "Lost", "last_name": "Card"},
        headers=headers,
    )
    assert holder.status_code == 201, holder.text
    hid = holder.json()["id"]
    cred = client.post(
        f"/api/v1/cardholders/{hid}/credentials",
        json={"card_number": card},
        headers=headers,
    )
    assert cred.status_code == 201, cred.text
    return hid, cred.json()["id"]


def _revoke_commands(org_id=None):
    db = SessionLocal()
    try:
        q = db.query(GatewayCommand).filter_by(type=GatewayCommandType.REVOKE_CARD)
        if org_id is not None:
            q = q.filter_by(organization_id=org_id)
        return q.all()
    finally:
        db.close()


def test_deactivating_card_enqueues_revoke_per_controller(client, admin_headers, seeded, bridge_mode):
    _controller(client, admin_headers, "900100001")
    _controller(client, admin_headers, "900100002")
    hid, cid = _holder_with_card(client, admin_headers, "55551234")

    resp = client.patch(
        f"/api/v1/cardholders/{hid}/credentials/{cid}",
        json={"is_active": False}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    cmds = _revoke_commands(seeded["org_a"])
    assert len(cmds) == 2  # one per controller in the org
    assert {c.controller_id for c in cmds}  # each bound to a controller
    assert all(c.payload == {"card_number": "55551234"} for c in cmds)


def test_deleting_card_enqueues_revoke(client, admin_headers, seeded, bridge_mode):
    _controller(client, admin_headers, "900100003")
    hid, cid = _holder_with_card(client, admin_headers, "55555678")

    resp = client.delete(
        f"/api/v1/cardholders/{hid}/credentials/{cid}", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    cmds = _revoke_commands(seeded["org_a"])
    assert len(cmds) == 1
    assert cmds[0].payload == {"card_number": "55555678"}


def test_reactivation_or_noop_update_does_not_enqueue(client, admin_headers, seeded, bridge_mode):
    _controller(client, admin_headers, "900100004")
    hid, cid = _holder_with_card(client, admin_headers, "55559999")
    # A PIN-only update (card stays active) must not queue a revocation.
    client.patch(
        f"/api/v1/cardholders/{hid}/credentials/{cid}",
        json={"pin": "4321"}, headers=admin_headers,
    )
    assert _revoke_commands(seeded["org_a"]) == []


def test_direct_mode_does_not_enqueue(client, admin_headers, seeded):
    """Default (direct) dispatch: the access engine denies online, no outbox."""
    assert get_settings().command_dispatch == "direct"
    _controller(client, admin_headers, "900100005")
    hid, cid = _holder_with_card(client, admin_headers, "55550000")
    client.patch(
        f"/api/v1/cardholders/{hid}/credentials/{cid}",
        json={"is_active": False}, headers=admin_headers,
    )
    assert _revoke_commands() == []


def test_revocation_is_tenant_scoped(client, admin_headers, admin_b_headers, seeded, bridge_mode):
    """Org A's revocation must not target Org B's controllers."""
    _controller(client, admin_headers, "900100006")            # org A
    _controller(client, admin_b_headers, "900100007")          # org B
    hid, cid = _holder_with_card(client, admin_headers, "55551111")

    client.patch(
        f"/api/v1/cardholders/{hid}/credentials/{cid}",
        json={"is_active": False}, headers=admin_headers,
    )
    a_cmds = _revoke_commands(seeded["org_a"])
    b_cmds = _revoke_commands(seeded["org_b"])
    assert len(a_cmds) == 1
    assert b_cmds == []


def test_bridge_can_claim_and_ack_revoke_command(client, admin_headers, seeded, bridge_mode):
    """The queued REVOKE_CARD is claimable/ackable by the org's bridge and its
    ack carries no spurious platform effect."""
    _controller(client, admin_headers, "900100008")
    hid, cid = _holder_with_card(client, admin_headers, "55552222")
    client.patch(
        f"/api/v1/cardholders/{hid}/credentials/{cid}",
        json={"is_active": False}, headers=admin_headers,
    )
    # Register the org's bridge. F-4: authentication requires the mTLS
    # fingerprint AND a per-bridge shared secret (stored only as a hash); a
    # bridge without a secret_hash is fail-closed and cannot authenticate.
    bridge_secret = "revoke-test-secret-xyz789"
    db = SessionLocal()
    try:
        db.add(GatewayBridge(
            organization_id=seeded["org_a"], name="Bridge", cert_fingerprint="ffee0011",
            secret_hash=hash_token(bridge_secret), is_active=True,
        ))
        db.commit()
    finally:
        db.close()
    settings = get_settings()
    headers = {
        settings.bridge_cert_header: "ffee0011",
        settings.bridge_secret_header: bridge_secret,
    }
    client.cookies.clear()
    claimed = client.post(
        "/api/v1/gateway/commands/claim", json={"worker_token": "w1"}, headers=headers
    )
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert len(body) == 1
    assert body[0]["type"] == "revoke_card"
    cmd_id = body[0]["id"]
    acked = client.post(
        f"/api/v1/gateway/commands/{cmd_id}/ack",
        json={"worker_token": "w1", "success": True}, headers=headers,
    )
    assert acked.status_code == 200
    assert acked.json()["status"] == "succeeded"
