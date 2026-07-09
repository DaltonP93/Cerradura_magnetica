"""Small helpers shared by the API routers."""
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.database import Base

M = TypeVar("M", bound=Base)


def get_or_404(db: Session, model: type[M], obj_id: int, org_id: int | None = None) -> M:
    obj = db.get(model, obj_id)
    if obj is None or (org_id is not None and getattr(obj, "organization_id", org_id) != org_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def paginate(db: Session, stmt: Select, limit: int, offset: int) -> tuple[list, int]:
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(items), total
