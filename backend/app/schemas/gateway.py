from datetime import datetime

from pydantic import BaseModel, Field

from app.models.base import GatewayCommandStatus, GatewayCommandType
from app.schemas.common import ORMModel


# --- Bridge registration (admin) ---
class GatewayBridgeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cert_fingerprint: str = Field(min_length=8, max_length=128)


class GatewayBridgeOut(ORMModel):
    id: int
    organization_id: int
    name: str
    cert_fingerprint: str
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime


# --- Commands (bridge-facing) ---
class GatewayCommandOut(ORMModel):
    id: int
    controller_id: int
    type: GatewayCommandType
    payload: dict | None
    status: GatewayCommandStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    result: dict | None
    leased_until: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ClaimRequest(BaseModel):
    worker_token: str = Field(min_length=1, max_length=64)
    controller_id: int | None = None
    lease_seconds: int = Field(default=60, ge=1, le=3600)
    limit: int = Field(default=10, ge=1, le=100)


class AckRequest(BaseModel):
    worker_token: str = Field(min_length=1, max_length=64)
    success: bool
    result: dict | None = None
    error: str | None = Field(default=None, max_length=500)
