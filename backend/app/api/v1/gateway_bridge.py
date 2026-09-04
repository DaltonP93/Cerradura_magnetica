"""Bridge-facing API for the local gateway daemon (Fase 3).

Admins register a bridge with its client-certificate fingerprint; the bridge
then authenticates every request via mTLS (terminated at the edge, which passes
the verified fingerprint in a trusted header) and pulls/acks commands scoped to
its own organization.
"""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.config import get_settings
from app.core.deps import DbSession, OrgId, require_roles
from app.models import GatewayBridge, GatewayCommand, GatewayCommandStatus, User, UserRole
from app.schemas.common import Page
from app.schemas.gateway import (
    AckRequest,
    ClaimRequest,
    GatewayBridgeCreate,
    GatewayBridgeOut,
    GatewayCommandOut,
)
from app.services import gateway_effects, gateway_outbox
from app.services.audit import record_audit

router = APIRouter(prefix="/gateway", tags=["gateway-bridge"])

Admin = Depends(require_roles(UserRole.ADMIN))


def normalize_fingerprint(value: str) -> str:
    """Lowercase and strip separators so ``AA:BB..`` and ``aabb..`` compare equal."""
    return "".join(ch for ch in value.strip().lower() if ch not in ":- ")


def get_current_bridge(request: Request, db: DbSession) -> GatewayBridge:
    """Authenticate a bridge from the edge-provided client-cert fingerprint."""
    header = get_settings().bridge_cert_header
    raw = request.headers.get(header)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bridge client certificate required")
    fingerprint = normalize_fingerprint(raw)
    bridge = db.execute(
        select(GatewayBridge).where(GatewayBridge.cert_fingerprint == fingerprint)
    ).scalar_one_or_none()
    if bridge is None or not bridge.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or inactive bridge")
    return bridge


CurrentBridge = Annotated[GatewayBridge, Depends(get_current_bridge)]


# --- Admin: bridge registration ----------------------------------------------
@router.post("/bridges", response_model=GatewayBridgeOut, status_code=status.HTTP_201_CREATED)
def register_bridge(
    body: GatewayBridgeCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    fingerprint = normalize_fingerprint(body.cert_fingerprint)
    if not fingerprint:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid certificate fingerprint")
    if db.execute(
        select(GatewayBridge).where(GatewayBridge.cert_fingerprint == fingerprint)
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "A bridge with this fingerprint already exists")
    bridge = GatewayBridge(
        organization_id=org_id, name=body.name, cert_fingerprint=fingerprint, is_active=True
    )
    db.add(bridge)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="gateway_bridge",
                 resource_id=bridge.id, request=request, organization_id=org_id)
    db.commit()
    return bridge


@router.get("/bridges", response_model=Page[GatewayBridgeOut])
def list_bridges(
    db: DbSession, org_id: OrgId, actor: User = Admin,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = (
        select(GatewayBridge)
        .where(GatewayBridge.organization_id == org_id)
        .order_by(GatewayBridge.name)
    )
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


# --- Bridge: claim / acknowledge commands -------------------------------------
@router.post("/commands/claim", response_model=list[GatewayCommandOut])
def claim_commands(body: ClaimRequest, db: DbSession, bridge: CurrentBridge):
    commands = gateway_outbox.claim(
        db,
        organization_id=bridge.organization_id,
        worker_token=body.worker_token,
        controller_id=body.controller_id,
        lease_seconds=body.lease_seconds,
        limit=body.limit,
    )
    bridge.last_seen_at = datetime.now(UTC)
    db.commit()
    return commands


@router.post("/commands/{command_id}/ack", response_model=GatewayCommandOut)
def acknowledge_command(command_id: int, body: AckRequest, db: DbSession, bridge: CurrentBridge):
    command = get_or_404(db, GatewayCommand, command_id, bridge.organization_id)
    was_terminal = command.status in (GatewayCommandStatus.SUCCEEDED, GatewayCommandStatus.FAILED)
    try:
        gateway_outbox.acknowledge(
            db, command=command, worker_token=body.worker_token,
            success=body.success, result=body.result, error=body.error,
        )
    except gateway_outbox.OutboxError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    # Apply the platform-side effect exactly once, on the terminal transition.
    now_terminal = command.status in (GatewayCommandStatus.SUCCEEDED, GatewayCommandStatus.FAILED)
    if not was_terminal and now_terminal:
        gateway_effects.apply_outcome(
            db, command=command, success=command.status == GatewayCommandStatus.SUCCEEDED
        )
    bridge.last_seen_at = datetime.now(UTC)
    db.commit()
    db.refresh(command)
    return command
