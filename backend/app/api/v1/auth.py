from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair, UserOut
from app.schemas.common import Message
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
def login(body: LoginRequest, db: DbSession, request: Request):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")
    if user.organization and not user.organization.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is suspended")

    user.last_login_at = datetime.now(UTC)
    record_audit(db, user=user, action="login", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return TokenPair(
        access_token=create_access_token(user.id, user.organization_id, user.role.value),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: DbSession):
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token") from exc
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return TokenPair(
        access_token=create_access_token(user.id, user.organization_id, user.role.value),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordRequest, user: CurrentUser, db: DbSession, request: Request):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    record_audit(db, user=user, action="change_password", resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return Message(detail="Password updated")
