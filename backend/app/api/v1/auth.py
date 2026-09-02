from datetime import UTC, datetime
from typing import Annotated

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.security import decode_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair, UserOut
from app.schemas.common import Message
from app.services import sessions
from app.services.audit import record_audit
from app.services.events import manager

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=TokenPair)
def login(body: LoginRequest, db: DbSession, request: Request):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")
    if not sessions.organization_active(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is suspended")

    sessions.purge_expired(db)
    access_token, refresh_token, _ = sessions.issue_tokens(db, user, request)
    user.last_login_at = datetime.now(UTC)
    record_audit(db, user=user, action="login", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: DbSession):
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token") from exc

    session_id = payload.get("sid")
    if not session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is not bound to a session")

    try:
        access_token, refresh_token = sessions.rotate_refresh(db, session_id, body.refresh_token)
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
