"""Apply the platform-side effect of a bridge command once it is acknowledged.

In `bridge` dispatch the endpoint only queues the command, so the physical
outcome (a door actually opening, a board being reachable) is not known until
the bridge reports back. This maps a terminal command to its platform effect:
the REMOTE_OPEN event for a door, the online/offline status for a ping. It must
be invoked exactly once, when the command transitions to a terminal status.
"""
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import (
    Controller,
    ControllerStatus,
    DoorOpenRequest,
    DoorOpenRequestStatus,
    EventType,
    GatewayCommand,
    GatewayCommandType,
)
from app.services.events import record_event


def apply_outcome(db: Session, *, command: GatewayCommand, success: bool) -> None:
    if command.type == GatewayCommandType.OPEN_DOOR:
        payload = command.payload or {}
        request_id = payload.get("open_request_id")
        if request_id is not None:
            _finalize_dual_approval(db, command=command, request_id=request_id, success=success)
            return
        if not success:
            return
        record_event(
            db,
            organization_id=command.organization_id,
            type=EventType.REMOTE_OPEN,
            message=f"Door opened via local bridge (command #{command.id})",
            controller_id=command.controller_id,
            door_id=payload.get("door_id"),
            details={"dispatch": "bridge", "requested_by_id": payload.get("requested_by_id")},
        )
    elif command.type == GatewayCommandType.PING:
        controller = db.get(Controller, command.controller_id)
        if controller is None:
            return
        previous = controller.status
        controller.status = ControllerStatus.ONLINE if success else ControllerStatus.OFFLINE
        if success:
            controller.last_seen_at = datetime.now(UTC)
        if controller.status != previous:
            record_event(
                db,
                organization_id=command.organization_id,
                type=EventType.CONTROLLER_ONLINE if success else EventType.CONTROLLER_OFFLINE,
                message=f"Controller {controller.name} is {controller.status.value}",
                controller_id=controller.id,
            )
    # SYNC_TIME / SYNC_PERMISSIONS carry no extra platform effect (already audited
    # at enqueue); their completion is recorded on the command row itself.


def _finalize_dual_approval(
    db: Session, *, command: GatewayCommand, request_id: int, success: bool
) -> None:
    """Resolve a DISPATCHED dual-approval request once the bridge reports back."""
    req = db.get(DoorOpenRequest, request_id)
    # Only the DISPATCHED -> terminal transition applies (idempotent).
    if req is None or req.status != DoorOpenRequestStatus.DISPATCHED:
        return
    payload = command.payload or {}
    now = datetime.now(UTC)
    req.status = DoorOpenRequestStatus.EXECUTED if success else DoorOpenRequestStatus.FAILED
    req.resolved_at = now
    if success:
        record_event(
            db,
            organization_id=command.organization_id,
            type=EventType.REMOTE_OPEN,
            message=f"Door opened under dual approval via local bridge (command #{command.id})",
            controller_id=command.controller_id,
            door_id=payload.get("door_id"),
            details={
                "dispatch": "bridge",
                "dual_approval": True,
                "requested_by_id": payload.get("requested_by_id"),
                "approved_by_id": payload.get("approved_by_id"),
            },
        )
