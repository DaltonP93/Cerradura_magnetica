"""Authentication session lifecycle: create, rotate, validate, revoke.

Design notes
------------
* A session owns a chain of refresh-token *generations*
  (:class:`AuthRefreshToken`). Presenting **any** generation that has already
  been used or revoked is treated as theft and revokes the whole family
  (session + every generation). This covers replays of arbitrarily old
  generations, not just the immediately previous one.
* Rotation is atomic: the current generation is consumed with a conditional
  ``UPDATE ... WHERE used_at IS NULL`` and a ``rowcount == 1`` check, so two
  concurrent requests carrying the same token can never both succeed. On
  PostgreSQL the losing request blocks on the row lock and then sees the row
  already consumed; on SQLite the database-level write lock serialises the two.
  A unique constraint on ``token_hash`` and on ``(session, generation)`` backs
  this up.
* Concurrency policy: a lost race is treated as reuse and revokes the family
  (fail-closed). There is deliberately no silent grace window — a legitimate
  double-submit forces re-authentication rather than leaving ambiguous state.
* Only token **hashes** are stored or logged; raw tokens never touch the
  database or the audit trail.
"""
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_token,
    new_session_id,
)
from app.models import AuthRefreshToken, AuthSession, Organization, User

settings = get_settings()


class SessionError(Exception):
    """Refresh/validation failure.

    ``reuse`` marks a replayed or raced generation (the family was revoked).
    ``session_id``/``organization_id`` let the caller emit a security event and
    tear down live connections without re-loading anything.
    """

    def __init__(
        self,
        message: str,
        *,
        reuse: bool = False,
        session_id: str | None = None,
        organization_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reuse = reuse
        self.session_id = session_id
        self.organization_id = organization_id


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _expired(dt: datetime | None) -> bool:
    aware = _as_utc(dt)
    return aware is not None and _now() > aware


# --- creation -------------------------------------------------------------

def issue_tokens(db: Session, user: User, request: Request | None = None) -> tuple[str, str, AuthSession]:
    """Create a fresh session with its first refresh generation."""
    session_id = new_session_id()
    now = _now()
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    auth_session = AuthSession(
        session_id=session_id,
        user_id=user.id,
        issued_at=now,
        expires_at=expires_at,
        last_used_at=now,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.add(auth_session)
    db.flush()

    refresh_token = create_refresh_token(user.id, session_id)
    db.add(
        AuthRefreshToken(
            auth_session_id=auth_session.id,
            token_hash=hash_token(refresh_token),
            generation=0,
            issued_at=now,
            expires_at=expires_at,
        )
    )
    db.flush()
    access_token = create_access_token(user.id, user.organization_id, user.role.value, session_id)
    return access_token, refresh_token, auth_session


# --- rotation / refresh ---------------------------------------------------

def rotate_refresh(db: Session, session_id: str, presented_token: str) -> tuple[str, str]:
    """Validate + atomically consume a refresh token and issue the next pair.

    Raises :class:`SessionError` on any problem; a replayed/raced generation
    raises with ``reuse=True`` after revoking the whole family.
    """
    session = db.execute(
        select(AuthSession).where(AuthSession.session_id == session_id)
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        raise SessionError("Session is not active")
    if _expired(session.expires_at):
        raise SessionError("Session expired")

    token_hash = hash_token(presented_token)
    token = db.execute(
        select(AuthRefreshToken).where(
            AuthRefreshToken.auth_session_id == session.id,
            AuthRefreshToken.token_hash == token_hash,
        )
    ).scalar_one_or_none()

    # Unknown token for this session: reject, but never revoke another session.
    if token is None:
        raise SessionError("Refresh token does not match session")

    # A generation that was already spent or revoked → replay → kill the family.
    if token.used_at is not None or token.revoked_at is not None:
        _revoke_family(db, session, "refresh_reuse")
        raise SessionError(
            "Refresh token already used",
            reuse=True,
            session_id=session.session_id,
            organization_id=_org_id(db, session.user_id),
        )

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        _revoke_family(db, session, "user_inactive")
        raise SessionError("User not found or inactive", session_id=session.session_id)
    if not organization_active(db, user):
        _revoke_family(db, session, "org_suspended")
        raise SessionError(
            "Organization is suspended",
            session_id=session.session_id,
            organization_id=user.organization_id,
        )

    # Atomic compare-and-swap: only one caller can flip used_at from NULL.
    now = _now()
    result = db.execute(
        update(AuthRefreshToken)
        .where(AuthRefreshToken.id == token.id, AuthRefreshToken.used_at.is_(None))
        .values(used_at=now)
    )
    if result.rowcount != 1:
        # Someone else consumed this exact generation first → treat as reuse.
        _revoke_family(db, session, "refresh_race")
        raise SessionError(
            "Refresh token already used",
            reuse=True,
            session_id=session.session_id,
            organization_id=_org_id(db, session.user_id),
        )

    new_refresh = create_refresh_token(user.id, session.session_id)
    next_gen = AuthRefreshToken(
        auth_session_id=session.id,
        token_hash=hash_token(new_refresh),
        generation=token.generation + 1,
        issued_at=now,
        expires_at=session.expires_at,
    )
    db.add(next_gen)
    db.flush()
    token.replaced_by_id = next_gen.id
    session.last_used_at = now
    access = create_access_token(user.id, user.organization_id, user.role.value, session.session_id)
    return access, new_refresh


# --- revocation -----------------------------------------------------------

def _revoke_family(db: Session, session: AuthSession, reason: str) -> None:
    now = _now()
    if session.revoked_at is None:
        session.revoked_at = now
        session.revoked_reason = reason
    db.execute(
        update(AuthRefreshToken)
        .where(AuthRefreshToken.auth_session_id == session.id, AuthRefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.flush()


def revoke(session: AuthSession, reason: str) -> None:
    """Revoke a single session object (caller flushes/commits)."""
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoked_reason = reason


def revoke_session_id(db: Session, session_id: str, reason: str) -> AuthSession | None:
    session = db.execute(
        select(AuthSession).where(AuthSession.session_id == session_id)
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    _revoke_family(db, session, reason)
    return session


def revoke_user_sessions(db: Session, user_id: int, reason: str) -> int:
    sessions = list(
        db.execute(
            select(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
            )
        ).scalars()
    )
    for s in sessions:
        _revoke_family(db, s, reason)
    return len(sessions)


def revoke_org_sessions(db: Session, organization_id: int, reason: str) -> int:
    user_ids = list(
        db.execute(select(User.id).where(User.organization_id == organization_id)).scalars()
    )
    if not user_ids:
        return 0
    sessions = list(
        db.execute(
            select(AuthSession).where(
                AuthSession.user_id.in_(user_ids), AuthSession.revoked_at.is_(None)
            )
        ).scalars()
    )
    for s in sessions:
        _revoke_family(db, s, reason)
    return len(sessions)


# --- validation / lookups -------------------------------------------------

def get_active_session(db: Session, session_id: str) -> AuthSession | None:
    """Return the session if it exists, is not revoked and has not expired."""
    session = db.execute(
        select(AuthSession).where(AuthSession.session_id == session_id)
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None or _expired(session.expires_at):
        return None
    return session


def session_is_live(db: Session, session_id: str) -> bool:
    """True only if the session is active AND its user and org are active."""
    session = get_active_session(db, session_id)
    if session is None:
        return False
    user = db.get(User, session.user_id)
    return user is not None and user.is_active and organization_active(db, user)


def organization_active(db: Session, user: User) -> bool:
    if user.organization_id is None:
        return True
    org = db.get(Organization, user.organization_id)
    return org is not None and org.is_active


# --- housekeeping ---------------------------------------------------------

def purge_expired(db: Session) -> int:
    """Delete refresh generations and sessions past their expiry. Returns rows removed."""
    now = _now()
    removed = db.execute(
        delete(AuthRefreshToken).where(AuthRefreshToken.expires_at < now)
    ).rowcount or 0
    removed += db.execute(
        delete(AuthSession).where(AuthSession.expires_at < now)
    ).rowcount or 0
    return removed


def _org_id(db: Session, user_id: int) -> int | None:
    user = db.get(User, user_id)
    return user.organization_id if user else None


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    return ua[:256] if ua else None
