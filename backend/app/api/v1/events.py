import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.core.masking import mask_card
from app.models import Door, Event, EventType, User, UserRole
from app.schemas.common import Page
from app.schemas.events import EventOut, SwipeRequest, SwipeResult
from app.services.access_engine import process_swipe
from app.services.audit import record_audit

router = APIRouter(prefix="/events", tags=["events"])

Operator = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))

# Upper bound on a single CSV export, so an unbounded range can't stream forever.
EXPORT_MAX_ROWS = 100_000


def _event_filters(stmt, *, type, door_id, controller_id, cardholder_id, date_from, date_to):
    """Apply the shared event query filters (used by the list and the export)."""
    if type is not None:
        stmt = stmt.where(Event.type == type)
    if door_id is not None:
        stmt = stmt.where(Event.door_id == door_id)
    if controller_id is not None:
        stmt = stmt.where(Event.controller_id == controller_id)
    if cardholder_id is not None:
        stmt = stmt.where(Event.cardholder_id == cardholder_id)
    if date_from is not None:
        stmt = stmt.where(Event.occurred_at >= date_from.replace(tzinfo=None))
    if date_to is not None:
        stmt = stmt.where(Event.occurred_at <= date_to.replace(tzinfo=None))
    return stmt


@router.get("", response_model=Page[EventOut], dependencies=[AnyUser])
def list_events(
    db: DbSession,
    org_id: OrgId,
    type: EventType | None = None,
    door_id: int | None = None,
    controller_id: int | None = None,
    cardholder_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = (
        select(Event)
        .where(Event.organization_id == org_id)
        .order_by(Event.occurred_at.desc(), Event.id.desc())
    )
    stmt = _event_filters(
        stmt, type=type, door_id=door_id, controller_id=controller_id,
        cardholder_id=cardholder_id, date_from=date_from, date_to=date_to,
    )
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/export.csv", dependencies=[AnyUser])
def export_events_csv(
    db: DbSession,
    org_id: OrgId,
    type: EventType | None = None,
    door_id: int | None = None,
    controller_id: int | None = None,
    cardholder_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    """Stream the full event report (all matching rows, not just one page) as CSV.

    Same filters as the list endpoint. Only non-sensitive columns are emitted —
    no raw ``details`` blob and no card numbers (invariant #6). Capped at
    ``EXPORT_MAX_ROWS`` rows.
    """
    stmt = (
        select(
            Event.id, Event.occurred_at, Event.type, Event.message,
            Event.controller_id, Event.door_id, Event.cardholder_id,
        )
        .where(Event.organization_id == org_id)
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(EXPORT_MAX_ROWS)
    )
    stmt = _event_filters(
        stmt, type=type, door_id=door_id, controller_id=controller_id,
        cardholder_id=cardholder_id, date_from=date_from, date_to=date_to,
    )
    rows = db.execute(stmt).all()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "occurred_at", "type", "message", "controller_id", "door_id", "cardholder_id"]
        )
        for r in rows:
            writer.writerow([
                r.id,
                r.occurred_at.isoformat() if r.occurred_at else "",
                r.type.value if r.type else "",
                r.message,
                r.controller_id if r.controller_id is not None else "",
                r.door_id if r.door_id is not None else "",
                r.cardholder_id if r.cardholder_id is not None else "",
            ])
        buf.seek(0)
        yield buf.getvalue()

    filename = f"eventos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/swipe", response_model=SwipeResult)
def swipe(body: SwipeRequest, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator):
    """Evaluate a credential at a door.

    Used by the built-in simulator UI and as the callback endpoint for
    gateway daemons that relay real reader swipes to the platform.
    """
    door = get_or_404(db, Door, body.door_id, org_id)
    decision, event_id = process_swipe(
        db, organization_id=org_id, door=door, card_number=body.card_number, pin=body.pin
    )
    record_audit(db, user=actor, action="swipe_test", resource_type="door",
                 resource_id=door.id, request=request, organization_id=org_id,
                 details={"granted": decision.granted, "card": mask_card(body.card_number)})
    db.commit()
    return SwipeResult(
        granted=decision.granted,
        reason=decision.reason.value if decision.reason else None,
        cardholder_id=decision.cardholder.id if decision.cardholder else None,
        event_id=event_id,
    )
