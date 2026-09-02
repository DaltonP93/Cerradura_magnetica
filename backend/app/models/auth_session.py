"""Server-side authentication sessions.

Each login creates one persistent session row. The refresh token rotates on
every use: the current token's hash is stored, and the immediately previous
hash is kept so that presenting an already-rotated token (token theft/replay)
can be detected and the whole session revoked. Access tokens carry the
session id (``sid``) so that revoking a session — on logout, or when a user or
organization is suspended — takes effect on the next request instead of
waiting for the short access-token lifetime to expire.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
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

    # SHA-256 hex of the current refresh token, and of the one it replaced.
    current_token_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(64))

    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))

    user = relationship("User")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
