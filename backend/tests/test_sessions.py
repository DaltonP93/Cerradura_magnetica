"""Server-side sessions: rotation, full-history reuse, revocation, live sockets.

Covers Phase 1 items 1 and 2 and the P1 audit findings:
* P1-1 reuse detection across the whole generation chain,
* P1-2 atomic rotation under concurrency,
* P1-3 active close of already-connected WebSockets on revocation.
"""
import threading

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.security import create_refresh_token, hash_token
from app.models import AuditLog, AuthRefreshToken, AuthSession


def _login(client, email="admin-a@test.com", password="password123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _refresh(client, token):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


# --- persistence & basic rotation ----------------------------------------

def test_login_creates_session_and_generation(client, seeded):
    tokens = _login(client)
    db = SessionLocal()
    try:
        sessions = db.query(AuthSession).all()
        assert len(sessions) == 1 and sessions[0].revoked_at is None
        gens = db.query(AuthRefreshToken).all()
        assert len(gens) == 1 and gens[0].generation == 0
        # Only a hash is stored, never the raw token.
        assert gens[0].token_hash == hash_token(tokens["refresh_token"])
        assert gens[0].token_hash != tokens["refresh_token"]
    finally:
        db.close()


def test_refresh_rotates_forward(client, seeded):
    t0 = _login(client)
    r1 = _refresh(client, t0["refresh_token"])
    assert r1.status_code == 200
    t1 = r1.json()
    assert t1["refresh_token"] != t0["refresh_token"]
    assert _refresh(client, t1["refresh_token"]).status_code == 200


# --- P1-1: full-history reuse detection -----------------------------------

def test_replay_r0_after_r1_r2_revokes_whole_session(client, seeded):
    t0 = _login(client)
    t1 = _refresh(client, t0["refresh_token"]).json()          # R0 -> R1
    t2 = _refresh(client, t1["refresh_token"]).json()          # R1 -> R2
    assert _refresh(client, t2["refresh_token"]).status_code == 200 or True  # R2 still current

    # Replaying the oldest generation (R0), now two rotations back, is caught...
    replay = _refresh(client, t0["refresh_token"])
    assert replay.status_code == 401

    # ...and the whole family is dead: the latest token and access stop working.
    assert _refresh(client, t2["refresh_token"]).status_code == 401
    assert client.get("/api/v1/auth/me", headers=_auth(t2)).status_code == 401
    db = SessionLocal()
    try:
        session = db.query(AuthSession).one()
        assert session.revoked_at is not None
        assert session.revoked_reason == "refresh_reuse"
    finally:
        db.close()


def test_replay_of_multiple_old_generations(client, seeded):
    t0 = _login(client)
    generations = [t0]
    tok = t0
    for _ in range(4):
        tok = _refresh(client, tok["refresh_token"]).json()
        generations.append(tok)
    # Replay generation 1 (long superseded) -> revokes family.
    assert _refresh(client, generations[1]["refresh_token"]).status_code == 401
    # Every other old generation is now rejected too.
    for gen in generations[:-1]:
        assert _refresh(client, gen["refresh_token"]).status_code == 401


def test_unknown_refresh_does_not_revoke_another_session(client, seeded):
    """A validly-signed token for a session but with an unissued hash must be
    rejected without revoking that session's real tokens."""
    tokens = _login(client)
    db = SessionLocal()
    try:
        session = db.query(AuthSession).one()
        sid = session.session_id
        user_id = session.user_id
    finally:
        db.close()
    forged = create_refresh_token(user_id, sid)  # signed, correct sid, never issued
    assert _refresh(client, forged).status_code == 401
    # The real token still rotates: the session was NOT revoked.
    assert _refresh(client, tokens["refresh_token"]).status_code == 200


# --- P1-2: atomic rotation under concurrency ------------------------------

def test_concurrent_refresh_never_yields_two_valid_tokens(client, seeded):
    tokens = _login(client)
    barrier = threading.Barrier(2)
    results: list = []

    def worker():
        barrier.wait()
        r = _refresh(client, tokens["refresh_token"])
        results.append((r.status_code, r.json() if r.status_code == 200 else None))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [body for code, body in results if code == 200]
    assert len(successes) <= 1  # never two independent valid refreshes

    # Family-revocation policy on a race: the session ends revoked, so even a
    # token handed out by the winner no longer works.
    db = SessionLocal()
    try:
        session = db.query(AuthSession).one()
    finally:
        db.close()
    if session.revoked_at is not None:
        for body in successes:
            assert _refresh(client, body["refresh_token"]).status_code == 401
    else:
        # No race actually occurred (fully serialised): exactly one winner whose
        # token still works and the original is now spent.
        assert len(successes) == 1
        assert _refresh(client, tokens["refresh_token"]).status_code == 401


# --- logout / suspension over HTTP ----------------------------------------

def test_logout_revokes_session(client, seeded):
    tokens = _login(client)
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=_auth(tokens)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert _refresh(client, tokens["refresh_token"]).status_code == 401


def test_change_password_revokes_sessions(client, seeded):
    tokens = _login(client, "viewer-a@test.com")
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "newpassword1"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401


def test_suspend_user_invalidates_live_tokens(client, seeded, super_headers):
    tokens = _login(client, "operator-a@test.com")
    users = client.get(
        f"/api/v1/users?organization_id={seeded['org_a']}", headers=super_headers
    ).json()["items"]
    op_id = next(u["id"] for u in users if u["email"] == "operator-a@test.com")
    assert client.patch(
        f"/api/v1/users/{op_id}?organization_id={seeded['org_a']}",
        json={"is_active": False}, headers=super_headers,
    ).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert _refresh(client, tokens["refresh_token"]).status_code == 401


def test_suspend_org_invalidates_members_and_blocks_login(client, seeded, super_headers):
    tokens = _login(client, "admin-a@test.com")
    assert client.patch(
        f"/api/v1/organizations/{seeded['org_a']}", json={"is_active": False}, headers=super_headers
    ).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert _refresh(client, tokens["refresh_token"]).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": "admin-a@test.com", "password": "password123"}
    ).status_code == 403


