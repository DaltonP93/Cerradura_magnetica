"""Ingest events reported by a board through the bridge (Fase 5 inbox).

The bridge relays events the board decided or observed on its own — offline
access decisions, door sensors, forced/held-open alarms, controller
online/offline. Each event carries an idempotency key (``event_uid``) so a
redelivery is never double-recorded, and card numbers are masked before storage
(invariant #6). This is the counterpart to the outbox: platform→board commands
vs board→platform events. Recorded events broadcast to live monitors like any
other, once the transaction commits.
"""
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.masking import mask_card
from app.models import Controller, Credential, Door, Event, EventType
from app.services.events import record_event


def ingest_events(db: Session, *, organization_id: int, events: Sequence) -> dict:
    """Record a batch of board events for one organization; return a summary."""
    # Preload the lookups this batch needs, scoped to the organization.
    valid_ids: set[int] = set()
    serial_to_id: dict[str, int] = {}
    for cid, serial in db.execute(
        select(Controller.id, Controller.serial_number).where(
            Controller.organization_id == organization_id
        )
    ):
        valid_ids.add(cid)
        serial_to_id[serial] = cid
    doors: dict[tuple[int, int], int] = {
        (ctrl_id, number): did
        for did, ctrl_id, number in db.execute(
            select(Door.id, Door.controller_id, Door.number).where(
                Door.organization_id == organization_id
            )
        )
    }
    cardholders: dict[str, int] = {
        card: holder_id
        for card, holder_id in db.execute(
            select(Credential.card_number, Credential.cardholder_id).where(
                Credential.organization_id == organization_id
            )
        )
    }
    uids = [e.event_uid for e in events]
    already: set[str] = {
        x
        for (x,) in db.execute(
            select(Event.external_id).where(
                Event.organization_id == organization_id, Event.external_id.in_(uids)
            )
        )
    }

    accepted = 0
    duplicates = 0
    errors: list[dict] = []
    seen: set[str] = set()
    for e in events:
        if e.event_uid in already or e.event_uid in seen:
            duplicates += 1
            continue

        controller_id = e.controller_id if e.controller_id in valid_ids else None
        if controller_id is None and e.controller_serial:
            controller_id = serial_to_id.get(e.controller_serial)
        if controller_id is None:
            errors.append({"event_uid": e.event_uid, "reason": "unknown controller"})
            continue

        try:
            event_type = EventType(e.type)
        except ValueError:
            errors.append({"event_uid": e.event_uid, "reason": f"unknown event type: {e.type}"})
            continue

        door_id = doors.get((controller_id, e.door_number)) if e.door_number else None
        cardholder_id = cardholders.get(e.card_number) if e.card_number else None
        details = dict(e.details or {})
        details["source"] = "board"
        if e.card_number:
            details["card"] = mask_card(e.card_number)  # never store the raw card

        record_event(
            db,
            organization_id=organization_id,
            type=event_type,
            message=e.message or f"{event_type.value} reported by board",
            controller_id=controller_id,
            door_id=door_id,
            cardholder_id=cardholder_id,
            details=details,
            external_id=e.event_uid,
            occurred_at=e.occurred_at,
        )
        seen.add(e.event_uid)
        accepted += 1

    return {"accepted": accepted, "duplicates": duplicates, "errors": errors}
