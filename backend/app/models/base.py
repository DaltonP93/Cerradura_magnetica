"""Shared model mixins and enums."""
import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class OrgScopedMixin:
    """Every tenant-owned row carries its organization id."""

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"  # platform operator, cross-tenant
    ADMIN = "admin"              # tenant administrator
    OPERATOR = "operator"        # day-to-day operation (open doors, manage people)
    VIEWER = "viewer"            # read-only


class ControllerStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class DoorMode(str, enum.Enum):
    CONTROLLED = "controlled"          # opens with valid credential
    NORMALLY_OPEN = "normally_open"    # always unlocked
    NORMALLY_CLOSED = "normally_closed"  # always locked, remote open only


class CredentialType(str, enum.Enum):
    CARD = "card"
    PIN = "pin"
    CARD_PLUS_PIN = "card_plus_pin"


class EventType(str, enum.Enum):
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    DOOR_OPENED = "door_opened"
    DOOR_CLOSED = "door_closed"
    DOOR_FORCED = "door_forced"
    DOOR_HELD_OPEN = "door_held_open"
    REMOTE_OPEN = "remote_open"
    CONTROLLER_ONLINE = "controller_online"
    CONTROLLER_OFFLINE = "controller_offline"
    ALARM = "alarm"


class DeniedReason(str, enum.Enum):
    UNKNOWN_CREDENTIAL = "unknown_credential"
    CREDENTIAL_INACTIVE = "credential_inactive"
    CARDHOLDER_INACTIVE = "cardholder_inactive"
    OUT_OF_VALIDITY = "out_of_validity"
    NO_ACCESS_LEVEL = "no_access_level"
    OUT_OF_SCHEDULE = "out_of_schedule"
    HOLIDAY = "holiday"
    WRONG_PIN = "wrong_pin"
    DOOR_LOCKED = "door_locked"
