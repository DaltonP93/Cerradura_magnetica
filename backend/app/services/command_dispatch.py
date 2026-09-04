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
