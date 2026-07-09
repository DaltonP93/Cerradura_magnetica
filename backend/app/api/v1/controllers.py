from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import (
    Controller,
    ControllerStatus,
    Credential,
    Door,
    EventType,
    Site,
    User,
    UserRole,
)
from app.schemas.common import Message, Page
from app.schemas.infrastructure import CommandResult, ControllerCreate, ControllerOut, ControllerUpdate
from app.services.audit import record_audit
from app.services.events import record_event
from app.services.gateway import get_gateway

router = APIRouter(prefix="/controllers", tags=["controllers"])

Admin = Depends(require_roles(UserRole.ADMIN))
Operator = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


def _controller_stmt(org_id: int):
    return (
        select(Controller)
        .options(selectinload(Controller.doors))
        .where(Controller.organization_id == org_id)
    )


@router.get("", response_model=Page[ControllerOut], dependencies=[AnyUser])
def list_controllers(
    db: DbSession,
    org_id: OrgId,
    site_id: int | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = _controller_stmt(org_id).order_by(Controller.name)
    if site_id is not None:
        stmt = stmt.where(Controller.site_id == site_id)
    if q:
        stmt = stmt.where(Controller.name.ilike(f"%{q}%") | Controller.serial_number.ilike(f"%{q}%"))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ControllerOut, status_code=status.HTTP_201_CREATED)
def create_controller(
    body: ControllerCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    if db.execute(
        select(Controller).where(Controller.serial_number == body.serial_number)
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Serial number already registered")
    if body.site_id is not None:
        get_or_404(db, Site, body.site_id, org_id)

    controller = Controller(organization_id=org_id, **body.model_dump())
    db.add(controller)
    db.flush()
    # The L04 board exposes a fixed set of doors; create them eagerly so they
    # can be renamed/configured immediately, matching the desktop software.
    for n in range(1, controller.door_count + 1):
        db.add(Door(organization_id=org_id, controller_id=controller.id, number=n, name=f"{body.name} - Door {n}"))
    record_audit(db, user=actor, action="create", resource_type="controller",
                 resource_id=controller.id, request=request, organization_id=org_id)
    db.commit()
    return db.execute(_controller_stmt(org_id).where(Controller.id == controller.id)).scalar_one()


@router.get("/{controller_id}", response_model=ControllerOut, dependencies=[AnyUser])
def get_controller(controller_id: int, db: DbSession, org_id: OrgId):
    controller = db.execute(
        _controller_stmt(org_id).where(Controller.id == controller_id)
    ).scalar_one_or_none()
    if controller is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Controller not found")
    return controller


@router.patch("/{controller_id}", response_model=ControllerOut)
def update_controller(
    controller_id: int, body: ControllerUpdate, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Admin,
):
    controller = get_or_404(db, Controller, controller_id, org_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("site_id") is not None:
        get_or_404(db, Site, data["site_id"], org_id)
    for field, value in data.items():
        setattr(controller, field, value)
    record_audit(db, user=actor, action="update", resource_type="controller",
                 resource_id=controller.id, request=request, organization_id=org_id)
    db.commit()
    return db.execute(_controller_stmt(org_id).where(Controller.id == controller.id)).scalar_one()


@router.delete("/{controller_id}", response_model=Message)
def delete_controller(
    controller_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    controller = get_or_404(db, Controller, controller_id, org_id)
    db.delete(controller)
    record_audit(db, user=actor, action="delete", resource_type="controller",
                 resource_id=controller_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Controller deleted")


@router.post("/{controller_id}/ping", response_model=CommandResult)
async def ping_controller(
    controller_id: int, db: DbSession, org_id: OrgId, actor: User = Operator
):
    controller = get_or_404(db, Controller, controller_id, org_id)
    result = await get_gateway().ping(controller)
    previous = controller.status
    controller.status = ControllerStatus.ONLINE if result.success else ControllerStatus.OFFLINE
    if result.success:
        controller.last_seen_at = datetime.now(UTC)
    if controller.status != previous:
        record_event(
            db,
            organization_id=org_id,
            type=EventType.CONTROLLER_ONLINE if result.success else EventType.CONTROLLER_OFFLINE,
            message=f"Controller {controller.name} is {controller.status.value}",
            controller_id=controller.id,
        )
    db.commit()
    return CommandResult(success=result.success, message=result.message)


@router.post("/{controller_id}/sync-time", response_model=CommandResult)
async def sync_controller_time(
    controller_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    controller = get_or_404(db, Controller, controller_id, org_id)
    result = await get_gateway().sync_time(controller)
    record_audit(db, user=actor, action="command:sync_time", resource_type="controller",
                 resource_id=controller.id, request=request, organization_id=org_id,
                 details={"success": result.success})
    db.commit()
    return CommandResult(success=result.success, message=result.message)


@router.post("/{controller_id}/sync-permissions", response_model=CommandResult)
async def sync_controller_permissions(
    controller_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    """Push all active card permissions for this board so it can decide offline."""
    controller = get_or_404(db, Controller, controller_id, org_id)
    door_ids = {d.id: d.number for d in controller.doors}

    cards: dict[str, dict] = {}
    creds = db.execute(
        select(Credential)
        .options(selectinload(Credential.cardholder))
        .where(Credential.organization_id == org_id, Credential.is_active.is_(True))
    ).scalars()
    for cred in creds:
        holder = cred.cardholder
        if not holder.is_active:
            continue
        doors = sorted(
            {
                door_ids[rule.door_id]
                for level in holder.access_levels
                for rule in level.door_rules
                if rule.door_id in door_ids
            }
        )
        if not doors:
            continue
        cards[cred.card_number] = {
            "card_number": cred.card_number,
            "doors": doors,
            "valid_from": holder.valid_from.date() if holder.valid_from else None,
            "valid_to": holder.valid_to.date() if holder.valid_to else None,
        }

    result = await get_gateway().sync_permissions(controller, list(cards.values()))
    record_audit(db, user=actor, action="command:sync_permissions", resource_type="controller",
                 resource_id=controller.id, request=request, organization_id=org_id,
                 details={"cards": len(cards), "success": result.success})
    db.commit()
    return CommandResult(success=result.success, message=result.message)
