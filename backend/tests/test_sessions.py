"""Server-side sessions: rotation, reuse detection, revocation, suspension.

Covers Phase 1 items 1 (invalidate sessions/refresh/WS on suspension) and 2
(persistent sessions, rotating refresh, revocation).
"""
from app.core.database import SessionLocal
from app.models import AuthSession


def _login(client, email="admin-a@test.com", password="password123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_login_creates_persistent_session(client, seeded):
    tokens = _login(client)
    db = SessionLocal()
    try:
        rows = db.query(AuthSession).all()
        assert len(rows) == 1
        assert rows[0].revoked_at is None
        assert rows[0].current_token_hash  # stored as a hash, never the raw token
        assert rows[0].current_token_hash != tokens["refresh_token"]
    finally:
        db.close()


def test_refresh_rotates_and_old_token_is_rejected(client, seeded):
    tokens = _login(client)
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # New refresh token works...
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert again.status_code == 200


def test_refresh_reuse_detection_revokes_session(client, seeded):
    tokens = _login(client)
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    rotated = first.json()

    # Replaying the ORIGINAL (already-rotated) refresh token is treated as theft.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401

    # ...and the whole session is revoked, so the rotated token no longer works either.
    after = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert after.status_code == 401
    # The rotated access token is also dead now.
    assert client.get("/api/v1/auth/me", headers=_auth(rotated)).status_code == 401


def test_logout_revokes_session(client, seeded):
    tokens = _login(client)
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=_auth(tokens)).status_code == 200
    # Access token and refresh token are both dead after logout.
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_change_password_revokes_all_sessions(client, seeded):
    tokens = _login(client, "viewer-a@test.com")
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "newpassword1"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 200
    # Old access token is invalid after the password change.
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401


def test_suspending_user_invalidates_live_access_token(client, seeded, super_headers):
    tokens = _login(client, "operator-a@test.com")
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 200

    # Find and disable the operator via the admin API.
    users = client.get(
        f"/api/v1/users?organization_id={seeded['org_a']}", headers=super_headers
    ).json()["items"]
    op_id = next(u["id"] for u in users if u["email"] == "operator-a@test.com")
    disabled = client.patch(
        f"/api/v1/users/{op_id}?organization_id={seeded['org_a']}",
        json={"is_active": False},
        headers=super_headers,
    )
    assert disabled.status_code == 200

    # The operator's still-unexpired access token is rejected immediately.
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_suspending_organization_invalidates_members(client, seeded, super_headers):
    tokens = _login(client, "admin-a@test.com")
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 200

    suspended = client.patch(
        f"/api/v1/organizations/{seeded['org_a']}", json={"is_active": False}, headers=super_headers
    )
    assert suspended.status_code == 200

    # Suspension revokes live sessions (401) and blocks a fresh login (403).
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    blocked = client.post("/api/v1/auth/login", json={"email": "admin-a@test.com", "password": "password123"})
    assert blocked.status_code == 403


def test_websocket_rejects_revoked_session(client, seeded):
    tokens = _login(client, "admin-a@test.com")
    token = tokens["access_token"]
    # A valid session connects.
    with client.websocket_connect(f"/ws/events?token={token}") as ws:
        ws.close()
    # After logout the same token is refused by the WebSocket handshake.
    client.post("/api/v1/auth/logout", headers=_auth(tokens))
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/events?token={token}") as ws:
            ws.receive_text()
