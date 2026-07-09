"""Events (real-time monitoring / history) and audit trail."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import EventType, OrgScopedMixin, utcnow


class Event(Base, OrgScopedMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[EventType] = mapped_column(Enum(EventType), index=True, nullable=False)
    controller_id: Mapped[int | None] = mapped_column(ForeignKey("controllers.id", ondelete="SET NULL"), index=True)
    door_id: Mapped[int | None] = mapped_column(ForeignKey("doors.id", ondelete="SET NULL"), index=True)
    cardholder_id: Mapped[int | None] = mapped_column(ForeignKey("cardholders.id", ondelete="SET NULL"), index=True)
    credential_id: Mapped[int | None] = mapped_column(ForeignKey("credentials.id", ondelete="SET NULL"))
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    controller = relationship("Controller")
    door = relationship("Door")
    cardholder = relationship("Cardholder")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # create/update/delete/login/command
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(50))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    user = relationship("User")
