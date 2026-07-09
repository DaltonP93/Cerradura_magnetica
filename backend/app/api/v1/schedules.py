from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import Holiday, Schedule, ScheduleInterval, User, UserRole
from app.schemas.access import HolidayCreate, HolidayOut, ScheduleCreate, ScheduleOut, ScheduleUpdate
from app.schemas.common import Message, Page
from app.services.audit import record_audit

router = APIRouter(tags=["schedules"])

Admin = Depends(require_roles(UserRole.ADMIN))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


def _stmt(org_id: int):
    return (
        select(Schedule)
        .options(selectinload(Schedule.intervals))
        .where(Schedule.organization_id == org_id)
    )


@router.get("/schedules", response_model=Page[ScheduleOut], dependencies=[AnyUser])
def list_schedules(
    db: DbSession, org_id: OrgId,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    items, total = paginate(db, _stmt(org_id).order_by(Schedule.name), limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    schedule = Schedule(
        organization_id=org_id,
        name=body.name,
        description=body.description,
        allow_on_holidays=body.allow_on_holidays,
        intervals=[ScheduleInterval(**iv.model_dump()) for iv in body.intervals],
    )
    db.add(schedule)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="schedule",
                 resource_id=schedule.id, request=request, organization_id=org_id)
    db.commit()
    return db.execute(_stmt(org_id).where(Schedule.id == schedule.id)).scalar_one()


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut, dependencies=[AnyUser])
def get_schedule(schedule_id: int, db: DbSession, org_id: OrgId):
    schedule = db.execute(_stmt(org_id).where(Schedule.id == schedule_id)).scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: int, body: ScheduleUpdate, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Admin,
):
    schedule = get_or_404(db, Schedule, schedule_id, org_id)
    data = body.model_dump(exclude_unset=True)
    intervals = data.pop("intervals", None)
    if intervals is not None:
        schedule.intervals = [ScheduleInterval(**iv) for iv in intervals]
    for field, value in data.items():
        setattr(schedule, field, value)
    record_audit(db, user=actor, action="update", resource_type="schedule",
                 resource_id=schedule.id, request=request, organization_id=org_id)
    db.commit()
    return db.execute(_stmt(org_id).where(Schedule.id == schedule.id)).scalar_one()


@router.delete("/schedules/{schedule_id}", response_model=Message)
def delete_schedule(
    schedule_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    schedule = get_or_404(db, Schedule, schedule_id, org_id)
    db.delete(schedule)
    record_audit(db, user=actor, action="delete", resource_type="schedule",
                 resource_id=schedule_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Schedule deleted")


# --- Holidays ---
@router.get("/holidays", response_model=Page[HolidayOut], dependencies=[AnyUser])
def list_holidays(
    db: DbSession, org_id: OrgId,
    limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = select(Holiday).where(Holiday.organization_id == org_id).order_by(Holiday.date)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def create_holiday(
    body: HolidayCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    exists = db.execute(
        select(Holiday).where(Holiday.organization_id == org_id, Holiday.date == body.date)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "A holiday already exists on that date")
    holiday = Holiday(organization_id=org_id, **body.model_dump())
    db.add(holiday)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="holiday",
                 resource_id=holiday.id, request=request, organization_id=org_id)
    db.commit()
    return holiday


@router.delete("/holidays/{holiday_id}", response_model=Message)
def delete_holiday(holiday_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    holiday = get_or_404(db, Holiday, holiday_id, org_id)
    db.delete(holiday)
    record_audit(db, user=actor, action="delete", resource_type="holiday",
                 resource_id=holiday_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Holiday deleted")
