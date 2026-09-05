"""Command outbox for the local gateway bridge (Fase 3 scaffolding).

Platform-side queue with three operations:

* ``enqueue``  — add a command, idempotent by ``(organization_id,
  idempotency_key)``: a repeated enqueue returns the existing row.
* ``claim``    — a bridge worker atomically leases pending (or lease-expired)
  commands; the compare-and-set guarantees a command is delivered to at most
  one worker at a time.
* ``acknowledge`` — the leasing worker reports success or failure; idempotent
  (a second ack on a terminal command is a no-op), with bounded retries.

No hardware or network here: executing the command against a controller is the
bridge's job.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import GatewayCommand, GatewayCommandStatus, GatewayCommandType

DEFAULT_LEASE_SECONDS = 60


class OutboxError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def enqueue(
    db: Session, *, organization_id: int, controller_id: int, type: GatewayCommandType,
    idempotency_key: str, payload: dict | None = None, max_attempts: int = 5,
) -> GatewayCommand:
    """Queue a command, returning the existing row if the key was already used."""
    existing = db.execute(
        select(GatewayCommand).where(
            GatewayCommand.organization_id == organization_id,
            GatewayCommand.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    command = GatewayCommand(
        organization_id=organization_id,
        controller_id=controller_id,
        idempotency_key=idempotency_key,
        type=type,
        payload=payload,
        status=GatewayCommandStatus.PENDING,
        max_attempts=max_attempts,
    )
    db.add(command)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent enqueue won the unique key; return that row instead.
        db.rollback()
        return db.execute(
            select(GatewayCommand).where(
                GatewayCommand.organization_id == organization_id,
                GatewayCommand.idempotency_key == idempotency_key,
            )
        ).scalar_one()
    return command


def claim(
    db: Session, *, organization_id: int, worker_token: str, controller_id: int | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS, limit: int = 10,
) -> list[GatewayCommand]:
    """Atomically lease up to ``limit`` deliverable commands for a worker."""
    if not worker_token:
        raise OutboxError("worker_token is required", status_code=400)
    now = _now()
    deliverable = or_(
        GatewayCommand.status == GatewayCommandStatus.PENDING,
        and_(
            GatewayCommand.status == GatewayCommandStatus.LEASED,
            GatewayCommand.leased_until < now,
        ),
    )
    stmt = (
        select(GatewayCommand.id)
        .where(GatewayCommand.organization_id == organization_id, deliverable)
        .order_by(GatewayCommand.created_at, GatewayCommand.id)
        .limit(limit)
    )
    if controller_id is not None:
        stmt = stmt.where(GatewayCommand.controller_id == controller_id)

    leased_ids: list[int] = []
    for (command_id,) in db.execute(stmt).all():
        result = db.execute(
            update(GatewayCommand)
            .where(GatewayCommand.id == command_id, deliverable)
            .values(
                status=GatewayCommandStatus.LEASED,
                lease_token=worker_token,
                leased_at=now,
                leased_until=now + timedelta(seconds=lease_seconds),
                attempts=GatewayCommand.attempts + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            leased_ids.append(command_id)
    db.flush()
    if not leased_ids:
        return []
    rows = db.execute(
        select(GatewayCommand).where(GatewayCommand.id.in_(leased_ids))
    ).scalars().all()
    for row in rows:
        db.refresh(row)
    return list(rows)


def acknowledge(
    db: Session, *, command: GatewayCommand, worker_token: str, success: bool,
    result: dict | None = None, error: str | None = None,
) -> GatewayCommand:
    """Report a command's outcome. Idempotent; failures retry until exhausted."""
    # Idempotent: a terminal command is not re-processed.
    if command.status in (GatewayCommandStatus.SUCCEEDED, GatewayCommandStatus.FAILED):
        return command
    if command.status != GatewayCommandStatus.LEASED or command.lease_token != worker_token:
        raise OutboxError("command is not leased by this worker", status_code=409)

    now = _now()
    if success:
        command.status = GatewayCommandStatus.SUCCEEDED
        command.result = result
        command.last_error = None
        command.completed_at = now
    elif command.attempts >= command.max_attempts:
        command.status = GatewayCommandStatus.FAILED
        command.last_error = error
        command.completed_at = now
    else:
        # Return to the queue for another worker/attempt.
        command.status = GatewayCommandStatus.PENDING
        command.last_error = error
    command.lease_token = None
    command.leased_until = None
    db.flush()
    return command
