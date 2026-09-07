"""Choose how a controller/door command reaches the hardware.

`ACP_COMMAND_DISPATCH=direct` (default) keeps the synchronous path (the endpoint
calls the ControllerGateway now). `bridge` enqueues the command in the outbox for
a local bridge daemon to execute and acknowledge later; the endpoint returns
"accepted/queued" without touching hardware.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import GatewayCommand, GatewayCommandType


def bridge_mode() -> bool:
    return get_settings().command_dispatch == "bridge"


def enqueue_command(
    db: Session, *, organization_id: int, controller_id: int, type: GatewayCommandType,
    payload: dict | None = None, idempotency_key: str | None = None,
) -> GatewayCommand:
    """Queue a command for the bridge.

    F-11: when the caller supplies ``idempotency_key`` (e.g. a client's
    ``Idempotency-Key`` header on a remote open), it becomes the outbox key, so a
    double-submit/retry collapses onto the **same** command instead of pulsing
    the door twice. Without it a fresh uuid is used, so two distinct operator
    actions never collapse into one.
    """
    # Import here to avoid a circular import (gateway_outbox imports models only).
    from app.services import gateway_outbox

    suffix = idempotency_key if idempotency_key else uuid.uuid4().hex
    key = f"{type.value}:{controller_id}:{suffix}"
    return gateway_outbox.enqueue(
        db, organization_id=organization_id, controller_id=controller_id,
        type=type, idempotency_key=key, payload=payload,
    )
