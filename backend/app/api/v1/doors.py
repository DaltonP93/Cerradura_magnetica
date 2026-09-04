from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import (
    Controller,
    Door,
    DoorOpenRequest,
    DoorOpenRequestStatus,
    EventType,
    GatewayCommandType,
    User,
    UserRole,
)
from app.schemas.common import Page
from app.schemas.infrastructure import (
    CommandResult,
    DoorOpenRequestCreate,
    DoorOpenRequestOut,
    DoorOut,
    DoorUpdate,
)
from app.services import command_dispatch, dual_approval
from app.services.audit import record_audit
from app.services.events import record_event
from app.services.gateway import call_gateway, get_gateway

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


# --- Dual-approval open requests --------------------------------------------
# These collection routes must be declared before ``/{door_id}`` so the literal
# path segment is not captured as a (numeric) door id.
@router.get("/open-requests", response_model=Page[DoorOpenRequestOut], dependencies=[AnyUser])
def list_open_requests(
    db: DbSession,
    org_id: OrgId,
    status_filter: DoorOpenRequestStatus | None = Query(default=None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = (
        select(DoorOpenRequest)
        .where(DoorOpenRequest.organization_id == org_id)
        .order_by(DoorOpenRequest.created_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(DoorOpenRequest.status == status_filter)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/open-requests/{request_id}/approve",
    response_model=DoorOpenRequestOut,
)
def approve_open_request(
    request_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    """Second-operator approval: verifies the two-person rule, then opens.

    The endpoint is synchronous (runs in a worker thread) and commits the
    approval claim to release the DB connection *before* the gateway network
    round-trip, so no transaction is held across the physical command.
    """
    actor_id, actor_name = actor.id, actor.full_name
    bridge = command_dispatch.bridge_mode()
    target = DoorOpenRequestStatus.DISPATCHED if bridge else DoorOpenRequestStatus.EXECUTED
    req = get_or_404(db, DoorOpenRequest, request_id, org_id)
    try:
        dual_approval.claim_for_approval(db, request=req, approver_id=actor_id, target_status=target)
    except dual_approval.DualApprovalError as exc:
        db.commit()  # persist any expiry transition recorded during the check
        raise HTTPException(exc.status_code, exc.message) from exc

    door = get_or_404(db, Door, req.door_id, org_id)
    controller = get_or_404(db, Controller, req.controller_id, org_id)
    req_id, requested_by_id = req.id, req.requested_by_id
    door_id, door_name, controller_id = door.id, door.name, controller.id

    if bridge:
        # Two-person rule satisfied and reserved (DISPATCHED); queue the open for
        # the bridge. The REMOTE_OPEN event and the final EXECUTED/FAILED status
        # are applied when the bridge acknowledges the command.
        command = command_dispatch.enqueue_command(
            db, organization_id=org_id, controller_id=controller_id,
            type=GatewayCommandType.OPEN_DOOR,
            payload={
                "door": door.number, "door_id": door_id,
                "open_request_id": req_id, "requested_by_id": requested_by_id,
                "approved_by_id": actor_id,
            },
        )
        record_audit(
            db, user=actor, action="command:dual_open_approve", resource_type="door",
            resource_id=door_id, request=request, organization_id=org_id,
            details={"request_id": req_id, "requested_by_id": requested_by_id,
                     "queued": True, "command_id": command.id},
        )
        db.commit()
        return db.get(DoorOpenRequest, req_id)

    # Direct path: persist the EXECUTED claim (reserving the request) and release
    # the connection; the ORM objects are detached but keep their loaded columns.
    db.expunge(door)
    db.expunge(controller)
    db.commit()

    result = call_gateway(get_gateway().open_door(controller, door))
    if result.success:
        record_event(
            db,
            organization_id=org_id,
            type=EventType.REMOTE_OPEN,
            message=f"{door_name} opened under dual approval by {actor_name}",
            controller_id=controller_id,
            door_id=door_id,
            details={
                "requested_by_id": requested_by_id,
                "approved_by_id": actor_id,
                "dual_approval": True,
            },
        )
    else:
        failed = db.get(DoorOpenRequest, req_id)
        if failed is not None:
            dual_approval.mark_failed(db, request=failed)
    record_audit(
        db, user=actor, action="command:dual_open_approve", resource_type="door",
        resource_id=door_id, request=request, organization_id=org_id,
        details={"request_id": req_id, "requested_by_id": requested_by_id, "success": result.success},
    )
    db.commit()
    return db.get(DoorOpenRequest, req_id)


@router.post(
    "/open-requests/{request_id}/reject",
    response_model=DoorOpenRequestOut,
)
def reject_open_request(
    request_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    req = get_or_404(db, DoorOpenRequest, request_id, org_id)
    try:
        dual_approval.reject(db, request=req)
    except dual_approval.DualApprovalError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    record_audit(
        db, user=actor, action="command:dual_open_reject", resource_type="door",
        resource_id=req.door_id, request=request, organization_id=org_id,
        details={"request_id": req.id},
    )
    db.commit()
    db.refresh(req)
    return req


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
def open_door(
    door_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    """Remote open — the 'open door' button of the original desktop software.

    Critical doors (``requires_dual_approval``) cannot be opened here; they
    require the two-person request/approve workflow. Synchronous handler: the DB
    connection is released before the gateway network round-trip.
    """
    actor_id, actor_name = actor.id, actor.full_name
    door = get_or_404(db, Door, door_id, org_id)
    if door.requires_dual_approval:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This door requires dual approval; create an open request instead.",
        )
    controller = get_or_404(db, Controller, door.controller_id, org_id)
    door_id_val, door_name, controller_id = door.id, door.name, controller.id

    if command_dispatch.bridge_mode():
        # Queue the pulse for the local bridge; the physical open (and its
        # REMOTE_OPEN event) is recorded when the board reports back.
        command = command_dispatch.enqueue_command(
            db, organization_id=org_id, controller_id=controller_id,
            type=GatewayCommandType.OPEN_DOOR,
            payload={"door": door.number, "door_id": door_id_val, "requested_by_id": actor_id},
        )
        record_audit(db, user=actor, action="command:open_door", resource_type="door",
                     resource_id=door_id_val, request=request, organization_id=org_id,
                     details={"queued": True, "command_id": command.id})
        db.commit()
        return CommandResult(success=True, message="Command queued for the local bridge")

    # Release the connection before the network round-trip; detached objects
    # keep their loaded columns for the gateway call.
    db.expunge(door)
    db.expunge(controller)
    db.commit()

    result = call_gateway(get_gateway().open_door(controller, door))
    if result.success:
        record_event(
            db,
            organization_id=org_id,
            type=EventType.REMOTE_OPEN,
            message=f"{door_name} opened remotely by {actor_name}",
            controller_id=controller_id,
            door_id=door_id_val,
            details={"user_id": actor_id},
        )
    record_audit(db, user=actor, action="command:open_door", resource_type="door",
                 resource_id=door_id_val, request=request, organization_id=org_id,
                 details={"success": result.success})
    db.commit()
    return CommandResult(success=result.success, message=result.message)


@router.post("/{door_id}/open-requests", response_model=DoorOpenRequestOut, status_code=201)
def create_open_request(
    door_id: int, body: DoorOpenRequestCreate, db: DbSession, org_id: OrgId,
    request: Request, actor: User = Operator,
):
    """First operator initiates a dual-approval remote open for a critical door."""
    door = get_or_404(db, Door, door_id, org_id)
    if not door.requires_dual_approval:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This door does not require dual approval; use /open.",
        )
    try:
        req = dual_approval.create_request(
            db, org_id=org_id, door_id=door.id, controller_id=door.controller_id,
            requested_by_id=actor.id, reason=body.reason,
        )
    except dual_approval.DualApprovalError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    record_audit(
        db, user=actor, action="command:dual_open_request", resource_type="door",
        resource_id=door.id, request=request, organization_id=org_id,
        details={"request_id": req.id, "reason": body.reason},
    )
    db.commit()
    db.refresh(req)
    return req
