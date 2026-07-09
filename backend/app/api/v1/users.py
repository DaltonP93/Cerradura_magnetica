from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.helpers import paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.core.security import hash_password
from app.models import Organization, User, UserRole
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import Message, Page
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["users"])

Admin = Depends(require_roles(UserRole.ADMIN))


def _get_scoped_user(db, user_id: int, actor: User, org_id: int) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if actor.role != UserRole.SUPER_ADMIN and target.organization_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return target


@router.get("", response_model=Page[UserOut])
def list_users(
    db: DbSession,
    org_id: OrgId,
    actor: User = Admin,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(User).where(User.organization_id == org_id).order_by(User.full_name)
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    email = body.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    target_org: int | None = org_id
    if actor.role == UserRole.SUPER_ADMIN and body.organization_id is not None:
        target_org = body.organization_id
    if body.role == UserRole.SUPER_ADMIN:
        if actor.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only super admins can create super admins")
        target_org = body.organization_id  # may be None (platform-level user)
    if target_org is not None and db.get(Organization, target_org) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    user = User(
        email=email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        organization_id=target_org,
    )
    db.add(user)
    db.flush()
    record_audit(
        db, user=actor, action="create", resource_type="user",
        resource_id=user.id, request=request, organization_id=target_org,
    )
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin
):
    target = _get_scoped_user(db, user_id, actor, org_id)
    data = body.model_dump(exclude_unset=True)
    if "role" in data and data["role"] == UserRole.SUPER_ADMIN and actor.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only super admins can grant super admin")
    if "password" in data:
        target.hashed_password = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(target, field, value)
    record_audit(
        db, user=actor, action="update", resource_type="user",
        resource_id=target.id, request=request, organization_id=target.organization_id,
    )
    db.commit()
    return target


@router.delete("/{user_id}", response_model=Message)
def delete_user(user_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Admin):
    target = _get_scoped_user(db, user_id, actor, org_id)
    if target.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    record_audit(
        db, user=actor, action="delete", resource_type="user",
        resource_id=target.id, request=request, organization_id=target.organization_id,
    )
    db.delete(target)
    db.commit()
    return Message(detail="User deleted")
