"""Audit trail recording."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.core.observability import get_request_id
from app.models import AuditLog, User


def record_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    resource_type: str,
    resource_id: int | str | None = None,
    details: dict | None = None,
    request: Request | None = None,
    organization_id: int | None = None,
) -> AuditLog:
    request_id = get_request_id()
    entry = AuditLog(
        organization_id=organization_id if organization_id is not None else (user.organization_id if user else None),
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=details,
        ip_address=request.client.host if request and request.client else None,
        request_id=request_id if request_id != "-" else None,
    )
    db.add(entry)
    db.flush()
    return entry
