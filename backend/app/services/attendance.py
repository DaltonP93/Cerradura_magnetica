"""Attendance report computation (Part 4 of the legacy manual).

For each cardholder and day in the range, punches are gathered from access
events (granted swipes) and manual signs. The first punch of the day is the
check-in and the last one the check-out. The cardholder's shift determines
workdays, expected times and tolerances. Days are evaluated in UTC.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Cardholder, Event, EventType, Holiday, Leave, ManualSign, Shift

MAX_RANGE_DAYS = 92


@dataclass
class DayRow:
    cardholder: Cardholder
    day: date
    check_in: datetime | None
    check_out: datetime | None
    statuses: list[str]


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def compute_attendance(
    db: Session,
    *,
    organization_id: int,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    cardholder_id: int | None = None,
) -> list[DayRow]:
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Range too large (max {MAX_RANGE_DAYS} days)")

    holders_stmt = (
        select(Cardholder)
        .options(selectinload(Cardholder.department))
        .where(Cardholder.organization_id == organization_id, Cardholder.is_active.is_(True))
        .order_by(Cardholder.last_name, Cardholder.first_name)
    )
    if department_id is not None:
        holders_stmt = holders_stmt.where(Cardholder.department_id == department_id)
    if cardholder_id is not None:
        holders_stmt = holders_stmt.where(Cardholder.id == cardholder_id)
    holders = list(db.execute(holders_stmt).scalars())
    if not holders:
        return []
    holder_ids = [h.id for h in holders]

    range_start = datetime.combine(date_from, time.min)
    range_end = datetime.combine(date_to + timedelta(days=1), time.min)

    # Punches: granted access events + manual signs, grouped by (cardholder, day)
    punches: dict[tuple[int, date], list[datetime]] = {}
    events = db.execute(
        select(Event.cardholder_id, Event.occurred_at).where(
            Event.organization_id == organization_id,
            Event.type == EventType.ACCESS_GRANTED,
            Event.cardholder_id.in_(holder_ids),
            Event.occurred_at >= range_start,
            Event.occurred_at < range_end,
        )
    )
    for holder_id, occurred_at in events:
        occurred_at = _naive(occurred_at)
        punches.setdefault((holder_id, occurred_at.date()), []).append(occurred_at)
    signs = db.execute(
        select(ManualSign.cardholder_id, ManualSign.signed_at).where(
            ManualSign.organization_id == organization_id,
            ManualSign.cardholder_id.in_(holder_ids),
            ManualSign.signed_at >= range_start,
            ManualSign.signed_at < range_end,
        )
    )
    for holder_id, signed_at in signs:
        signed_at = _naive(signed_at)
        punches.setdefault((holder_id, signed_at.date()), []).append(signed_at)

    leaves: dict[int, list[Leave]] = {}
    for leave in db.execute(
        select(Leave).where(
            Leave.organization_id == organization_id,
            Leave.cardholder_id.in_(holder_ids),
            Leave.date_from <= date_to,
            Leave.date_to >= date_from,
        )
    ).scalars():
        leaves.setdefault(leave.cardholder_id, []).append(leave)

    holidays = {
        d
        for (d,) in db.execute(
            select(Holiday.date).where(
                Holiday.organization_id == organization_id,
                Holiday.date >= date_from,
                Holiday.date <= date_to,
            )
        )
    }
    shifts = {
        s.id: s
        for s in db.execute(select(Shift).where(Shift.organization_id == organization_id)).scalars()
    }

    rows: list[DayRow] = []
    for holder in holders:
        shift = shifts.get(holder.shift_id) if holder.shift_id else None
        day = date_from
        while day <= date_to:
            rows.append(_evaluate_day(holder, shift, day, punches, leaves, holidays))
            day += timedelta(days=1)
    return rows


def _evaluate_day(
    holder: Cardholder,
    shift: Shift | None,
    day: date,
    punches: dict[tuple[int, date], list[datetime]],
    leaves: dict[int, list[Leave]],
    holidays: set[date],
) -> DayRow:
    day_punches = sorted(punches.get((holder.id, day), []))
    check_in = day_punches[0] if day_punches else None
    check_out = day_punches[-1] if len(day_punches) > 1 else None

    statuses: list[str] = []
    leave = next(
        (lv for lv in leaves.get(holder.id, []) if lv.date_from <= day <= lv.date_to), None
    )
    is_workday = shift is not None and day.weekday() in (shift.days_of_week or [])

    if day in holidays:
        statuses.append("holiday")
    elif leave is not None:
        statuses.append(leave.type.value)  # leave | business_trip
    elif not is_workday:
        if day_punches:
            statuses.append("present")
        else:
            statuses.append("rest_day")
    elif not day_punches:
        statuses.append("absent")
    else:
        statuses.append("present")
        assert shift is not None
        late_limit = (
            datetime.combine(day, shift.start_time) + timedelta(minutes=shift.late_tolerance_minutes)
        )
        if check_in and check_in > late_limit:
            statuses.append("late")
        early_limit = (
            datetime.combine(day, shift.end_time)
            - timedelta(minutes=shift.early_leave_tolerance_minutes)
        )
        if check_out and check_out < early_limit:
            statuses.append("early_leave")
        if check_out is None:
            statuses.append("incomplete")

    return DayRow(cardholder=holder, day=day, check_in=check_in, check_out=check_out, statuses=statuses)
