"""Server-side CSV export of the events report (P2-2)."""
from datetime import datetime

from app.core.database import SessionLocal
from app.models import Event, EventType


def _add_event(org_id: int, message: str, etype: EventType = EventType.ACCESS_GRANTED) -> None:
    db = SessionLocal()
    try:
        db.add(Event(organization_id=org_id, type=etype, message=message,
                     occurred_at=datetime(2026, 1, 2, 3, 4, 5)))
        db.commit()
    finally:
        db.close()


def test_export_csv_streams_all_rows(client, admin_headers, seeded):
    _add_event(seeded["org_a"], "primer evento")
    _add_event(seeded["org_a"], "segundo evento")

    resp = client.get("/api/v1/events/export.csv", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")

    lines = [ln for ln in resp.text.splitlines() if ln.strip()]
    assert lines[0] == "id,occurred_at,type,message,controller_id,door_id,cardholder_id"
    body = "\n".join(lines[1:])
    assert "primer evento" in body
    assert "segundo evento" in body
    # No raw details / card-number columns are ever emitted (invariant #6).
    assert "details" not in lines[0]
    assert "card_number" not in lines[0]


def test_export_csv_applies_type_filter(client, admin_headers, seeded):
    _add_event(seeded["org_a"], "concedido", EventType.ACCESS_GRANTED)
    _add_event(seeded["org_a"], "denegado", EventType.ACCESS_DENIED)

    resp = client.get(
        "/api/v1/events/export.csv",
        params={"type": "access_denied"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert "denegado" in resp.text
    assert "concedido" not in resp.text


def test_export_csv_is_tenant_scoped(client, admin_headers, admin_b_headers, seeded):
    _add_event(seeded["org_a"], "solo-org-a")
    _add_event(seeded["org_b"], "solo-org-b")

    a = client.get("/api/v1/events/export.csv", headers=admin_headers).text
    assert "solo-org-a" in a
    assert "solo-org-b" not in a
