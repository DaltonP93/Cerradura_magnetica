"""Attendance module (Part 4 of the legacy manual): shifts, leaves and manual signs."""
import enum
from datetime import date, datetime, time

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin


class LeaveType(str, enum.Enum):
    LEAVE = "leave"
    BUSINESS_TRIP = "business_trip"


class SignKind(str, enum.Enum):
    IN = "in"
    OUT = "out"


class Shift(Base, TimestampMixin, OrgScopedMixin):
    """Normal shift rule: expected working window on given weekdays."""

    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    late_tolerance_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    early_leave_tolerance_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    days_of_week: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # 0=Monday .. 6=Sunday


class Leave(Base, TimestampMixin, OrgScopedMixin):
    """Approved absence: leave or business trip (manual 4.3)."""

    __tablename__ = "leaves"

    id: Mapped[int] = mapped_column(primary_key=True)
    cardholder_id: Mapped[int] = mapped_column(
        ForeignKey("cardholders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[LeaveType] = mapped_column(Enum(LeaveType), default=LeaveType.LEAVE, nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    cardholder = relationship("Cardholder")


class ManualSign(Base, TimestampMixin, OrgScopedMixin):
    """Manual punch to fix a missing check-in/check-out (manual 4.4)."""

    __tablename__ = "manual_signs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cardholder_id: Mapped[int] = mapped_column(
        ForeignKey("cardholders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[SignKind] = mapped_column(Enum(SignKind), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    cardholder = relationship("Cardholder")
