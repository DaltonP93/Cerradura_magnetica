from datetime import datetime

from pydantic import BaseModel, Field

from app.models.base import ControllerStatus, DoorMode, DoorOpenRequestStatus
from app.schemas.common import ORMModel


# --- Sites ---
class SiteOut(ORMModel):
    id: int
    name: str
    address: str | None
    timezone: str
    created_at: datetime


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    timezone: str = "UTC"


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = None


# --- Doors ---
class DoorOut(ORMModel):
    id: int
    controller_id: int
    number: int
    name: str
    mode: DoorMode
    open_duration_seconds: int
    held_open_alarm_seconds: int
    sensor_enabled: bool
    anti_passback: bool
    first_card_open: bool
    multi_card_count: int
    requires_dual_approval: bool


class DoorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    mode: DoorMode | None = None
    open_duration_seconds: int | None = Field(default=None, ge=1, le=60)
    held_open_alarm_seconds: int | None = Field(default=None, ge=5, le=600)
    sensor_enabled: bool | None = None
    anti_passback: bool | None = None
    first_card_open: bool | None = None
    multi_card_count: int | None = Field(default=None, ge=1, le=4)
    requires_dual_approval: bool | None = None


# --- Dual-approval remote open ---
class DoorOpenRequestCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DoorOpenRequestOut(ORMModel):
    id: int
    door_id: int
    controller_id: int
    requested_by_id: int | None
    approved_by_id: int | None
    status: DoorOpenRequestStatus
    reason: str | None
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None


# --- Controllers ---
class ControllerOut(ORMModel):
    id: int
    site_id: int | None
    name: str
    model: str
    serial_number: str
    ip_address: str | None
    port: int
    door_count: int
    firmware_version: str | None
    status: ControllerStatus
    last_seen_at: datetime | None
    interlock_enabled: bool
    created_at: datetime
    doors: list[DoorOut] = []


class ControllerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    serial_number: str = Field(min_length=1, max_length=100)
    model: str = "L04"
    site_id: int | None = None
    ip_address: str | None = None
    port: int = Field(default=60000, ge=1, le=65535)
    door_count: int = Field(default=4, ge=1, le=4)


class ControllerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    site_id: int | None = None
    ip_address: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    interlock_enabled: bool | None = None


class CommandResult(BaseModel):
    success: bool
    message: str
