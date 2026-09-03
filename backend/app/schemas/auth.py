from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.base import UserRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = Field(default=None, max_length=10)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # Optional: browser clients carry the refresh token in an HttpOnly cookie,
    # so the body may be empty. Programmatic clients may still send it here.
    refresh_token: str | None = None


class UserOut(ORMModel):
    id: int
    organization_id: int | None
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class MfaDisableRequest(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=10)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER
    organization_id: int | None = None  # only honoured for super admins


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
