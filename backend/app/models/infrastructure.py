"""Physical infrastructure: sites, L04 controllers and doors."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import ControllerStatus, DoorMode, OrgScopedMixin, TimestampMixin


class Site(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    controllers: Mapped[list["Controller"]] = relationship(back_populates="site")


class Controller(Base, TimestampMixin, OrgScopedMixin):
    """An L04-style access control board (up to 4 doors, TCP/IP)."""

    __tablename__ = "controllers"
    __table_args__ = (UniqueConstraint("serial_number", name="uq_controller_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model: Mapped[str] = mapped_column(String(50), default="L04", nullable=False)
    serial_number: Mapped[str] = mapped_column(String(100), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    port: Mapped[int] = mapped_column(Integer, default=60000, nullable=False)
    door_count: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[ControllerStatus] = mapped_column(
        Enum(ControllerStatus), default=ControllerStatus.UNKNOWN, nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Interlock (manual 3.2.7): only one door of the board may be open at a time.
    interlock_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    site: Mapped[Site | None] = relationship(back_populates="controllers")
    doors: Mapped[list["Door"]] = relationship(back_populates="controller", cascade="all, delete-orphan")


class Door(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "doors"
    __table_args__ = (UniqueConstraint("controller_id", "number", name="uq_door_controller_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    controller_id: Mapped[int] = mapped_column(ForeignKey("controllers.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4 on the board
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[DoorMode] = mapped_column(Enum(DoorMode), default=DoorMode.CONTROLLED, nullable=False)
    open_duration_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    held_open_alarm_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    sensor_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    anti_passback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # First card open (manual 3.2.9): door stays unlocked after the first valid card.
    first_card_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # MultiCard access (manual 3.2.8): cards required simultaneously to open (1 = disabled).
    multi_card_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    controller: Mapped[Controller] = relationship(back_populates="doors")
