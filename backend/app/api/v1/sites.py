from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import Site, User, UserRole
from app.schemas.common import Message, Page
from app.schemas.infrastructure import SiteCreate, SiteOut, SiteUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/sites", tags=["sites"])

Admin = Depends(require_roles(UserRole.ADMIN))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


@router.get("", response_model=Page[SiteOut], dependencies=[AnyUser])
def list_sites(
    db: DbSession,
    org_id: OrgId,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(Site).where(Site.organization_id == org_id).order_by(Site.name)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(body: SiteCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    site = Site(organization_id=org_id, **body.model_dump())
    db.add(site)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="site",
                 resource_id=site.id, request=request, organization_id=org_id)
    db.commit()
    return site


@router.get("/{site_id}", response_model=SiteOut, dependencies=[AnyUser])
def get_site(site_id: int, db: DbSession, org_id: OrgId):
    return get_or_404(db, Site, site_id, org_id)


@router.patch("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: int, body: SiteUpdate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    site = get_or_404(db, Site, site_id, org_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(site, field, value)
    record_audit(db, user=actor, action="update", resource_type="site",
                 resource_id=site.id, request=request, organization_id=org_id)
    db.commit()
    return site


@router.delete("/{site_id}", response_model=Message)
def delete_site(site_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    site = get_or_404(db, Site, site_id, org_id)
    db.delete(site)
    record_audit(db, user=actor, action="delete", resource_type="site",
                 resource_id=site_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Site deleted")
