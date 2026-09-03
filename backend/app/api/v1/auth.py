from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import rate_limit_auth
from app.core.security import decode_token, hash_password, verify_password
from app.core.totp import generate_secret, provisioning_uri, verify_code
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MfaDisableRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from app.schemas.common import Message
from app.services import sessions
from app.services.audit import record_audit
from app.services.events import manager

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_bearer = HTTPBearer(auto_error=False)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.post("/login", response_model=TokenPair, dependencies=[Depends(rate_limit_auth)])
def login(body: LoginRequest, db: DbSession, request: Request):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    now = datetime.now(UTC)

    locked_until = _as_utc(user.locked_until) if user else None
    if locked_until and locked_until > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Account temporarily locked after repeated failed logins. Try again later.",
        )

    if user is None or not verify_password(body.password, user.hashed_password):
        # Count the failure and lock the account once the threshold is reached.
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                record_audit(
                    db, user=user, action="account_locked", resource_type="user",
                    resource_id=user.id, request=request,
                    details={"lockout_minutes": settings.login_lockout_minutes},
                )
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")
    if not sessions.organization_active(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is suspended")

    # Second factor, if enabled. A missing code is a two-step prompt (not a
    # failed attempt); a wrong code counts toward the lockout.
    if user.mfa_enabled:
        if not body.mfa_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code required")
        if not verify_code(user.mfa_secret, body.mfa_code):
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid MFA code")

    # A successful login clears any accumulated failure state.
    user.failed_login_count = 0
    user.locked_until = None
    sessions.purge_expired(db)
    access_token, refresh_token, _ = sessions.issue_tokens(db, user, request)
    user.last_login_at = now
    record_audit(db, user=user, action="login", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(rate_limit_auth)])
def refresh(body: RefreshRequest, db: DbSession):
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token") from exc

    session_id = payload.get("sid")
    if not session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is not bound to a session")

    try:
        access_token, refresh_token = sessions.rotate_refresh(
            db, session_id, body.refresh_token, int(payload["sub"])
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
            manager.close_session(exc.session_id)  # tear down live sockets on reuse
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, exc.message) from exc

    db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=Message)
def logout(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
):
    """Revoke the session behind the presented access token (idempotent)."""
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials, "access")
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
                manager.close_session(session.session_id)
    return Message(detail="Logged out")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(user: CurrentUser, db: DbSession):
    """Generate a TOTP secret and return its provisioning URI. Not active until
    confirmed via /mfa/enable."""
    secret = generate_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    db.commit()
    return MfaSetupResponse(secret=secret, provisioning_uri=provisioning_uri(secret, user.email))


@router.post("/mfa/enable", response_model=Message)
def mfa_enable(body: MfaVerifyRequest, user: CurrentUser, db: DbSession, request: Request):
    if not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start MFA setup first")
    if not verify_code(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MFA code")
    user.mfa_enabled = True
    record_audit(db, user=user, action="mfa_enabled", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return Message(detail="MFA enabled")


@router.post("/mfa/disable", response_model=Message)
def mfa_disable(body: MfaDisableRequest, user: CurrentUser, db: DbSession, request: Request):
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if not user.mfa_enabled or not verify_code(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MFA code")
    user.mfa_enabled = False
    user.mfa_secret = None
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
    manager.close_user(user.id)
    return Message(detail="Password updated")
