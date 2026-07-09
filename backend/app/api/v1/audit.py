from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.helpers import paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import AuditLog, UserRole
from app.schemas.common import Page
from app.schemas.events import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])

Admin = Depends(require_roles(UserRole.ADMIN))


@router.get("", response_model=Page[AuditLogOut], dependencies=[Admin])
def list_audit_logs(
    db: DbSession,
    org_id: OrgId,
    user_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from.replace(tzinfo=None))
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to.replace(tzinfo=None))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
