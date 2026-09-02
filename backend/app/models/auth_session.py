"""Server-side authentication sessions and their refresh-token generations.

A login creates one :class:`AuthSession`. Every refresh token that session ever
issues is recorded as an :class:`AuthRefreshToken` generation, storing only the
SHA-256 hash of the token — never the token itself. Keeping the whole chain for
the life of the session lets us detect the replay of *any* previously issued
generation (not just the immediately previous one) and revoke the whole family.
Access tokens carry the session id (``sid``) so revocation — logout, suspension
or reuse detection — takes effect on the next request.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class AuthSession(Base, TimestampMixin):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(64))

    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))

    user = relationship("User")
    tokens = relationship(
        "AuthRefreshToken", back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class AuthRefreshToken(Base, TimestampMixin):
    """One refresh-token generation within a session.

    ``used_at`` is set atomically when the token is consumed by a rotation, so a
    conditional (compare-and-swap) update guarantees a token is spent at most
    once even under concurrent requests.
    """

    __tablename__ = "auth_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("auth_session_id", "generation", name="uq_refresh_session_generation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    auth_session_id: Mapped[int] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # SHA-256 hex of the refresh token; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_refresh_tokens.id", ondelete="SET NULL")
    )

    session = relationship("AuthSession", back_populates="tokens")
