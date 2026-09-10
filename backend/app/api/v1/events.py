from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
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
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


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