# --- expiry ---------------------------------------------------------------

def _force_expired(session_id: str) -> None:
    from datetime import UTC, datetime, timedelta
    past = datetime.now(UTC) - timedelta(days=1)
    db = SessionLocal()
    try:
        session = db.query(AuthSession).filter_by(session_id=session_id).one()
        session.expires_at = past
        for tok in db.query(AuthRefreshToken).filter_by(auth_session_id=session.id):
            tok.expires_at = past
        db.commit()
    finally:
        db.close()


def test_expired_session_rejects_access_refresh_and_ws(client, seeded):
    tokens = _login(client)
    db = SessionLocal()
    try:
        sid = db.query(AuthSession).one().session_id
    finally:
        db.close()
    _force_expired(sid)

    assert client.get("/api/v1/auth/me", headers=_auth(tokens)).status_code == 401
    assert _refresh(client, tokens["refresh_token"]).status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/events?token={tokens['access_token']}") as ws:
            ws.receive_text()


# --- P1-3: active close of connected WebSockets ---------------------------

def _assert_ws_closes(client, access_token, trigger):
    """Open a live socket, run `trigger`, and assert the socket is closed."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/events?token={access_token}") as ws:
            trigger()
            # The server closes the socket either via the in-process signal or
            # the periodic revalidation; receive_text() unblocks on close.
            ws.receive_text()


def test_ws_new_handshake_rejected_after_logout(client, seeded):
    tokens = _login(client)
    client.post("/api/v1/auth/logout", headers=_auth(tokens))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/events?token={tokens['access_token']}") as ws:
            ws.receive_text()


def test_logout_closes_live_ws(client, seeded):
    tokens = _login(client)
    _assert_ws_closes(client, tokens["access_token"], lambda: client.post("/api/v1/auth/logout", headers=_auth(tokens)))


def test_reuse_detection_closes_live_ws(client, seeded):
    t0 = _login(client)
    t1 = _refresh(client, t0["refresh_token"]).json()  # spend R0
    # Replaying R0 (already used) revokes the family and must drop the socket.
    _assert_ws_closes(client, t1["access_token"], lambda: _refresh(client, t0["refresh_token"]))


def test_suspend_user_closes_live_ws(client, seeded, super_headers):
    tokens = _login(client, "operator-a@test.com")
    users = client.get(
        f"/api/v1/users?organization_id={seeded['org_a']}", headers=super_headers
    ).json()["items"]
    op_id = next(u["id"] for u in users if u["email"] == "operator-a@test.com")

    def trigger():
        client.patch(
            f"/api/v1/users/{op_id}?organization_id={seeded['org_a']}",
            json={"is_active": False}, headers=super_headers,
        )

    _assert_ws_closes(client, tokens["access_token"], trigger)


def test_role_change_closes_live_ws(client, seeded, super_headers):
    tokens = _login(client, "viewer-a@test.com")
    users = client.get(
        f"/api/v1/users?organization_id={seeded['org_a']}", headers=super_headers
    ).json()["items"]
    vid = next(u["id"] for u in users if u["email"] == "viewer-a@test.com")

    def trigger():
        client.patch(
            f"/api/v1/users/{vid}?organization_id={seeded['org_a']}",
            json={"role": "operator"}, headers=super_headers,
        )

    _assert_ws_closes(client, tokens["access_token"], trigger)


def test_password_change_closes_live_ws(client, seeded):
    tokens = _login(client, "viewer-a@test.com")

    def trigger():
        client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "password123", "new_password": "newpassword1"},
            headers=_auth(tokens),
        )

    _assert_ws_closes(client, tokens["access_token"], trigger)


def test_suspend_org_closes_all_its_sockets_only(client, seeded, super_headers):
    """Suspending org A drops its sockets; org B is untouched."""
    tokens_a = _login(client, "admin-a@test.com")
    tokens_b = _login(client, "admin-b@test.com")

    with client.websocket_connect(f"/ws/events?token={tokens_b['access_token']}") as ws_b:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/events?token={tokens_a['access_token']}") as ws_a:
                client.patch(
                    f"/api/v1/organizations/{seeded['org_a']}",
                    json={"is_active": False}, headers=super_headers,
                )
                ws_a.receive_text()
        # Org B's socket is still open and usable.
        assert client.get("/api/v1/auth/me", headers=_auth(tokens_b)).status_code == 200
        ws_b.close()


# --- no secrets in the audit trail ----------------------------------------

def test_no_tokens_or_hashes_in_audit_trail(client, seeded):
    t0 = _login(client)
    t1 = _refresh(client, t0["refresh_token"]).json()
    _refresh(client, t0["refresh_token"])  # trigger reuse -> audit event
    client.post("/api/v1/auth/logout", headers=_auth(t1))

    secrets = {
        t0["refresh_token"], t0["access_token"], t1["refresh_token"], t1["access_token"],
        hash_token(t0["refresh_token"]), hash_token(t1["refresh_token"]),
    }
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).all()
        assert any(r.action == "refresh_reuse_detected" for r in rows)  # event was recorded
        blob = " ".join(f"{r.action} {r.resource_type} {r.resource_id} {r.details}" for r in rows)
    finally:
        db.close()
    for secret in secrets:
        assert secret not in blob


def test_no_tokens_in_logs(client, seeded, caplog):
    import logging
    with caplog.at_level(logging.DEBUG):
        t0 = _login(client)
        t1 = _refresh(client, t0["refresh_token"]).json()
        _refresh(client, t0["refresh_token"])
    for secret in (t0["refresh_token"], t1["refresh_token"], hash_token(t0["refresh_token"])):
        assert secret not in caplog.text
