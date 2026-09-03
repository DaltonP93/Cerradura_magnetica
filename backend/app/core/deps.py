"""FastAPI dependencies: authentication, RBAC and tenant scoping."""
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.cookies import ACCESS_COOKIE
from app.core.database import get_db
from app.core.security import decode_token
from app.models import User, UserRole
from app.services.sessions import get_active_session, organization_active

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    # Browser sessions authenticate via the HttpOnly access cookie; programmatic
    # clients may still present a Bearer token. The bearer header wins if both
    # are somehow present.
    token = credentials.credentials if credentials is not None else request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(token, "access")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    session_id = payload.get("sid")
    subject = int(payload["sub"])
    # The session must exist, be live, AND belong to the token's subject.
    if not session_id or get_active_session(db, session_id, subject) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer active")

    user = db.get(User, subject)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    if not organization_active(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is suspended")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_roles(*roles: UserRole):
    """Dependency factory: only allow the given roles (super admin always passes)."""

    def checker(user: CurrentUser) -> User:
        if user.role == UserRole.SUPER_ADMIN or user.role in roles:
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

    return checker


# Common role bundles
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
OperatorUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]
SuperAdminUser = Annotated[User, Depends(require_roles())]


def get_org_id(
    user: CurrentUser,
    organization_id: Annotated[int | None, Query(description="Super admins only: act on this organization")] = None,
) -> int:
    """Resolve the tenant the request operates on.

    Regular users are always locked to their own organization. Super admins
    must select one explicitly via the ``organization_id`` query parameter.
    """
    if user.role == UserRole.SUPER_ADMIN:
        if organization_id is None:
            if user.organization_id is not None:
                return user.organization_id
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Super admin must provide organization_id query parameter"
            )
        return organization_id
    if user.organization_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no organization")
    if organization_id is not None and organization_id != user.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot access another organization")
    return user.organization_id


OrgId = Annotated[int, Depends(get_org_id)]
