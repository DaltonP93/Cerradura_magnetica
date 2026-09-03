"""Attendance module: shifts, leaves, manual signs and the report (manual Part 4)."""
from datetime import date, datetime, time, timedelta

import pytest

from app.core.database import SessionLocal
from app.models import Event, EventType


@pytest.fixture
def staff(client, admin_headers):
    """A shift (Mon-Sun 09:00-18:00) and one cardholder assigned to it."""
    shift = client.post(
        "/api/v1/attendance/shifts",
        json={
            "name": "Turno completo",
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "late_tolerance_minutes": 10,
            "early_leave_tolerance_minutes": 10,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        },
        headers=admin_headers,
    ).json()
    holder = client.post(
        "/api/v1/cardholders",
        json={"first_name": "Diego", "last_name": "Soto", "shift_id": shift["id"]},
        headers=admin_headers,
    ).json()
    return {"shift": shift, "holder": holder}


def add_punch(client_org_id: int, cardholder_id: int, when: datetime) -> None:
    """Insert a granted access event directly (simulates a swipe at `when`)."""
    db = SessionLocal()
    try:
        db.add(
            Event(
                organization_id=client_org_id,
                type=EventType.ACCESS_GRANTED,
                message="test punch",
                cardholder_id=cardholder_id,
                occurred_at=when,
            )
        )
        db.commit()
    finally:
        db.close()


