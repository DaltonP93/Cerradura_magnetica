from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import Controller, Door, EventType, User, UserRole
from app.schemas.common import Page
from app.schemas.infrastructure import CommandResult, DoorOut, DoorUpdate
from app.services.audit import record_audit
from app.services.events import record_event
from app.services.gateway import get_gateway

router = APIRouter(prefix="/doors", tags=["doors"])

Admin = Depends(require_roles(UserRole.ADMIN))
Operator = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


@router.get("", response_model=Page[DoorOut], dependencies=[AnyUser])
def list_doors(
    db: DbSession,
    org_id: OrgId,
    controller_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(Door).where(Door.organization_id == org_id).order_by(Door.controller_id, Door.number)
    if controller_id is not None:
        stmt = stmt.where(Door.controller_id == controller_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{door_id}", response_model=DoorOut, dependencies=[AnyUser])
def get_door(door_id: int, db: DbSession, org_id: OrgId):
    return get_or_404(db, Door, door_id, org_id)


@router.patch("/{door_id}", response_model=DoorOut)
def update_door(
    door_id: int, body: DoorUpdate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    door = get_or_404(db, Door, door_id, org_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(door, field, value)
    record_audit(db, user=actor, action="update", resource_type="door",
                 resource_id=door.id, request=request, organization_id=org_id)
    db.commit()
    return door


@router.post("/{door_id}/open", response_model=CommandResult)
async def open_door(
    door_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    """Remote open — the 'open door' button of the original desktop software."""
    door = get_or_404(db, Door, door_id, org_id)
    controller = get_or_404(db, Controller, door.controller_id, org_id)
    result = await get_gateway().open_door(controller, door)
    if result.success:
        record_event(
            db,
            organization_id=org_id,
            type=EventType.REMOTE_OPEN,
            message=f"{door.name} opened remotely by {actor.full_name}",
            controller_id=controller.id,
            door_id=door.id,
            details={"user_id": actor.id},
        )
    record_audit(db, user=actor, action="command:open_door", resource_type="door",
                 resource_id=door.id, request=request, organization_id=org_id,
                 details={"success": result.success})
    db.commit()
    return CommandResult(success=result.success, message=result.message)
