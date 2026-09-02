"""Authentication session lifecycle: create, rotate, validate, revoke.

A session is the server-side anchor for a login. The refresh token rotates on
each use and the previous hash is retained so a replayed (stolen) token is
detected and the session is revoked. Access-token validation looks the session
up by its ``sid`` claim, so revocation — logout or suspension — is effective on
the next request rather than after the access token expires.
"""
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_token,
    new_session_id,
)
from app.models import AuthSession, Organization, User

settings = get_settings()


class SessionError(Exception):
    """Refresh/validation failure. ``reuse`` flags a replayed rotated token."""

    def __init__(self, message: str, *, reuse: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.reuse = reuse


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def issue_tokens(db: Session, user: User, request: Request | None = None) -> tuple[str, str, AuthSession]:
    """Create a fresh session and return (access_token, refresh_token, session)."""
    session_id = new_session_id()
    refresh_token = create_refresh_token(user.id, session_id)
    now = _now()
    auth_session = AuthSession(
        session_id=session_id,
        user_id=user.id,
        current_token_hash=hash_token(refresh_token),
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        last_used_at=now,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.add(auth_session)
    db.flush()
    access_token = create_access_token(user.id, user.organization_id, user.role.value, session_id)
    return access_token, refresh_token, auth_session


def rotate(db: Session, user: User, session: AuthSession) -> tuple[str, str]:
    """Rotate the refresh token of an existing session. Returns (access, refresh)."""
    new_refresh = create_refresh_token(user.id, session.session_id)
    session.previous_token_hash = session.current_token_hash
    session.current_token_hash = hash_token(new_refresh)
    session.last_used_at = _now()
    db.flush()
    access = create_access_token(user.id, user.organization_id, user.role.value, session.session_id)
    return access, new_refresh


def revoke(session: AuthSession, reason: str) -> None:
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoked_reason = reason


def revoke_user_sessions(db: Session, user_id: int, reason: str) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason)
    )
    return result.rowcount or 0


def revoke_org_sessions(db: Session, organization_id: int, reason: str) -> int:
    user_ids = select(User.id).where(User.organization_id == organization_id)
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id.in_(user_ids), AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason)
    )
    return result.rowcount or 0


def get_active_session(db: Session, session_id: str) -> AuthSession | None:
    """Return the session if it exists, is not revoked and has not expired."""
    session = db.execute(
        select(AuthSession).where(AuthSession.session_id == session_id)
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    if _as_utc(session.expires_at) is not None and _now() > _as_utc(session.expires_at):
        return None
    return session


def consume_for_refresh(db: Session, session_id: str, presented_token: str) -> tuple[User, AuthSession]:
    """Validate a refresh attempt. Raises SessionError on any problem.

    Rotated-token replay revokes the session (``reuse=True``).
    """
    session = db.execute(
        select(AuthSession).where(AuthSession.session_id == session_id)
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        raise SessionError("Session is not active")
    if _as_utc(session.expires_at) is not None and _now() > _as_utc(session.expires_at):
        raise SessionError("Session expired")

    token_hash = hash_token(presented_token)
    if token_hash == session.previous_token_hash:
        # A token we already rotated away is being presented again: treat as theft.
        revoke(session, "refresh_reuse")
        db.flush()
        raise SessionError("Refresh token already used", reuse=True)
    if token_hash != session.current_token_hash:
        raise SessionError("Refresh token does not match session")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        revoke(session, "user_inactive")
        db.flush()
        raise SessionError("User not found or inactive")
    if not organization_active(db, user):
        revoke(session, "org_suspended")
        db.flush()
        raise SessionError("Organization is suspended")
    return user, session


def organization_active(db: Session, user: User) -> bool:
    if user.organization_id is None:
        return True
    org = db.get(Organization, user.organization_id)
    return org is not None and org.is_active


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    return ua[:256] if ua else None
