from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import Cardholder, Department, User, UserRole
from app.schemas.common import Message, Page
from app.schemas.people import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/departments", tags=["departments"])

Operator = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


@router.get("", response_model=Page[DepartmentOut], dependencies=[AnyUser])
def list_departments(
    db: DbSession,
    org_id: OrgId,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(Department).where(Department.organization_id == org_id).order_by(Department.name)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(
    body: DepartmentCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    if body.parent_id is not None:
        get_or_404(db, Department, body.parent_id, org_id)
    dept = Department(organization_id=org_id, **body.model_dump())
    db.add(dept)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="department",
                 resource_id=dept.id, request=request, organization_id=org_id)
    db.commit()
    return dept


@router.patch("/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: int, body: DepartmentUpdate, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Operator,
):
    dept = get_or_404(db, Department, department_id, org_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("parent_id") is not None:
        if data["parent_id"] == dept.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A department cannot be its own parent")
        get_or_404(db, Department, data["parent_id"], org_id)
    for field, value in data.items():
        setattr(dept, field, value)
    record_audit(db, user=actor, action="update", resource_type="department",
                 resource_id=dept.id, request=request, organization_id=org_id)
    db.commit()
    return dept


@router.delete("/{department_id}", response_model=Message)
def delete_department(
    department_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    dept = get_or_404(db, Department, department_id, org_id)
    in_use = db.execute(
        select(func.count()).select_from(Cardholder).where(Cardholder.department_id == dept.id)
    ).scalar_one()
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Department has {in_use} cardholders assigned")
    db.delete(dept)
    record_audit(db, user=actor, action="delete", resource_type="department",
                 resource_id=department_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Department deleted")
