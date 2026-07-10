"""Attendance: shifts, leaves, manual signs and the attendance report."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import Cardholder, Leave, ManualSign, Shift, User, UserRole
from app.schemas.attendance import (
    AttendanceReport,
    AttendanceRow,
    AttendanceSummary,
    LeaveCreate,
    LeaveOut,
    ManualSignCreate,
    ManualSignOut,
    ShiftCreate,
    ShiftOut,
    ShiftUpdate,
)
from app.schemas.common import Message, Page
from app.services.attendance import compute_attendance
from app.services.audit import record_audit

router = APIRouter(prefix="/attendance", tags=["attendance"])

Admin = Depends(require_roles(UserRole.ADMIN))
Operator = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


# --- Shifts ---
@router.get("/shifts", response_model=Page[ShiftOut], dependencies=[AnyUser])
def list_shifts(
    db: DbSession, org_id: OrgId,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = select(Shift).where(Shift.organization_id == org_id).order_by(Shift.name)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/shifts", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(body: ShiftCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    shift = Shift(organization_id=org_id, **body.model_dump())
    db.add(shift)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="shift",
                 resource_id=shift.id, request=request, organization_id=org_id)
    db.commit()
    return shift


@router.patch("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int, body: ShiftUpdate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    shift = get_or_404(db, Shift, shift_id, org_id)
    data = body.model_dump(exclude_unset=True)
    if "days_of_week" in data and data["days_of_week"] is not None:
        if any(d < 0 or d > 6 for d in data["days_of_week"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "days_of_week values must be 0..6")
    for field, value in data.items():
        setattr(shift, field, value)
    if shift.start_time >= shift.end_time:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "start_time must be before end_time")
    record_audit(db, user=actor, action="update", resource_type="shift",
                 resource_id=shift.id, request=request, organization_id=org_id)
    db.commit()
    return shift


@router.delete("/shifts/{shift_id}", response_model=Message)
def delete_shift(shift_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    shift = get_or_404(db, Shift, shift_id, org_id)
    db.delete(shift)
    record_audit(db, user=actor, action="delete", resource_type="shift",
                 resource_id=shift_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Shift deleted")


# --- Leaves ---
@router.get("/leaves", response_model=Page[LeaveOut], dependencies=[AnyUser])
def list_leaves(
    db: DbSession, org_id: OrgId,
    cardholder_id: int | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = select(Leave).where(Leave.organization_id == org_id).order_by(Leave.date_from.desc())
    if cardholder_id is not None:
        stmt = stmt.where(Leave.cardholder_id == cardholder_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/leaves", response_model=LeaveOut, status_code=status.HTTP_201_CREATED)
def create_leave(body: LeaveCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator):
    get_or_404(db, Cardholder, body.cardholder_id, org_id)
    leave = Leave(organization_id=org_id, created_by_id=actor.id, **body.model_dump())
    db.add(leave)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="leave",
                 resource_id=leave.id, request=request, organization_id=org_id)
    db.commit()
    return leave


@router.delete("/leaves/{leave_id}", response_model=Message)
def delete_leave(leave_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator):
    leave = get_or_404(db, Leave, leave_id, org_id)
    db.delete(leave)
    record_audit(db, user=actor, action="delete", resource_type="leave",
                 resource_id=leave_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Leave deleted")


# --- Manual signs ---
@router.get("/manual-signs", response_model=Page[ManualSignOut], dependencies=[AnyUser])
def list_manual_signs(
    db: DbSession, org_id: OrgId,
    cardholder_id: int | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = select(ManualSign).where(ManualSign.organization_id == org_id).order_by(ManualSign.signed_at.desc())
    if cardholder_id is not None:
        stmt = stmt.where(ManualSign.cardholder_id == cardholder_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/manual-signs", response_model=ManualSignOut, status_code=status.HTTP_201_CREATED)
def create_manual_sign(
    body: ManualSignCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    get_or_404(db, Cardholder, body.cardholder_id, org_id)
    data = body.model_dump()
    data["signed_at"] = data["signed_at"].replace(tzinfo=None)  # store naive UTC like events
    sign = ManualSign(organization_id=org_id, created_by_id=actor.id, **data)
    db.add(sign)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="manual_sign",
                 resource_id=sign.id, request=request, organization_id=org_id)
    db.commit()
    return sign


@router.delete("/manual-signs/{sign_id}", response_model=Message)
def delete_manual_sign(sign_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator):
    sign = get_or_404(db, ManualSign, sign_id, org_id)
    db.delete(sign)
    record_audit(db, user=actor, action="delete", resource_type="manual_sign",
                 resource_id=sign_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Manual sign deleted")


# --- Report ---
@router.get("/report", response_model=AttendanceReport, dependencies=[AnyUser])
def attendance_report(
    db: DbSession,
    org_id: OrgId,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    cardholder_id: int | None = None,
):
    try:
        rows = compute_attendance(
            db,
            organization_id=org_id,
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            cardholder_id=cardholder_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    out_rows = [
        AttendanceRow(
            cardholder_id=r.cardholder.id,
            cardholder_name=r.cardholder.full_name,
            department=r.cardholder.department.name if r.cardholder.department else None,
            date=r.day,
            check_in=r.check_in,
            check_out=r.check_out,
            statuses=r.statuses,
        )
        for r in rows
    ]

    def count(status_name: str) -> int:
        return sum(1 for r in out_rows if status_name in r.statuses)

    summary = AttendanceSummary(
        days=len({r.date for r in out_rows}),
        present=count("present"),
        late=count("late"),
        early_leave=count("early_leave"),
        absent=count("absent"),
        on_leave=count("leave") + count("business_trip"),
        incomplete=count("incomplete"),
    )
    return AttendanceReport(date_from=date_from, date_to=date_to, rows=out_rows, summary=summary)
