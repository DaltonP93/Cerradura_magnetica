from datetime import datetime

from pydantic import BaseModel, Field

from app.models.base import EventType
from app.schemas.common import ORMModel


class EventOut(ORMModel):
    id: int
    type: EventType
    controller_id: int | None
    door_id: int | None
    cardholder_id: int | None
    credential_id: int | None
    message: str
    details: dict | None
    occurred_at: datetime


class SwipeRequest(BaseModel):
    """Simulates (or reports) a credential presented at a door reader."""

    door_id: int
    card_number: str = Field(min_length=1, max_length=50)
    pin: str | None = None


class SwipeResult(BaseModel):
    granted: bool
    reason: str | None = None
    cardholder_id: int | None = None
    event_id: int


class AuditLogOut(ORMModel):
    id: int
    organization_id: int | None
    user_id: int | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict | None
    ip_address: str | None
    created_at: datetime


class DashboardStats(BaseModel):
    controllers_total: int
    controllers_online: int
    doors_total: int
    cardholders_total: int
    cardholders_active: int
    events_today: int
    access_granted_today: int
    access_denied_today: int
    alarms_today: int
    recent_events: list[EventOut]
