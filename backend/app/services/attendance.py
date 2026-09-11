"""Attendance report computation (Part 4 of the legacy manual).

For each cardholder and day in the range, punches are gathered from access
events (granted swipes) and manual signs. The first punch of the day is the
check-in and the last one the check-out. The cardholder's shift determines
workdays, expected times and tolerances.

Punches are stored in UTC; the report evaluates them in an explicit timezone
(``timezone``, IANA name, default UTC) so that day boundaries and the shift's
wall-clock times line up with the site's local time — consistent with how the
access engine evaluates schedules in the site's timezone.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

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


def _to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    """Interpret a stored timestamp as UTC and express it as naive local time."""
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.astimezone(tz).replace(tzinfo=None)


def _is_overnight(shift: Shift | None) -> bool:
    """A shift whose end wall-clock time is strictly before its start crosses
    midnight (e.g. 22:00 → 06:00)."""
    return shift is not None and shift.end_time < shift.start_time


def _seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _attribution_date(local_dt: datetime, shift: Shift | None) -> date:
    """Which shift-instance day a punch belongs to.

    Normal shifts attribute a punch to its own calendar day. For an overnight
    shift the instance starts the evening of day D and ends the morning of D+1;
    the "off" period runs from the end time to the start time. Punches in the
    first half of that gap (early morning, including a slightly-late checkout)
    belong to the *previous* day's instance; punches from the midpoint onward
    (afternoon/evening, including a slightly-early check-in) belong to their own
    day. Splitting at the midpoint tolerates arrivals before start and
    departures after end without misattributing them.
    """
    if not _is_overnight(shift):
        return local_dt.date()
    assert shift is not None
    midpoint = (_seconds(shift.end_time) + _seconds(shift.start_time)) // 2
    if _seconds(local_dt.time()) < midpoint:
        return local_dt.date() - timedelta(days=1)
    return local_dt.date()


def compute_attendance(
    db: Session,
    *,
    organization_id: int,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    cardholder_id: int | None = None,
    timezone: str = "UTC",
) -> list[DayRow]:
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Range too large (max {MAX_RANGE_DAYS} days)")
    try:
        tz = ZoneInfo(timezone)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc

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

    # Widen the UTC query window by a day on each side so every punch whose
    # *local* date falls in range is captured regardless of the timezone offset.
    range_start = datetime.combine(date_from - timedelta(days=1), time.min)
    range_end = datetime.combine(date_to + timedelta(days=2), time.min)

    # Punches: granted access events + manual signs, collected per cardholder as
    # local datetimes. Bucketing into shift-instance days happens later, once we
    # know each holder's shift (overnight shifts attribute early-morning punches
    # to the previous day).
    raw_by_holder: dict[int, list[datetime]] = {}
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
        raw_by_holder.setdefault(holder_id, []).append(_to_local(occurred_at, tz))
    signs = db.execute(
        select(ManualSign.cardholder_id, ManualSign.signed_at).where(
            ManualSign.organization_id == organization_id,
            ManualSign.cardholder_id.in_(holder_ids),
            ManualSign.signed_at >= range_start,
            ManualSign.signed_at < range_end,
        )
    )
    for holder_id, signed_at in signs:
        raw_by_holder.setdefault(holder_id, []).append(_to_local(signed_at, tz))

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
        # Bucket this holder's punches into shift-instance days (overnight shifts
        # attribute early-morning punches to the previous day).
        holder_punches: dict[date, list[datetime]] = {}
        for local in raw_by_holder.get(holder.id, []):
            holder_punches.setdefault(_attribution_date(local, shift), []).append(local)
        day = date_from
        while day <= date_to:
            rows.append(_evaluate_day(holder, shift, day, holder_punches, leaves, holidays))
            day += timedelta(days=1)
    return rows


def _evaluate_day(
    holder: Cardholder,
    shift: Shift | None,
    day: date,
    punches: dict[date, list[datetime]],
    leaves: dict[int, list[Leave]],
    holidays: set[date],
) -> DayRow:
    day_punches = sorted(punches.get(day, []))
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
        # For an overnight shift the expected end falls on the following day.
        end_day = day + timedelta(days=1) if _is_overnight(shift) else day
        late_limit = (
            datetime.combine(day, shift.start_time) + timedelta(minutes=shift.late_tolerance_minutes)
        )
        if check_in and check_in > late_limit:
            statuses.append("late")
        early_limit = (
            datetime.combine(end_day, shift.end_time)
            - timedelta(minutes=shift.early_leave_tolerance_minutes)
        )
        if check_out and check_out < early_limit:
            statuses.append("early_leave")
        if check_out is None:
            statuses.append("incomplete")

    return DayRow(cardholder=holder, day=day, check_in=check_in, check_out=check_out, statuses=statuses)
