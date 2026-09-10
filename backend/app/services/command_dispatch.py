"""Choose how a controller/door command reaches the hardware.

`ACP_COMMAND_DISPATCH=direct` (default) keeps the synchronous path (the endpoint
calls the ControllerGateway now). `bridge` enqueues the command in the outbox for
a local bridge daemon to execute and acknowledge later; the endpoint returns
"accepted/queued" without touching hardware.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Controller, GatewayCommand, GatewayCommandType


def bridge_mode() -> bool:
    return get_settings().command_dispatch == "bridge"


def enqueue_command(
    db: Session, *, organization_id: int, controller_id: int, type: GatewayCommandType,
    payload: dict | None = None,
) -> GatewayCommand:
    """Queue a command for the bridge. Each call is a distinct action (fresh
    idempotency key), so retries at the transport layer dedupe but two explicit
    operator actions do not collapse into one."""
    # Import here to avoid a circular import (gateway_outbox imports models only).
    from app.services import gateway_outbox

    key = f"{type.value}:{controller_id}:{uuid.uuid4().hex}"
    return gateway_outbox.enqueue(
        db, organization_id=organization_id, controller_id=controller_id,
        type=type, idempotency_key=key, payload=payload,
    )


def revoke_card_from_boards(
    db: Session, *, organization_id: int, card_number: str
) -> list[GatewayCommand]:
    """Push a card revocation to the offline board caches, automatically.

    A deactivated or deleted credential is already denied online by the access
    engine, but a board that decides offline keeps the card in its own cache
    until told otherwise. In ``bridge`` dispatch we enqueue a ``REVOKE_CARD`` for
    **every** controller in the organization so no board can still admit it; the
    bridge treats removing an absent card as a no-op, so this is safe to fan out.

    In ``direct`` dispatch there is no offline board cache to reconcile (the
    simulated gateway defers every decision to the platform), so this is a no-op
    and returns an empty list.
    """
    if not bridge_mode():
        return []
    controller_ids = db.execute(
        select(Controller.id).where(Controller.organization_id == organization_id)
    ).scalars().all()
    return [
        enqueue_command(
            db, organization_id=organization_id, controller_id=cid,
            type=GatewayCommandType.REVOKE_CARD, payload={"card_number": card_number},
        )
        for cid in controller_ids
    ]
