"""Access rules: schedules (time zones in the L04 manual), holidays and access levels."""
from datetime import date, time

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, Table, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin

cardholder_access_levels = Table(
    "cardholder_access_levels",
    Base.metadata,
    Column("cardholder_id", ForeignKey("cardholders.id", ondelete="CASCADE"), primary_key=True),
    Column("access_level_id", ForeignKey("access_levels.id", ondelete="CASCADE"), primary_key=True),
)


class Schedule(Base, TimestampMixin, OrgScopedMixin):
    """Weekly time profile: when access is allowed."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    allow_on_holidays: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    intervals: Mapped[list["ScheduleInterval"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="ScheduleInterval.day_of_week"
    )


class ScheduleInterval(Base):
    __tablename__ = "schedule_intervals"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    schedule: Mapped[Schedule] = relationship(back_populates="intervals")


class Holiday(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("organization_id", "date", name="uq_holiday_org_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)


class AccessLevel(Base, TimestampMixin, OrgScopedMixin):
    """A named set of (door, schedule) permissions assigned to cardholders."""

    __tablename__ = "access_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    door_rules: Mapped[list["AccessLevelDoor"]] = relationship(
        back_populates="access_level", cascade="all, delete-orphan"
    )
    cardholders = relationship(
        "Cardholder", secondary=cardholder_access_levels, backref="access_levels"
    )


class AccessLevelDoor(Base):
    __tablename__ = "access_level_doors"
    __table_args__ = (
        UniqueConstraint("access_level_id", "door_id", name="uq_access_level_door"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    access_level_id: Mapped[int] = mapped_column(
        ForeignKey("access_levels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    door_id: Mapped[int] = mapped_column(ForeignKey("doors.id", ondelete="CASCADE"), index=True, nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id", ondelete="SET NULL"))

    access_level: Mapped[AccessLevel] = relationship(back_populates="door_rules")
    door = relationship("Door")
    schedule = relationship("Schedule")
