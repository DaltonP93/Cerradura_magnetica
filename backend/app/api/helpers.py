"""Small helpers shared by the API routers."""
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.database import Base

M = TypeVar("M", bound=Base)

_MISSING = object()


def get_or_404(db: Session, model: type[M], obj_id: int, org_id: int | None = None) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    if org_id is not None:
        # F-9: fail-closed. The old `getattr(obj, "organization_id", org_id)`
        # defaulted to org_id when the attribute was absent, so a tenant-scoped
        # lookup on a model WITHOUT organization_id would silently pass and leak
        # across orgs. A scoped lookup now REQUIRES the attribute; its absence is
        # a programming error, surfaced loudly instead of leaking data.
        obj_org = getattr(obj, "organization_id", _MISSING)
        if obj_org is _MISSING:
            raise RuntimeError(
                f"{model.__name__} has no organization_id; get_or_404 cannot enforce tenant scope"
            )
        if obj_org != org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def paginate(db: Session, stmt: Select, limit: int, offset: int) -> tuple[list, int]:
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(items), total
