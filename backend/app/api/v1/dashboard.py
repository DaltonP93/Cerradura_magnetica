from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.deps import DbSession, OrgId, require_roles
from app.models import Cardholder, Controller, ControllerStatus, Door, Event, EventType, UserRole
from app.schemas.events import DashboardStats, EventOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


def _count(db, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


@router.get("", response_model=DashboardStats, dependencies=[AnyUser])
def dashboard(db: DbSession, org_id: OrgId):
    today_start = datetime.combine(datetime.now(UTC).date(), time.min)

    events_today = select(Event).where(Event.organization_id == org_id, Event.occurred_at >= today_start)
    recent = (
        db.execute(
            select(Event)
            .where(Event.organization_id == org_id)
            .order_by(Event.occurred_at.desc(), Event.id.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )
    return DashboardStats(
        controllers_total=_count(db, select(Controller).where(Controller.organization_id == org_id)),
        controllers_online=_count(
            db,
            select(Controller).where(
                Controller.organization_id == org_id, Controller.status == ControllerStatus.ONLINE
            ),
        ),
        doors_total=_count(db, select(Door).where(Door.organization_id == org_id)),
        cardholders_total=_count(db, select(Cardholder).where(Cardholder.organization_id == org_id)),
        cardholders_active=_count(
            db,
            select(Cardholder).where(Cardholder.organization_id == org_id, Cardholder.is_active.is_(True)),
        ),
        events_today=_count(db, events_today),
        access_granted_today=_count(db, events_today.where(Event.type == EventType.ACCESS_GRANTED)),
        access_denied_today=_count(db, events_today.where(Event.type == EventType.ACCESS_DENIED)),
        alarms_today=_count(
            db,
            events_today.where(
                Event.type.in_([EventType.ALARM, EventType.DOOR_FORCED, EventType.DOOR_HELD_OPEN])
            ),
        ),
        recent_events=[EventOut.model_validate(e) for e in recent],
    )