def report(client, headers, day: date, **params):
    resp = client.get(
        "/api/v1/attendance/report",
        params={"date_from": day.isoformat(), "date_to": day.isoformat(), **params},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_shift_crud_and_validation(client, admin_headers):
    resp = client.post(
        "/api/v1/attendance/shifts",
        json={"name": "Malo", "start_time": "18:00:00", "end_time": "09:00:00"},
        headers=admin_headers,
    )
    assert resp.status_code == 422  # start >= end

    shift = client.post(
        "/api/v1/attendance/shifts",
        json={"name": "Nocturno v1", "start_time": "08:00:00", "end_time": "17:00:00"},
        headers=admin_headers,
    ).json()
    updated = client.patch(
        f"/api/v1/attendance/shifts/{shift['id']}",
        json={"name": "Nocturno", "late_tolerance_minutes": 5},
        headers=admin_headers,
    ).json()
    assert updated["name"] == "Nocturno"
    assert updated["late_tolerance_minutes"] == 5
    assert client.delete(
        f"/api/v1/attendance/shifts/{shift['id']}", headers=admin_headers
    ).status_code == 200


def test_present_and_late_and_early_leave(client, admin_headers, seeded, staff):
    day = date.today() - timedelta(days=1)
    holder_id = staff["holder"]["id"]
    # check-in 09:30 (late, tolerance 10min) and check-out 17:00 (early, end 18:00)
    add_punch(seeded["org_a"], holder_id, datetime.combine(day, time(9, 30)))
    add_punch(seeded["org_a"], holder_id, datetime.combine(day, time(17, 0)))

    body = report(client, admin_headers, day, cardholder_id=holder_id)
    row = body["rows"][0]
    assert set(row["statuses"]) == {"present", "late", "early_leave"}
    assert row["check_in"].endswith("09:30:00")
    assert row["check_out"].endswith("17:00:00")
    assert body["summary"]["late"] == 1


def test_absent_without_punches(client, admin_headers, staff):
    day = date.today() - timedelta(days=1)
    body = report(client, admin_headers, day, cardholder_id=staff["holder"]["id"])
    assert body["rows"][0]["statuses"] == ["absent"]
    assert body["summary"]["absent"] == 1


def test_on_leave(client, admin_headers, operator_headers, staff):
    day = date.today() - timedelta(days=1)
    holder_id = staff["holder"]["id"]
    resp = client.post(
        "/api/v1/attendance/leaves",
        json={
            "cardholder_id": holder_id,
            "type": "business_trip",
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
            "reason": "Cliente",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201
    body = report(client, admin_headers, day, cardholder_id=holder_id)
    assert body["rows"][0]["statuses"] == ["business_trip"]
    assert body["summary"]["on_leave"] == 1


def test_holiday_over_workday(client, admin_headers, staff):
    day = date.today() - timedelta(days=1)
    client.post(
        "/api/v1/holidays",
        json={"name": "Feriado test", "date": day.isoformat()},
        headers=admin_headers,
    )
    body = report(client, admin_headers, day, cardholder_id=staff["holder"]["id"])
    assert body["rows"][0]["statuses"] == ["holiday"]


def test_manual_sign_fixes_missing_checkout(client, admin_headers, operator_headers, seeded, staff):
    day = date.today() - timedelta(days=1)
    holder_id = staff["holder"]["id"]
    add_punch(seeded["org_a"], holder_id, datetime.combine(day, time(9, 0)))

    body = report(client, admin_headers, day, cardholder_id=holder_id)
    assert "incomplete" in body["rows"][0]["statuses"]

    resp = client.post(
        "/api/v1/attendance/manual-signs",
        json={
            "cardholder_id": holder_id,
            "kind": "out",
            "signed_at": datetime.combine(day, time(18, 0)).isoformat() + "Z",
            "note": "Olvidó fichar la salida",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201
    body = report(client, admin_headers, day, cardholder_id=holder_id)
    assert body["rows"][0]["statuses"] == ["present"]


def test_rest_day_without_shift_day(client, admin_headers, seeded):
    """A cardholder whose shift excludes the day shows rest_day."""
    weekday_shift = client.post(
        "/api/v1/attendance/shifts",
        json={"name": "Solo lunes", "start_time": "09:00:00", "end_time": "18:00:00", "days_of_week": [0]},
        headers=admin_headers,
    ).json()
    holder = client.post(
        "/api/v1/cardholders",
        json={"first_name": "Rita", "last_name": "Paz", "shift_id": weekday_shift["id"]},
        headers=admin_headers,
    ).json()
    a_tuesday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=1) - timedelta(days=7)
    body = report(client, admin_headers, a_tuesday, cardholder_id=holder["id"])
    assert body["rows"][0]["statuses"] == ["rest_day"]


def test_report_respects_timezone(client, admin_headers, seeded, staff):
    """Punches (stored UTC) are shown and judged in the requested timezone."""
    day = date.today() - timedelta(days=1)
    holder_id = staff["holder"]["id"]
    # 12:30 UTC == 09:30 in America/Argentina/Buenos_Aires (UTC-3).
    add_punch(seeded["org_a"], holder_id, datetime.combine(day, time(12, 30)))
    tz = "America/Argentina/Buenos_Aires"

    row = report(client, admin_headers, day, cardholder_id=holder_id, timezone=tz)["rows"][0]
    assert row["check_in"].endswith("09:30:00")  # local time, not 12:30 UTC
    assert "late" in row["statuses"]  # 09:30 is past the 09:10 tolerance

    # Same data in UTC keeps the raw 12:30.
    utc_row = report(client, admin_headers, day, cardholder_id=holder_id)["rows"][0]
    assert utc_row["check_in"].endswith("12:30:00")


def test_report_timezone_day_boundary(client, admin_headers, seeded, staff):
    """A punch after midnight UTC still belongs to the previous local day."""
    day = date.today() - timedelta(days=1)
    holder_id = staff["holder"]["id"]
    # 01:00 UTC on day+1 == 22:00 on `day` in UTC-3.
    add_punch(seeded["org_a"], holder_id, datetime.combine(day + timedelta(days=1), time(1, 0)))
    tz = "America/Argentina/Buenos_Aires"
    row = report(client, admin_headers, day, cardholder_id=holder_id, timezone=tz)["rows"][0]
    assert row["check_in"].endswith("22:00:00")


def test_report_invalid_timezone(client, admin_headers, staff):
    day = date.today() - timedelta(days=1)
    resp = client.get(
        "/api/v1/attendance/report",
        params={"date_from": day.isoformat(), "date_to": day.isoformat(), "timezone": "Not/AZone"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_report_range_limit(client, admin_headers, staff):
    resp = client.get(
        "/api/v1/attendance/report",
        params={"date_from": "2024-01-01", "date_to": "2024-12-31"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_viewer_cannot_manage_shifts(client, viewer_headers):
    resp = client.post(
        "/api/v1/attendance/shifts",
        json={"name": "X", "start_time": "09:00:00", "end_time": "18:00:00"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403
