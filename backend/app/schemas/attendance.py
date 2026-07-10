from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

from app.models.attendance import LeaveType, SignKind
from app.schemas.common import ORMModel


# --- Shifts ---
class ShiftOut(ORMModel):
    id: int
    name: str
    start_time: time
    end_time: time
    late_tolerance_minutes: int
    early_leave_tolerance_minutes: int
    days_of_week: list[int]
    created_at: datetime


class ShiftCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_time: time
    end_time: time
    late_tolerance_minutes: int = Field(default=10, ge=0, le=240)
    early_leave_tolerance_minutes: int = Field(default=10, ge=0, le=240)
    days_of_week: list[int] = Field(default=[0, 1, 2, 3, 4])

    @model_validator(mode="after")
    def check(self) -> "ShiftCreate":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise ValueError("days_of_week values must be 0..6")
        return self


class ShiftUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_time: time | None = None
    end_time: time | None = None
    late_tolerance_minutes: int | None = Field(default=None, ge=0, le=240)
    early_leave_tolerance_minutes: int | None = Field(default=None, ge=0, le=240)
    days_of_week: list[int] | None = None


# --- Leaves ---
class LeaveOut(ORMModel):
    id: int
    cardholder_id: int
    type: LeaveType
    date_from: date
    date_to: date
    reason: str | None
    created_at: datetime


class LeaveCreate(BaseModel):
    cardholder_id: int
    type: LeaveType = LeaveType.LEAVE
    date_from: date
    date_to: date
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check(self) -> "LeaveCreate":
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


# --- Manual signs ---
class ManualSignOut(ORMModel):
    id: int
    cardholder_id: int
    kind: SignKind
    signed_at: datetime
    note: str | None
    created_at: datetime


class ManualSignCreate(BaseModel):
    cardholder_id: int
    kind: SignKind
    signed_at: datetime
    note: str | None = Field(default=None, max_length=500)


# --- Report ---
class AttendanceRow(BaseModel):
    cardholder_id: int
    cardholder_name: str
    department: str | None
    date: date
    check_in: datetime | None
    check_out: datetime | None
    statuses: list[str]  # present, late, early_leave, incomplete, absent, on_leave, business_trip, holiday, rest_day


class AttendanceSummary(BaseModel):
    days: int
    present: int
    late: int
    early_leave: int
    absent: int
    on_leave: int
    incomplete: int


class AttendanceReport(BaseModel):
    date_from: date
    date_to: date
    rows: list[AttendanceRow]
    summary: AttendanceSummary
