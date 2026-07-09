from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import AccessLevel, AccessLevelDoor, Door, Schedule, User, UserRole
from app.schemas.access import AccessLevelCreate, AccessLevelDoorIn, AccessLevelOut, AccessLevelUpdate
from app.schemas.common import Message, Page
from app.services.audit import record_audit

router = APIRouter(prefix="/access-levels", tags=["access-levels"])

Admin = Depends(require_roles(UserRole.ADMIN))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


def _stmt(org_id: int):
    return (
        select(AccessLevel)
        .options(selectinload(AccessLevel.door_rules))
        .where(AccessLevel.organization_id == org_id)
    )


def _validate_rules(db, org_id: int, rules: list[AccessLevelDoorIn]) -> None:
    seen: set[int] = set()
    for rule in rules:
        if rule.door_id in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Duplicate door {rule.door_id} in rules")
        seen.add(rule.door_id)
        get_or_404(db, Door, rule.door_id, org_id)
        if rule.schedule_id is not None:
            get_or_404(db, Schedule, rule.schedule_id, org_id)


@router.get("", response_model=Page[AccessLevelOut], dependencies=[AnyUser])
def list_access_levels(
    db: DbSession, org_id: OrgId,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    items, total = paginate(db, _stmt(org_id).order_by(AccessLevel.name), limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=AccessLevelOut, status_code=status.HTTP_201_CREATED)
def create_access_level(
    body: AccessLevelCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    _validate_rules(db, org_id, body.door_rules)
    level = AccessLevel(
        organization_id=org_id,
        name=body.name,
        description=body.description,
        door_rules=[AccessLevelDoor(**rule.model_dump()) for rule in body.door_rules],
    )
    db.add(level)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="access_level",
                 resource_id=level.id, request=request, organization_id=org_id)
    db.commit()
    return db.execute(_stmt(org_id).where(AccessLevel.id == level.id)).scalar_one()


@router.get("/{level_id}", response_model=AccessLevelOut, dependencies=[AnyUser])
def get_access_level(level_id: int, db: DbSession, org_id: OrgId):
    level = db.execute(_stmt(org_id).where(AccessLevel.id == level_id)).scalar_one_or_none()
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Access level not found")
    return level


@router.patch("/{level_id}", response_model=AccessLevelOut)
def update_access_level(
    level_id: int, body: AccessLevelUpdate, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Admin,
):
    level = get_or_404(db, AccessLevel, level_id, org_id)
    data = body.model_dump(exclude_unset=True)
    rules = data.pop("door_rules", None)
    if rules is not None:
        parsed = [AccessLevelDoorIn(**rule) for rule in rules]
        _validate_rules(db, org_id, parsed)
        level.door_rules.clear()
        db.flush()  # delete old rules before inserting, or the unique constraint trips
        level.door_rules = [AccessLevelDoor(**rule.model_dump()) for rule in parsed]
    for field, value in data.items():
        setattr(level, field, value)
    record_audit(db, user=actor, action="update", resource_type="access_level",
                 resource_id=level.id, request=request, organization_id=org_id)
    db.commit()
    return db.execute(_stmt(org_id).where(AccessLevel.id == level.id)).scalar_one()


@router.delete("/{level_id}", response_model=Message)
def delete_access_level(
    level_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    level = get_or_404(db, AccessLevel, level_id, org_id)
    db.delete(level)
    record_audit(db, user=actor, action="delete", resource_type="access_level",
                 resource_id=level_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Access level deleted")
