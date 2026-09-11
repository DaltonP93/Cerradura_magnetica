from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    new_csrf_token,
    set_auth_cookies,
)
from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import rate_limit_auth
from app.core.security import decode_token, hash_password, verify_password
from app.core.totp import generate_secret, provisioning_uri, verify_code
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MfaDisableRequest,
    MfaEnableResponse,
    MfaRecoveryRegenerateRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from app.schemas.common import Message
from app.services import mfa_recovery, revocation_bus, sessions
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_bearer = HTTPBearer(auto_error=False)

# F-8: a fixed bcrypt hash used to equalize login timing when the email does not
# exist. Without it, a missing user skips ``verify_password`` and returns much
# faster than a real user whose password is checked, letting an attacker
# enumerate registered emails by response time. We run the same bcrypt work
# against this dummy and discard the result. Computed once at import.
_DUMMY_PW_HASH = hash_password("acp-login-timing-equalizer")


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _register_failed_login(db, user: User, now: datetime, request: Request) -> None:
    """Count a failed login and lock the account at the threshold — atomically.

    F-1: the counter is bumped with a single ``UPDATE ... SET failed_login_count
    = failed_login_count + 1`` (evaluated under the row lock), not a Python
    read-modify-write, so concurrent failed attempts cannot lose increments and
    slip past the lockout threshold. The DB is the source of truth for the count.
    """
    new_count = db.execute(
        update(User)
        .where(User.id == user.id)
        .values(failed_login_count=User.failed_login_count + 1)
        .returning(User.failed_login_count)
        .execution_options(synchronize_session=False)
    ).scalar_one()
    if new_count >= settings.login_max_attempts:
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                locked_until=now + timedelta(minutes=settings.login_lockout_minutes),
                failed_login_count=0,
            )
            .execution_options(synchronize_session=False)
        )
        record_audit(
            db, user=user, action="account_locked", resource_type="user",
            resource_id=user.id, request=request,
            details={"lockout_minutes": settings.login_lockout_minutes},
        )
    db.expire(user)  # ORM copy is stale after the Core UPDATE(s)
    db.commit()


@router.post("/login", response_model=TokenPair, dependencies=[Depends(rate_limit_auth)])
def login(body: LoginRequest, db: DbSession, request: Request, response: Response):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    now = datetime.now(UTC)

    locked_until = _as_utc(user.locked_until) if user else None
    if locked_until and locked_until > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Account temporarily locked after repeated failed logins. Try again later.",
        )

    # F-8: always run exactly one bcrypt verification, even when the email does
    # not exist, against a dummy hash. Otherwise a missing user short-circuits
    # ``verify_password`` and returns far faster than a real user, letting an
    # attacker enumerate registered emails by response time. The dummy result is
    # discarded — a missing user still fails below.
    password_ok = verify_password(body.password, user.hashed_password if user else _DUMMY_PW_HASH)

    if user is None or not password_ok:
        # Count the failure and lock the account once the threshold is reached.
        if user is not None:
            _register_failed_login(db, user, now, request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")
    if not sessions.organization_active(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is suspended")

    # Second factor, if enabled. A missing code is a two-step prompt (not a
    # failed attempt); a wrong code counts toward the lockout. F-5: a one-time
    # recovery code may be presented instead of the TOTP code (device lost).
    if user.mfa_enabled:
        if not body.mfa_code and not body.recovery_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code required")
        code_ok = bool(body.mfa_code) and verify_code(user.mfa_secret, body.mfa_code)
        recovery_ok = False
        if not code_ok and body.recovery_code:
            # Consuming a recovery code mutates the user; it is persisted by the
            # commit below on the success path.
            recovery_ok = mfa_recovery.consume(user, body.recovery_code)
        if not code_ok and not recovery_ok:
            # F-1: atomic failure/lockout accounting (shared with the password path).
            _register_failed_login(db, user, now, request)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid MFA code")
        if recovery_ok:
            record_audit(
                db, user=user, action="mfa_recovery_code_used", resource_type="user",
                resource_id=user.id, request=request,
                details={"remaining_recovery_codes": mfa_recovery.remaining(user)},
            )

    # A successful login clears any accumulated failure state.
    user.failed_login_count = 0
    user.locked_until = None
    sessions.purge_expired(db)
    access_token, refresh_token, _ = sessions.issue_tokens(db, user, request)
    user.last_login_at = now
    record_audit(db, user=user, action="login", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    # Browser sessions carry the tokens in HttpOnly cookies; the body is kept
    # for programmatic clients.
    set_auth_cookies(response, access=access_token, refresh=refresh_token, csrf=new_csrf_token())
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(rate_limit_auth)])
def refresh(body: RefreshRequest, db: DbSession, request: Request, response: Response):
    # Prefer the body token (programmatic clients); fall back to the HttpOnly
    # refresh cookie (browser clients).
    presented = body.refresh_token or request.cookies.get(REFRESH_COOKIE)
    if not presented:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token provided")
    try:
        payload = decode_token(presented, "refresh")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token") from exc

    session_id = payload.get("sid")
    if not session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is not bound to a session")

    try:
        access_token, refresh_token = sessions.rotate_refresh(
            db, session_id, presented, int(payload["sub"])
        )
    except sessions.SessionError as exc:
        if exc.reuse and exc.session_id:
            # Security event: replay/race detected. Never store the token itself.
            record_audit(
                db, user=None, action="refresh_reuse_detected", resource_type="session",
                resource_id=exc.session_id, organization_id=exc.organization_id,
                details={"reason": "refresh_reuse"},
            )
        db.commit()  # persist any family revocation triggered above
        if exc.session_id:
            revocation_bus.revoke_session(exc.session_id)  # tear down live sockets on reuse
        # A rejected refresh clears the browser's stale cookies.
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, exc.message) from exc

    db.commit()
    set_auth_cookies(response, access=access_token, refresh=refresh_token, csrf=new_csrf_token())
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=Message)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
):
    """Revoke the session behind the presented access token (idempotent)."""
    token = credentials.credentials if credentials is not None else request.cookies.get(ACCESS_COOKIE)
    if token:
        try:
            payload = decode_token(token, "access")
        except pyjwt.InvalidTokenError:
            payload = None
        if payload and payload.get("sid"):
            session = sessions.revoke_session_id(db, payload["sid"], "logout")
            if session is not None:
                user = db.get(User, session.user_id)
                record_audit(
                    db, user=user, action="logout", resource_type="session",
                    resource_id=session.session_id,
                )
                db.commit()
                revocation_bus.revoke_session(session.session_id)
    # Always clear the browser's auth cookies, even for an already-dead session.
    clear_auth_cookies(response)
    return Message(detail="Logged out")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(user: CurrentUser, db: DbSession):
    """Generate a TOTP secret and return its provisioning URI. Not active until
    confirmed via /mfa/enable."""
    # Never let an unauthenticated re-enrolment silently drop an active second
    # factor: while MFA is on, the secret can only be rotated by first disabling
    # it (which requires the current password AND a valid code).
    if user.mfa_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "MFA is already enabled; disable it before re-enrolling.",
        )
    secret = generate_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    db.commit()
    return MfaSetupResponse(secret=secret, provisioning_uri=provisioning_uri(secret, user.email))


