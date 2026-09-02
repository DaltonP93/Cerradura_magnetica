"""Brute-force protection: per-account lockout and per-IP auth rate limiting.

Phase 1 item 7 (rate limiting + lockout; MFA is separate).
"""
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.ratelimit import auth_limiter
from app.models import User

settings = get_settings()


def _fail_login(client, email="admin-a@test.com", password="wrong-password"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _good_login(client, email="admin-a@test.com", password="password123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _user(email="admin-a@test.com") -> User:
    db = SessionLocal()
    try:
        return db.query(User).filter_by(email=email).one()
    finally:
        db.close()


def test_account_locks_after_max_failed_attempts(client, seeded):
    for _ in range(settings.login_max_attempts):
        assert _fail_login(client).status_code == 401
    # Now locked: even the correct password is refused with 429.
    resp = _good_login(client)
    assert resp.status_code == 429
    assert _user().locked_until is not None


def test_lock_expires_and_login_succeeds(client, seeded):
    for _ in range(settings.login_max_attempts):
        _fail_login(client)
    assert _good_login(client).status_code == 429

    # Fast-forward past the lock window.
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(email="admin-a@test.com").one()
        u.locked_until = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    assert _good_login(client).status_code == 200
    fresh = _user()
    assert fresh.locked_until is None and fresh.failed_login_count == 0


def test_successful_login_resets_failed_count(client, seeded):
    for _ in range(settings.login_max_attempts - 1):
        _fail_login(client)
    assert _user().failed_login_count == settings.login_max_attempts - 1
    assert _good_login(client).status_code == 200
    assert _user().failed_login_count == 0


def test_auth_rate_limit_throttles_by_ip(client, seeded):
    auth_limiter.limit = 3
    auth_limiter.reset()
    try:
        # Unknown email → 401 from the handler, but the limiter runs first.
        codes = [
            client.post(
                "/api/v1/auth/login", json={"email": "nobody@test.com", "password": "x"}
            ).status_code
            for _ in range(4)
        ]
        assert codes[:3] == [401, 401, 401]
        assert codes[3] == 429
    finally:
        auth_limiter.limit = 0
        auth_limiter.reset()
