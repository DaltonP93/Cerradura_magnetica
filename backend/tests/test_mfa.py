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
