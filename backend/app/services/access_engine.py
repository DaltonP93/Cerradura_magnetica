"""Access decision engine.

Given a credential presented at a door, decides whether access is granted,
mirroring the rules of the original L04 desktop software: credential state,
cardholder validity window, access levels (door + schedule), holidays and
door mode.
"""
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.masking import mask_card
from app.models import (
    AccessLevel,
    Cardholder,
    Credential,
    CredentialType,
    DeniedReason,
    Door,
    DoorMode,
    EventType,
    Holiday,
    Schedule,
)
from app.services.events import record_event


@dataclass
class AccessDecision:
    granted: bool
    reason: DeniedReason | None = None
    cardholder: Cardholder | None = None
    credential: Credential | None = None


# Credential types that require a PIN as a second (or sole) factor.
_PIN_REQUIRED = frozenset({CredentialType.CARD_PLUS_PIN, CredentialType.PIN})


def _pin_matches(presented: str | None, stored: str | None) -> bool:
    """Constant-time PIN comparison; a missing PIN on either side never matches."""
    if not presented or not stored:
        return False
    return secrets.compare_digest(presented, stored)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize naive datetimes (SQLite) to aware UTC for safe comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _local_now(door: Door, now: datetime) -> datetime:
    """Schedules are evaluated in the site's local timezone."""
    tz_name = "UTC"
    site = door.controller.site if door.controller else None
    if site and site.timezone:
        tz_name = site.timezone
    try:
        return now.astimezone(ZoneInfo(tz_name))
    except (KeyError, ValueError):
        return now.astimezone(UTC)


def _schedule_allows(db: Session, schedule: Schedule, org_id: int, local_now: datetime) -> bool:
    if not schedule.allow_on_holidays:
        is_holiday = (
            db.execute(
                select(Holiday.id).where(
                    Holiday.organization_id == org_id, Holiday.date == local_now.date()
                )
            ).first()
            is not None
        )
        if is_holiday:
            return False
    weekday = local_now.weekday()  # 0=Monday
    current = local_now.time()
    return any(
        iv.day_of_week == weekday and iv.start_time <= current <= iv.end_time
        for iv in schedule.intervals
    )


def evaluate_access(
    db: Session,
    *,
    organization_id: int,
    door: Door,
    card_number: str,
    pin: str | None = None,
    now: datetime | None = None,
) -> AccessDecision:
    now = now or datetime.now(UTC)

    credential = db.execute(
        select(Credential)
        .options(selectinload(Credential.cardholder))
        .where(
            Credential.organization_id == organization_id,
            Credential.card_number == card_number,
        )
    ).scalar_one_or_none()
    if credential is None:
        return AccessDecision(False, DeniedReason.UNKNOWN_CREDENTIAL)
    if not credential.is_active:
        return AccessDecision(False, DeniedReason.CREDENTIAL_INACTIVE, credential.cardholder, credential)
    # A PIN is mandatory for both card+PIN and PIN-only credentials. Without
    # this, a PIN-only credential would be granted on the card number alone,
    # bypassing its second factor (invariant #3).
    if credential.type in _PIN_REQUIRED and not _pin_matches(pin, credential.pin):
        return AccessDecision(False, DeniedReason.WRONG_PIN, credential.cardholder, credential)

    holder = credential.cardholder
    if not holder.is_active:
        return AccessDecision(False, DeniedReason.CARDHOLDER_INACTIVE, holder, credential)
    valid_from, valid_to = _as_utc(holder.valid_from), _as_utc(holder.valid_to)
    if (valid_from and now < valid_from) or (valid_to and now > valid_to):
        return AccessDecision(False, DeniedReason.OUT_OF_VALIDITY, holder, credential)

    if door.mode == DoorMode.NORMALLY_OPEN:
        return AccessDecision(True, None, holder, credential)
    if door.mode == DoorMode.NORMALLY_CLOSED:
        return AccessDecision(False, DeniedReason.DOOR_LOCKED, holder, credential)

    levels: list[AccessLevel] = [
        lvl
        for lvl in db.execute(
            select(AccessLevel)
            .options(selectinload(AccessLevel.door_rules))
            .join(AccessLevel.cardholders)
            .where(Cardholder.id == holder.id, AccessLevel.organization_id == organization_id)
        )
        .scalars()
        .all()
    ]
    door_rules = [rule for lvl in levels for rule in lvl.door_rules if rule.door_id == door.id]
    if not door_rules:
        return AccessDecision(False, DeniedReason.NO_ACCESS_LEVEL, holder, credential)

    local_now = _local_now(door, now)
    schedule_failed = False
    for rule in door_rules:
        if rule.schedule_id is None:
            return AccessDecision(True, None, holder, credential)  # 24/7 rule
        schedule = db.get(Schedule, rule.schedule_id)
        if schedule and _schedule_allows(db, schedule, organization_id, local_now):
            return AccessDecision(True, None, holder, credential)
        schedule_failed = True

    reason = DeniedReason.OUT_OF_SCHEDULE if schedule_failed else DeniedReason.NO_ACCESS_LEVEL
    return AccessDecision(False, reason, holder, credential)


def process_swipe(
    db: Session,
    *,
    organization_id: int,
    door: Door,
    card_number: str,
    pin: str | None = None,
    now: datetime | None = None,
) -> tuple[AccessDecision, int]:
    """Evaluate a swipe, persist the resulting event, return (decision, event_id)."""
    decision = evaluate_access(
        db,
        organization_id=organization_id,
        door=door,
        card_number=card_number,
        pin=pin,
        now=now,
    )
    holder = decision.cardholder
    if decision.granted:
        message = f"Access granted to {holder.full_name} at {door.name}" if holder else f"Access granted at {door.name}"
        event_type = EventType.ACCESS_GRANTED
    else:
        who = holder.full_name if holder else f"card {mask_card(card_number)}"
        message = f"Access denied to {who} at {door.name} ({decision.reason.value if decision.reason else 'unknown'})"
        event_type = EventType.ACCESS_DENIED

    event = record_event(
        db,
        organization_id=organization_id,
        type=event_type,
        message=message,
        controller_id=door.controller_id,
        door_id=door.id,
        cardholder_id=holder.id if holder else None,
        credential_id=decision.credential.id if decision.credential else None,
        details={"card_number": mask_card(card_number), "reason": decision.reason.value if decision.reason else None},
    )
    return decision, event.id