@router.post("/mfa/enable", response_model=MfaEnableResponse)
def mfa_enable(body: MfaVerifyRequest, user: CurrentUser, db: DbSession, request: Request):
    if not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start MFA setup first")
    if not verify_code(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MFA code")
    user.mfa_enabled = True
    # F-5: issue one-time recovery codes so a lost TOTP device is recoverable.
    # Store only the hashes; the plaintext is returned once, here, and never again.
    codes, hashes = mfa_recovery.generate()
    user.mfa_recovery_hashes = hashes
    record_audit(db, user=user, action="mfa_enabled", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return MfaEnableResponse(detail="MFA enabled", recovery_codes=codes)


@router.post("/mfa/recovery-codes", response_model=MfaEnableResponse)
def mfa_regenerate_recovery_codes(
    body: MfaRecoveryRegenerateRequest, user: CurrentUser, db: DbSession, request: Request
):
    """Re-issue recovery codes (e.g. after some were used). Requires the current
    password AND a valid TOTP code; the previous codes are invalidated."""
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if not user.mfa_enabled or not verify_code(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MFA code")
    codes, hashes = mfa_recovery.generate()
    user.mfa_recovery_hashes = hashes  # replaces (invalidates) any prior codes
    record_audit(
        db, user=user, action="mfa_recovery_codes_regenerated", resource_type="user",
        resource_id=user.id, request=request,
    )
    db.commit()
    return MfaEnableResponse(detail="Recovery codes regenerated", recovery_codes=codes)


@router.post("/mfa/disable", response_model=Message)
def mfa_disable(body: MfaDisableRequest, user: CurrentUser, db: DbSession, request: Request):
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if not user.mfa_enabled or not verify_code(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MFA code")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_hashes = None  # discard recovery codes with the second factor
    record_audit(db, user=user, action="mfa_disabled", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return Message(detail="MFA disabled")


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordRequest, user: CurrentUser, db: DbSession, request: Request):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    # A password change invalidates every existing session for the user.
    sessions.revoke_user_sessions(db, user.id, "password_change")
    record_audit(db, user=user, action="change_password", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    revocation_bus.revoke_user(user.id)
    return Message(detail="Password updated")
