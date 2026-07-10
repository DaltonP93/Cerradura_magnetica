"""Bulk import of cardholders from CSV/Excel exports.

Mirrors section 5.3 of the legacy Access Control Board Manual ("Import
consumer's information from Excel"), which accepts exactly these columns:
ConsumerNO, Name, CardID and Department. Spanish header aliases are also
accepted, and the delimiter (comma or semicolon) is auto-detected.
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
    created: int = 0
    errors: list[dict] = field(default_factory=list)

    def error(self, row: int, reason: str) -> None:
        self.errors.append({"row": row, "reason": reason})


def _normalize_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map raw CSV headers to canonical field names."""
    mapping = {}
    for raw in fieldnames:
        key = raw.strip().lstrip("﻿").lower().replace(" ", "")
        if key in HEADER_ALIASES:
            mapping[raw] = HEADER_ALIASES[key]
    return mapping


def import_cardholders_csv(db: Session, organization_id: int, content: bytes) -> ImportSummary:
    text = content.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.splitlines() and text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    summary = ImportSummary()

    if not reader.fieldnames:
        summary.error(0, "Empty file")
        return summary
    header_map = _normalize_headers(list(reader.fieldnames))
    required = {"name", "card_number"}
    if not required.issubset(set(header_map.values())):
        summary.error(0, "Missing required columns: Name and CardID")
        return summary

    departments: dict[str, Department] = {
        d.name.lower(): d
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

    for line_number, raw_row in enumerate(reader, start=2):
        row = {header_map[k]: (v or "").strip() for k, v in raw_row.items() if k in header_map}
        name = row.get("name", "")
        card = row.get("card_number", "")
        if not name and not card:
            continue  # blank line
        if not name:
            summary.error(line_number, "Missing name")
            continue
        if not card:
            summary.error(line_number, "Missing card number")
            continue
        if card in existing_cards:
            summary.error(line_number, f"Card {card} already assigned")
            continue

        department = None
        dept_name = row.get("department", "")
        if dept_name:
            department = departments.get(dept_name.lower())
            if department is None:
                department = Department(organization_id=organization_id, name=dept_name)
                db.add(department)
                db.flush()
                departments[dept_name.lower()] = department

        parts = name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) or "-"
        holder = Cardholder(
            organization_id=organization_id,
            first_name=first_name,
            last_name=last_name,
            employee_number=row.get("employee_number") or None,
            department_id=department.id if department else None,
        )
        db.add(holder)
        db.flush()
        db.add(Credential(organization_id=organization_id, cardholder_id=holder.id, card_number=card))
        existing_cards.add(card)
        summary.created += 1

    return summary
