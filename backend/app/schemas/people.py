from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.base import CredentialType
from app.schemas.common import ORMModel


# --- Departments ---
class DepartmentOut(ORMModel):
    id: int
    name: str
    parent_id: int | None
    created_at: datetime


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: int | None = None


# --- Credentials ---
class CredentialOut(ORMModel):
    id: int
    cardholder_id: int
    type: CredentialType
    card_number: str
    is_active: bool
    created_at: datetime


class CredentialCreate(BaseModel):
    type: CredentialType = CredentialType.CARD
    card_number: str = Field(min_length=1, max_length=50)
    pin: str | None = Field(default=None, min_length=4, max_length=8, pattern=r"^\d+$")


class CredentialUpdate(BaseModel):
    is_active: bool | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=8, pattern=r"^\d+$")


class ImportResult(BaseModel):
    """Result of a staged bulk import (manual section 5.3).

    On a dry run ``created`` is 0 and ``valid`` reports what would be created.
    """

    dry_run: bool = False
    created: int
    valid: int = 0
    skipped: int = 0
    new_departments: list[str] = []
    errors: list[dict]


# --- Cardholders ---
class CardholderOut(ORMModel):
    id: int
    department_id: int | None
    shift_id: int | None
    first_name: str
    last_name: str
    employee_number: str | None
    email: str | None
    phone: str | None
    photo_url: str | None
    valid_from: datetime | None
    valid_to: datetime | None
    is_active: bool
    notes: str | None
    created_at: datetime
    credentials: list[CredentialOut] = []
    access_level_ids: list[int] = []


class CardholderCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    department_id: int | None = None
    shift_id: int | None = None
    employee_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    photo_url: str | None = Field(default=None, max_length=500)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)
    access_level_ids: list[int] = []


class CardholderUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    department_id: int | None = None
    shift_id: int | None = None
    employee_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    photo_url: str | None = Field(default=None, max_length=500)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)
    access_level_ids: list[int] | None = None
