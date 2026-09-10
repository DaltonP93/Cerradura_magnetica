"""TOTP multi-factor authentication (Phase 1 item 7, MFA part)."""
import pyotp
from sqlalchemy import text

from app.core.database import SessionLocal
from tests.conftest import login


def _login(client, mfa_code=None):
    body = {"email": "admin-a@test.com", "password": "password123"}
    if mfa_code is not None:
        body["mfa_code"] = mfa_code
    return client.post("/api/v1/auth/login", json=body)


def _enable_mfa(client, headers) -> str:
    setup = client.post("/api/v1/auth/mfa/setup", headers=headers).json()
    secret = setup["secret"]
    assert setup["provisioning_uri"].startswith("otpauth://totp/")
    resp = client.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)
    assert resp.status_code == 200, resp.text
    return secret


def test_setup_enable_and_login_requires_totp(client, seeded):
    headers = login(client, "admin-a@test.com")
    secret = _enable_mfa(client, headers)

    # Password alone is now insufficient.
    resp = _login(client)
    assert resp.status_code == 401 and "MFA" in resp.json()["detail"]
    # Wrong code is rejected.
    assert _login(client, mfa_code="000000").status_code == 401
    # Correct code logs in.
    ok = _login(client, mfa_code=pyotp.TOTP(secret).now())
    assert ok.status_code == 200 and ok.json()["access_token"]


def test_enable_rejects_invalid_code(client, seeded):
    headers = login(client, "admin-a@test.com")
    client.post("/api/v1/auth/mfa/setup", headers=headers)
    resp = client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=headers)
    assert resp.status_code == 400


def test_disable_requires_password_and_code(client, seeded):
    headers = login(client, "admin-a@test.com")
    secret = _enable_mfa(client, headers)
    # Wrong password refused.
    bad = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "nope", "code": pyotp.TOTP(secret).now()}, headers=headers,
    )
    assert bad.status_code == 400
    # Correct password + code disables it.
    ok = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "password123", "code": pyotp.TOTP(secret).now()}, headers=headers,
    )
    assert ok.status_code == 200
    # Login no longer needs a code.
    assert _login(client).status_code == 200


def test_setup_refused_while_mfa_enabled(client, seeded):
    """Re-running setup on an MFA-enabled account must not silently rotate the
    secret and drop the second factor; disabling first is required."""
    headers = login(client, "admin-a@test.com")
    secret = _enable_mfa(client, headers)
    resp = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert resp.status_code == 409
    # The original factor is still in force.
    assert _login(client).status_code == 401  # code still required
    assert _login(client, mfa_code=pyotp.TOTP(secret).now()).status_code == 200


def test_mfa_secret_encrypted_at_rest(client, seeded):
    headers = login(client, "admin-a@test.com")
    secret = client.post("/api/v1/auth/mfa/setup", headers=headers).json()["secret"]
    db = SessionLocal()
    try:
        raw = db.execute(
            text("SELECT mfa_secret FROM users WHERE email = :e"), {"e": "admin-a@test.com"}
        ).scalar_one()
    finally:
        db.close()
    assert raw and raw != secret  # stored encrypted, not as the base32 secret


# --- F-5: one-time recovery codes ------------------------------------------
def _enable_mfa_with_codes(client, headers):
    setup = client.post("/api/v1/auth/mfa/setup", headers=headers).json()
    secret = setup["secret"]
    resp = client.post(
        "/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    codes = resp.json()["recovery_codes"]
    return secret, codes


def test_enable_returns_one_time_recovery_codes(client, seeded):
    headers = login(client, "admin-a@test.com")
    _, codes = _enable_mfa_with_codes(client, headers)
    assert isinstance(codes, list) and len(codes) == 10
    assert all(isinstance(c, str) and c for c in codes)
    assert len(set(codes)) == 10  # all distinct


def test_recovery_code_logs_in_without_totp(client, seeded):
    headers = login(client, "admin-a@test.com")
    _, codes = _enable_mfa_with_codes(client, headers)
    # No mfa_code, only a recovery code → login succeeds.
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin-a@test.com", "password": "password123", "recovery_code": codes[0]},
    )
    assert resp.status_code == 200 and resp.json()["access_token"]


def test_recovery_code_is_single_use(client, seeded):
    headers = login(client, "admin-a@test.com")
    _, codes = _enable_mfa_with_codes(client, headers)
    body = {"email": "admin-a@test.com", "password": "password123", "recovery_code": codes[0]}
    assert client.post("/api/v1/auth/login", json=body).status_code == 200
    # The same code cannot be reused.
    assert client.post("/api/v1/auth/login", json=body).status_code == 401
    # A different, still-unused code still works.
    body2 = {"email": "admin-a@test.com", "password": "password123", "recovery_code": codes[1]}
    assert client.post("/api/v1/auth/login", json=body2).status_code == 200


def test_invalid_recovery_code_rejected(client, seeded):
    headers = login(client, "admin-a@test.com")
    _enable_mfa_with_codes(client, headers)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin-a@test.com", "password": "password123", "recovery_code": "deadbeefdeadbeef"},
    )
    assert resp.status_code == 401


def test_regenerate_invalidates_previous_codes(client, seeded):
    headers = login(client, "admin-a@test.com")
    secret, old_codes = _enable_mfa_with_codes(client, headers)
    resp = client.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"password": "password123", "code": pyotp.TOTP(secret).now()}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    new_codes = resp.json()["recovery_codes"]
    assert set(new_codes).isdisjoint(old_codes)
    # An old code no longer authenticates ...
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin-a@test.com", "password": "password123", "recovery_code": old_codes[0]},
    ).status_code == 401
    # ... but a new one does.
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin-a@test.com", "password": "password123", "recovery_code": new_codes[0]},
    ).status_code == 200


def test_disable_clears_recovery_codes(client, seeded):
    headers = login(client, "admin-a@test.com")
    secret, codes = _enable_mfa_with_codes(client, headers)
    client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "password123", "code": pyotp.TOTP(secret).now()}, headers=headers,
    )
    db = SessionLocal()
    try:
        stored = db.execute(
            text("SELECT mfa_recovery_hashes FROM users WHERE email = :e"),
            {"e": "admin-a@test.com"},
        ).scalar_one()
    finally:
        db.close()
    assert stored in (None, "null", "[]")


def test_recovery_codes_stored_hashed_not_plaintext(client, seeded):
    headers = login(client, "admin-a@test.com")
    _, codes = _enable_mfa_with_codes(client, headers)
    db = SessionLocal()
    try:
        stored = db.execute(
            text("SELECT mfa_recovery_hashes FROM users WHERE email = :e"),
            {"e": "admin-a@test.com"},
        ).scalar_one()
    finally:
        db.close()
    # No plaintext recovery code appears in the stored JSON blob.
    for c in codes:
        assert c not in stored
