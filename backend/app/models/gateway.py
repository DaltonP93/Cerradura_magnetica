"""Outbox of commands for the local gateway bridge (Fase 3 scaffolding).

The platform enqueues commands here; a local bridge daemon (mTLS-authenticated,
with its own persistent SQLite queue) leases pending commands, executes them
against the physical controllers, and acknowledges the result. Every command
carries an idempotency key so an enqueue or a redelivery is never applied twice.

This is platform-side plumbing only: nothing in this module talks to hardware.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import (
    GatewayCommandStatus,
    GatewayCommandType,
    OrgScopedMixin,
    TimestampMixin,
)


class GatewayCommand(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "gateway_commands"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_gateway_command_idem"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    controller_id: Mapped[int] = mapped_column(
        ForeignKey("controllers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Idempotency: a redelivered enqueue with the same key returns the existing row.
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[GatewayCommandType] = mapped_column(Enum(GatewayCommandType), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[GatewayCommandStatus] = mapped_column(
        Enum(GatewayCommandStatus), default=GatewayCommandStatus.PENDING, index=True, nullable=False
    )
    # Lease: a worker claims the command with a token and an expiry so a crashed
    # worker's in-flight commands can be safely reclaimed.
    lease_token: Mapped[str | None] = mapped_column(String(64))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    controller = relationship("Controller")
