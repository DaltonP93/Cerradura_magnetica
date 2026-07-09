from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, require_roles
from app.models import Organization, User
from app.schemas.common import Message, Page
from app.schemas.tenancy import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/organizations", tags=["organizations"])

SuperAdmin = Depends(require_roles())  # only super_admin passes require_roles with no extra roles


@router.get("", response_model=Page[OrganizationOut], dependencies=[SuperAdmin])
def list_organizations(
    db: DbSession,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Organization).order_by(Organization.name)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    body: OrganizationCreate,
    db: DbSession,
    request: Request,
    user: User = SuperAdmin,
):
    if db.execute(select(Organization).where(Organization.slug == body.slug)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already in use")
    org = Organization(**body.model_dump())
    db.add(org)
    db.flush()
    record_audit(
        db, user=user, action="create", resource_type="organization",
        resource_id=org.id, request=request, organization_id=org.id,
    )
    db.commit()
    return org


@router.get("/{org_id}", response_model=OrganizationOut, dependencies=[SuperAdmin])
def get_organization(org_id: int, db: DbSession):
    return get_or_404(db, Organization, org_id)


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: int,
    body: OrganizationUpdate,
    db: DbSession,
    request: Request,
    user: User = SuperAdmin,
):
    org = get_or_404(db, Organization, org_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    record_audit(
        db, user=user, action="update", resource_type="organization",
        resource_id=org.id, request=request, organization_id=org.id,
    )
    db.commit()
    return org


@router.delete("/{org_id}", response_model=Message)
def delete_organization(org_id: int, db: DbSession, request: Request, user: User = SuperAdmin):
    org = get_or_404(db, Organization, org_id)
    db.delete(org)
    record_audit(
        db, user=user, action="delete", resource_type="organization",
        resource_id=org_id, request=request, organization_id=None,
    )
    db.commit()
    return Message(detail="Organization deleted")
