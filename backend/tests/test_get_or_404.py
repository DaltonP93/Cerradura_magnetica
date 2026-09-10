"""F-9: get_or_404 must fail-closed on models without organization_id."""
import pytest
from fastapi import HTTPException

from app.api.helpers import get_or_404
from app.core.database import SessionLocal
from app.models import Controller, Organization


def test_scoped_lookup_matches_and_mismatches(seeded):
    db = SessionLocal()
    try:
        ctrl = Controller(organization_id=seeded["org_a"], name="B", serial_number="900900001")
        db.add(ctrl)
        db.commit()
        cid = ctrl.id
        # Same org → returned.
        assert get_or_404(db, Controller, cid, seeded["org_a"]).id == cid
        # Other org → 404 (tenant isolation).
        with pytest.raises(HTTPException) as exc:
            get_or_404(db, Controller, cid, seeded["org_b"])
        assert exc.value.status_code == 404
    finally:
        db.close()


def test_missing_object_is_404(seeded):
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            get_or_404(db, Controller, 999999, seeded["org_a"])
        assert exc.value.status_code == 404
    finally:
        db.close()


def test_scoped_lookup_on_non_org_model_fails_closed(seeded):
    """Organization has no organization_id. The old getattr-default would have
    returned another org (IDOR); now it raises instead of leaking."""
    db = SessionLocal()
    try:
        # org_b exists; scoping it by org_a must NOT return org_b.
        with pytest.raises(RuntimeError):
            get_or_404(db, Organization, seeded["org_b"], seeded["org_a"])
    finally:
        db.close()


def test_unscoped_lookup_still_works_on_non_org_model(seeded):
    """Without org_id the helper is a plain get-or-404 (no tenant check)."""
    db = SessionLocal()
    try:
        assert get_or_404(db, Organization, seeded["org_a"]).id == seeded["org_a"]
    finally:
        db.close()
