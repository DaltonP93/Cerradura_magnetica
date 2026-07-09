from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


# --- Schedules ---
class ScheduleIntervalIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)  # 0=Monday .. 6=Sunday
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def check_order(self) -> "ScheduleIntervalIn":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ScheduleIntervalOut(ORMModel):
    id: int
    day_of_week: int
    start_time: time
    end_time: time


class ScheduleOut(ORMModel):
    id: int
    name: str
    description: str | None
    allow_on_holidays: bool
    created_at: datetime
    intervals: list[ScheduleIntervalOut] = []


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    allow_on_holidays: bool = False
    intervals: list[ScheduleIntervalIn] = []


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    allow_on_holidays: bool | None = None
    intervals: list[ScheduleIntervalIn] | None = None


# --- Holidays ---
class HolidayOut(ORMModel):
    id: int
    name: str
    date: date


class HolidayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    date: date


# --- Access levels ---
class AccessLevelDoorIn(BaseModel):
    door_id: int
    schedule_id: int | None = None  # None = 24/7


class AccessLevelDoorOut(ORMModel):
    id: int
    door_id: int
    schedule_id: int | None


class AccessLevelOut(ORMModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    door_rules: list[AccessLevelDoorOut] = []


class AccessLevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    door_rules: list[AccessLevelDoorIn] = []


class AccessLevelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    door_rules: list[AccessLevelDoorIn] | None = None
