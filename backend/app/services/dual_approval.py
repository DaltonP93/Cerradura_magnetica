"""Two-person rule for opening critical doors.

A door flagged ``requires_dual_approval`` cannot be opened remotely by a single
operator. One operator creates a pending :class:`DoorOpenRequest`; a second,
distinct operator approves it, and only that approval drives the gateway open
command. The approval transition is an atomic compare-and-set so two racing
approvers can never both trigger a physical open.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DoorOpenRequest, DoorOpenRequestStatus


class DualApprovalError(Exception):
    """A dual-approval request could not be created or approved."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def create_request(
    db: Session, *, org_id: int, door_id: int, controller_id: int, requested_by_id: int,
    reason: str | None = None,
) -> DoorOpenRequest:
    """Create a pending open request, refusing a duplicate active one."""
    now = datetime.now(UTC)
    existing = _active_pending(db, org_id=org_id, door_id=door_id, now=now)
    if existing is not None:
        raise DualApprovalError(
            "An open request for this door is already awaiting approval.",
            status_code=409,
        )
    ttl = get_settings().dual_approval_ttl_seconds
    request = DoorOpenRequest(
        organization_id=org_id,
        door_id=door_id,
        controller_id=controller_id,
        requested_by_id=requested_by_id,
        status=DoorOpenRequestStatus.PENDING,
        reason=reason,
        expires_at=now + timedelta(seconds=ttl),
    )
    db.add(request)
    db.flush()
    return request


def _active_pending(db: Session, *, org_id: int, door_id: int, now: datetime) -> DoorOpenRequest | None:
    stmt = (
        DoorOpenRequest.__table__.select()
        .where(
            DoorOpenRequest.organization_id == org_id,
            DoorOpenRequest.door_id == door_id,
            DoorOpenRequest.status == DoorOpenRequestStatus.PENDING,
        )
    )
    for row in db.execute(stmt).mappings():
        if _as_utc(row["expires_at"]) > now:
            return db.get(DoorOpenRequest, row["id"])
    return None


def claim_for_approval(
    db: Session, *, request: DoorOpenRequest, approver_id: int
) -> None:
    """Atomically transition PENDING -> EXECUTED for this approver.

    The row is optimistically marked executed; :func:`mark_failed` reverts it to
    FAILED if the subsequent gateway command does not succeed. Raises on any
    condition that forbids approval (self-approval, expiry, already resolved).
    """
    now = datetime.now(UTC)
    if request.requested_by_id is not None and request.requested_by_id == approver_id:
        raise DualApprovalError(
            "The operator who requested the open cannot approve it.", status_code=403
        )
    if request.status != DoorOpenRequestStatus.PENDING:
        raise DualApprovalError("Request is no longer pending.", status_code=409)
    if _as_utc(request.expires_at) <= now:
        # Best-effort mark as expired for accurate history.
        db.execute(
            update(DoorOpenRequest)
            .where(
                DoorOpenRequest.id == request.id,
                DoorOpenRequest.status == DoorOpenRequestStatus.PENDING,
            )
            .values(status=DoorOpenRequestStatus.EXPIRED, resolved_at=now)
            .execution_options(synchronize_session=False)
        )
        raise DualApprovalError("Request has expired.", status_code=410)

    # Compare-and-set: only one approver may win the transition out of PENDING.
    result = db.execute(
        update(DoorOpenRequest)
        .where(
            DoorOpenRequest.id == request.id,
            DoorOpenRequest.status == DoorOpenRequestStatus.PENDING,
            DoorOpenRequest.expires_at > now,
        )
        .values(
            status=DoorOpenRequestStatus.EXECUTED,
            approved_by_id=approver_id,
            resolved_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise DualApprovalError(
            "Request could not be approved (already resolved or expired).",
            status_code=409,
        )
    db.refresh(request)


def mark_failed(db: Session, *, request: DoorOpenRequest) -> None:
    """Roll the claimed request back to FAILED after a gateway command failed."""
    request.status = DoorOpenRequestStatus.FAILED
    db.flush()


def reject(db: Session, *, request: DoorOpenRequest) -> None:
    now = datetime.now(UTC)
    result = db.execute(
        update(DoorOpenRequest)
        .where(
            DoorOpenRequest.id == request.id,
            DoorOpenRequest.status == DoorOpenRequestStatus.PENDING,
        )
        .values(status=DoorOpenRequestStatus.REJECTED, resolved_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise DualApprovalError("Only a pending request can be rejected.", status_code=409)
    db.refresh(request)
