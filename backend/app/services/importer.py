"""Bulk import of cardholders from CSV/Excel exports, in two stages.

Mirrors section 5.3 of the legacy Access Control Board Manual ("Import
consumer's information from Excel"), which accepts exactly these columns:
ConsumerNO, Name, CardID and Department. Spanish header aliases are also
accepted, and the delimiter (comma or semicolon) is auto-detected.

The import runs in two stages so nothing is written until the operator has seen
what will happen (invariant #5, validate row by row, no silent overwrite):

* **plan** — parse and validate every row against the existing data (read only),
  producing per-row outcomes and the set of departments that would be created;
* **apply** — persist the planned creations.

A dry run performs the plan stage only and returns the summary without writing.
"""
import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cardholder, Credential, Department

HEADER_ALIASES = {
    "consumerno": "employee_number",
    "consumer_no": "employee_number",
    "employee_number": "employee_number",
    "legajo": "employee_number",
    "nro": "employee_number",
    "name": "name",
    "nombre": "name",
    "cardid": "card_number",
    "card_id": "card_number",
    "card_number": "card_number",
    "tarjeta": "card_number",
    "department": "department",
    "departamento": "department",
    "depto": "department",
}


@dataclass
class ImportSummary:
    dry_run: bool = False
    created: int = 0            # rows actually persisted (0 on a dry run)
    valid: int = 0             # rows that are / would be created
    skipped: int = 0           # blank rows ignored
    new_departments: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def error(self, row: int, reason: str) -> None:
        self.errors.append({"row": row, "reason": reason})


@dataclass
class _Plan:
    summary: ImportSummary
    creates: list[dict] = field(default_factory=list)  # resolved cardholder+card data


def _normalize_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map raw CSV headers to canonical field names."""
    mapping = {}
    for raw in fieldnames:
        key = raw.strip().lstrip("﻿").lower().replace(" ", "")
        if key in HEADER_ALIASES:
            mapping[raw] = HEADER_ALIASES[key]
    return mapping


def _build_plan(db: Session, organization_id: int, content: bytes) -> _Plan:
    """Validate every row against existing data without writing anything."""
    summary = ImportSummary()
    plan = _Plan(summary=summary)

    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    delimiter = ";" if lines and lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    if not reader.fieldnames:
        summary.error(0, "Empty file")
        return plan
    header_map = _normalize_headers(list(reader.fieldnames))
    if not {"name", "card_number"}.issubset(set(header_map.values())):
        summary.error(0, "Missing required columns: Name and CardID")
        return plan

    existing_departments = {
        d.name.lower()
        for d in db.execute(
            select(Department).where(Department.organization_id == organization_id)
        ).scalars()
    }
    existing_cards = {
        c
        for (c,) in db.execute(
            select(Credential.card_number).where(Credential.organization_id == organization_id)
        )
    }
    seen_cards: set[str] = set()
    new_departments: dict[str, None] = {}  # ordered set of new department names

    for line_number, raw_row in enumerate(reader, start=2):
        row = {header_map[k]: (v or "").strip() for k, v in raw_row.items() if k in header_map}
        name = row.get("name", "")
        card = row.get("card_number", "")
        if not name and not card:
            summary.skipped += 1
            continue
        if not name:
            summary.error(line_number, "Missing name")
            continue
        if not card:
            summary.error(line_number, "Missing card number")
            continue
        if card in existing_cards:
            summary.error(line_number, f"Card {card} already assigned")
            continue
        if card in seen_cards:
            summary.error(line_number, f"Card {card} duplicated within the file")
            continue

        dept_name = row.get("department", "") or None
        if dept_name and dept_name.lower() not in existing_departments:
            new_departments.setdefault(dept_name, None)

        parts = name.split()
        plan.creates.append(
            {
                "first_name": parts[0],
                "last_name": " ".join(parts[1:]) or "-",
                "employee_number": row.get("employee_number") or None,
                "department": dept_name,
                "card_number": card,
            }
        )
        seen_cards.add(card)

    summary.valid = len(plan.creates)
    summary.new_departments = list(new_departments)
    return plan


def _apply(db: Session, organization_id: int, creates: list[dict]) -> None:
    departments: dict[str, Department] = {
        d.name.lower(): d
        for d in db.execute(
            select(Department).where(Department.organization_id == organization_id)
        ).scalars()
    }
    for item in creates:
        department = None
        dept_name = item["department"]
        if dept_name:
            department = departments.get(dept_name.lower())
            if department is None:
                department = Department(organization_id=organization_id, name=dept_name)
                db.add(department)
                db.flush()
                departments[dept_name.lower()] = department
        holder = Cardholder(
            organization_id=organization_id,
            first_name=item["first_name"],
            last_name=item["last_name"],
            employee_number=item["employee_number"],
            department_id=department.id if department else None,
        )
        db.add(holder)
        db.flush()
        db.add(Credential(organization_id=organization_id, cardholder_id=holder.id,
                          card_number=item["card_number"]))


def import_cardholders_csv(
    db: Session, organization_id: int, content: bytes, *, dry_run: bool = False
) -> ImportSummary:
    """Plan the import; apply it unless ``dry_run`` is set."""
    plan = _build_plan(db, organization_id, content)
    plan.summary.dry_run = dry_run
    if not dry_run:
        _apply(db, organization_id, plan.creates)
        plan.summary.created = plan.summary.valid
    return plan.summary
