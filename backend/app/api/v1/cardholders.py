from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.helpers import get_or_404, paginate
from app.core.deps import DbSession, OrgId, require_roles
from app.models import AccessLevel, Cardholder, Credential, Department, User, UserRole
from app.schemas.common import Message, Page
from app.schemas.people import (
    CardholderCreate,
    CardholderOut,
    CardholderUpdate,
    CredentialCreate,
    CredentialOut,
    CredentialUpdate,
    ImportResult,
)
from app.services.audit import record_audit
from app.services.importer import import_cardholders_csv

router = APIRouter(prefix="/cardholders", tags=["cardholders"])

Operator = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
AnyUser = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))


def _stmt(org_id: int):
    return (
        select(Cardholder)
        .options(selectinload(Cardholder.credentials))
        .where(Cardholder.organization_id == org_id)
    )


def _resolve_access_levels(db, org_id: int, ids: list[int]) -> list[AccessLevel]:
    levels = db.execute(
        select(AccessLevel).where(AccessLevel.organization_id == org_id, AccessLevel.id.in_(ids))
    ).scalars().all()
    if len(levels) != len(set(ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more access levels not found")
    return list(levels)


@router.get("", response_model=Page[CardholderOut], dependencies=[AnyUser])
def list_cardholders(
    db: DbSession,
    org_id: OrgId,
    q: str | None = None,
    department_id: int | None = None,
    is_active: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = _stmt(org_id).order_by(Cardholder.last_name, Cardholder.first_name)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            Cardholder.first_name.ilike(pattern)
            | Cardholder.last_name.ilike(pattern)
            | Cardholder.employee_number.ilike(pattern)
        )
    if department_id is not None:
        stmt = stmt.where(Cardholder.department_id == department_id)
    if is_active is not None:
        stmt = stmt.where(Cardholder.is_active.is_(is_active))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=CardholderOut, status_code=status.HTTP_201_CREATED)
def create_cardholder(
    body: CardholderCreate, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    data = body.model_dump(exclude={"access_level_ids"})
    if data.get("department_id") is not None:
        get_or_404(db, Department, data["department_id"], org_id)
    holder = Cardholder(organization_id=org_id, **data)
    holder.access_levels = _resolve_access_levels(db, org_id, body.access_level_ids)
    db.add(holder)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="cardholder",
                 resource_id=holder.id, request=request, organization_id=org_id)
    db.commit()
    return holder


@router.get("/{cardholder_id}", response_model=CardholderOut, dependencies=[AnyUser])
def get_cardholder(cardholder_id: int, db: DbSession, org_id: OrgId):
    holder = db.execute(_stmt(org_id).where(Cardholder.id == cardholder_id)).scalar_one_or_none()
    if holder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cardholder not found")
    return holder


@router.patch("/{cardholder_id}", response_model=CardholderOut)
def update_cardholder(
    cardholder_id: int, body: CardholderUpdate, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Operator,
):
    holder = get_or_404(db, Cardholder, cardholder_id, org_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("department_id") is not None:
        get_or_404(db, Department, data["department_id"], org_id)
    level_ids = data.pop("access_level_ids", None)
    if level_ids is not None:
        holder.access_levels = _resolve_access_levels(db, org_id, level_ids)
    for field, value in data.items():
        setattr(holder, field, value)
    record_audit(db, user=actor, action="update", resource_type="cardholder",
                 resource_id=holder.id, request=request, organization_id=org_id)
    db.commit()
    return holder


@router.delete("/{cardholder_id}", response_model=Message)
def delete_cardholder(
    cardholder_id: int, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    holder = get_or_404(db, Cardholder, cardholder_id, org_id)
    db.delete(holder)
    record_audit(db, user=actor, action="delete", resource_type="cardholder",
                 resource_id=cardholder_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Cardholder deleted")


@router.post("/import", response_model=ImportResult)
async def import_cardholders(
    file: UploadFile, db: DbSession, org_id: OrgId, request: Request, actor: User = Operator
):
    """Bulk import from a CSV export (columns: ConsumerNO, Name, CardID, Department).

    Mirrors the legacy software's "Import consumer's information from Excel"
    (manual section 5.3). Rows with problems are reported, valid rows are
    created; missing departments are created on the fly.
    """
    if file.filename and not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a CSV file (export the Excel as CSV)")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File larger than 5 MB")
    summary = import_cardholders_csv(db, org_id, content)
    record_audit(db, user=actor, action="import", resource_type="cardholder",
                 request=request, organization_id=org_id,
                 details={"created": summary.created, "errors": len(summary.errors)})
    db.commit()
    return ImportResult(created=summary.created, errors=summary.errors)


# --- Credentials ---
@router.post("/{cardholder_id}/credentials", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
def add_credential(
    cardholder_id: int, body: CredentialCreate, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Operator,
):
    holder = get_or_404(db, Cardholder, cardholder_id, org_id)
    exists = db.execute(
        select(Credential).where(
            Credential.organization_id == org_id, Credential.card_number == body.card_number
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Card number already assigned")
    credential = Credential(organization_id=org_id, cardholder_id=holder.id, **body.model_dump())
    db.add(credential)
    db.flush()
    record_audit(db, user=actor, action="create", resource_type="credential",
                 resource_id=credential.id, request=request, organization_id=org_id,
                 details={"cardholder_id": holder.id})
    db.commit()
    return credential


@router.patch("/{cardholder_id}/credentials/{credential_id}", response_model=CredentialOut)
def update_credential(
    cardholder_id: int, credential_id: int, body: CredentialUpdate, db: DbSession, org_id: OrgId,
    request: Request, actor: User = Operator,
):
    credential = get_or_404(db, Credential, credential_id, org_id)
    if credential.cardholder_id != cardholder_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(credential, field, value)
    record_audit(db, user=actor, action="update", resource_type="credential",
                 resource_id=credential.id, request=request, organization_id=org_id)
    db.commit()
    return credential


@router.delete("/{cardholder_id}/credentials/{credential_id}", response_model=Message)
def delete_credential(
    cardholder_id: int, credential_id: int, db: DbSession, org_id: OrgId, request: Request,
    actor: User = Operator,
):
    credential = get_or_404(db, Credential, credential_id, org_id)
    if credential.cardholder_id != cardholder_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
    db.delete(credential)
    record_audit(db, user=actor, action="delete", resource_type="credential",
                 resource_id=credential_id, request=request, organization_id=org_id)
    db.commit()
    return Message(detail="Credential deleted")
