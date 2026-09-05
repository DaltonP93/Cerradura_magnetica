"""Two-person rule for opening critical doors."""
from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal
from app.models import DoorOpenRequest, DoorOpenRequestStatus


def _make_critical(client, admin_headers, controller_with_doors):
    door = controller_with_doors["doors"][0]
    resp = client.patch(
        f"/api/v1/doors/{door['id']}",
        json={"requires_dual_approval": True},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["requires_dual_approval"] is True
    return door


def test_direct_open_rejected_for_critical_door(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    resp = client.post(f"/api/v1/doors/{door['id']}/open", headers=operator_headers)
    assert resp.status_code == 409
    # No remote_open event should have been recorded.
    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 0


def test_create_request_rejected_for_normal_door(client, operator_headers, controller_with_doors):
    door = controller_with_doors["doors"][1]  # not critical
    resp = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers)
    assert resp.status_code == 400


def test_requester_cannot_approve_own_request(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    created = client.post(
        f"/api/v1/doors/{door['id']}/open-requests",
        json={"reason": "delivery"},
        headers=operator_headers,
    )
    assert created.status_code == 201, created.text
    req = created.json()
    assert req["status"] == "pending"

    # The same operator may not approve — two-person rule.
    resp = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=operator_headers)
    assert resp.status_code == 403
    # Door must not have opened.
    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 0


def test_second_operator_approval_opens_door(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    req = client.post(
        f"/api/v1/doors/{door['id']}/open-requests",
        json={"reason": "delivery"},
        headers=operator_headers,
    ).json()

    # A different authorized operator (the admin) approves.
    resp = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "executed"
    assert body["approved_by_id"] is not None
    assert body["approved_by_id"] != body["requested_by_id"]

    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 1
    assert events["items"][0]["door_id"] == door["id"]
    assert events["items"][0]["details"]["dual_approval"] is True


def test_second_approval_after_execution_conflicts(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    req = client.post(
        f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers
    ).json()
    first = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=admin_headers)
    assert first.status_code == 200
    second = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=admin_headers)
    assert second.status_code == 409
    # Still exactly one open event.
    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 1


def test_duplicate_pending_request_rejected(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    first = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers)
    assert first.status_code == 201
    second = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers)
    assert second.status_code == 409


def test_reject_request(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    req = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers).json()
    resp = client.post(f"/api/v1/doors/open-requests/{req['id']}/reject", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    # A rejected request can no longer be approved.
    approve = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=admin_headers)
    assert approve.status_code == 409


def test_expired_request_cannot_be_approved(client, admin_headers, operator_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    req = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers).json()

    # Age the request past its window directly in the database.
    db = SessionLocal()
    try:
        row = db.get(DoorOpenRequest, req["id"])
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=admin_headers)
    assert resp.status_code == 410

    db = SessionLocal()
    try:
        row = db.get(DoorOpenRequest, req["id"])
        assert row.status == DoorOpenRequestStatus.EXPIRED
    finally:
        db.close()

    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 0


def test_viewer_cannot_request_or_approve(
    client, admin_headers, viewer_headers, operator_headers, controller_with_doors
):
    door = _make_critical(client, admin_headers, controller_with_doors)
    denied = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=viewer_headers)
    assert denied.status_code == 403

    req = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers).json()
    denied_approve = client.post(
        f"/api/v1/doors/open-requests/{req['id']}/approve", headers=viewer_headers
    )
    assert denied_approve.status_code == 403


def test_tenant_isolation_on_requests(client, admin_headers, operator_headers, admin_b_headers, controller_with_doors):
    door = _make_critical(client, admin_headers, controller_with_doors)
    req = client.post(f"/api/v1/doors/{door['id']}/open-requests", json={}, headers=operator_headers).json()
    # Org B cannot see or approve org A's request.
    resp = client.post(f"/api/v1/doors/open-requests/{req['id']}/approve", headers=admin_b_headers)
    assert resp.status_code == 404
    listing = client.get("/api/v1/doors/open-requests", headers=admin_b_headers).json()
    assert listing["total"] == 0
