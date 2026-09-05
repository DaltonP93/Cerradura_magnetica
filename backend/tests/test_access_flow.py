"""End-to-end access decision tests: the core business logic of the platform."""
import pytest


@pytest.fixture
def setup_access(client, admin_headers, controller_with_doors):
    """Department, cardholder with card 55555, 24/7 access to door 1 only."""
    doors = controller_with_doors["doors"]

    dept = client.post("/api/v1/departments", json={"name": "Engineering"}, headers=admin_headers).json()
    level = client.post(
        "/api/v1/access-levels",
        json={"name": "Door 1 always", "door_rules": [{"door_id": doors[0]["id"]}]},
        headers=admin_headers,
    ).json()
    holder = client.post(
        "/api/v1/cardholders",
        json={
            "first_name": "Carla",
            "last_name": "Mendez",
            "department_id": dept["id"],
            "access_level_ids": [level["id"]],
        },
        headers=admin_headers,
    ).json()
    cred = client.post(
        f"/api/v1/cardholders/{holder['id']}/credentials",
        json={"card_number": "55555"},
        headers=admin_headers,
    ).json()
    return {"doors": doors, "holder": holder, "credential": cred, "level": level}


def swipe(client, headers, door_id, card, pin=None):
    resp = client.post(
        "/api/v1/events/swipe",
        json={"door_id": door_id, "card_number": card, "pin": pin},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_granted_on_authorized_door(client, operator_headers, setup_access):
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "55555")
    assert result["granted"] is True
    assert result["cardholder_id"] == setup_access["holder"]["id"]


def test_denied_on_unauthorized_door(client, operator_headers, setup_access):
    result = swipe(client, operator_headers, setup_access["doors"][1]["id"], "55555")
    assert result["granted"] is False
    assert result["reason"] == "no_access_level"


def test_denied_unknown_card(client, operator_headers, setup_access):
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "99999")
    assert result["granted"] is False
    assert result["reason"] == "unknown_credential"


def test_denied_inactive_cardholder(client, admin_headers, operator_headers, setup_access):
    holder_id = setup_access["holder"]["id"]
    client.patch(f"/api/v1/cardholders/{holder_id}", json={"is_active": False}, headers=admin_headers)
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "55555")
    assert result["granted"] is False
    assert result["reason"] == "cardholder_inactive"


def test_denied_inactive_credential(client, admin_headers, operator_headers, setup_access):
    holder_id = setup_access["holder"]["id"]
    cred_id = setup_access["credential"]["id"]
    client.patch(
        f"/api/v1/cardholders/{holder_id}/credentials/{cred_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "55555")
    assert result["granted"] is False
    assert result["reason"] == "credential_inactive"


def test_denied_expired_validity(client, admin_headers, operator_headers, setup_access):
    holder_id = setup_access["holder"]["id"]
    client.patch(
        f"/api/v1/cardholders/{holder_id}",
        json={"valid_to": "2020-01-01T00:00:00Z"},
        headers=admin_headers,
    )
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "55555")
    assert result["granted"] is False
    assert result["reason"] == "out_of_validity"


def test_schedule_restriction(client, admin_headers, operator_headers, setup_access):
    """A schedule with no intervals never allows access."""
    empty_schedule = client.post(
        "/api/v1/schedules", json={"name": "Never", "intervals": []}, headers=admin_headers
    ).json()
    level_id = setup_access["level"]["id"]
    client.patch(
        f"/api/v1/access-levels/{level_id}",
        json={"door_rules": [{"door_id": setup_access["doors"][0]["id"], "schedule_id": empty_schedule["id"]}]},
        headers=admin_headers,
    )
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "55555")
    assert result["granted"] is False
    assert result["reason"] == "out_of_schedule"


def test_always_schedule_allows(client, admin_headers, operator_headers, setup_access):
    """A 7-day 00:00-23:59 schedule allows access at any time."""
    always = client.post(
        "/api/v1/schedules",
        json={
            "name": "Always",
            "intervals": [
                {"day_of_week": d, "start_time": "00:00:00", "end_time": "23:59:59"} for d in range(7)
            ],
        },
        headers=admin_headers,
    ).json()
    level_id = setup_access["level"]["id"]
    client.patch(
        f"/api/v1/access-levels/{level_id}",
        json={"door_rules": [{"door_id": setup_access["doors"][0]["id"], "schedule_id": always["id"]}]},
        headers=admin_headers,
    )
    result = swipe(client, operator_headers, setup_access["doors"][0]["id"], "55555")
    assert result["granted"] is True


def test_card_plus_pin(client, admin_headers, operator_headers, setup_access):
    holder_id = setup_access["holder"]["id"]
    cred = client.post(
        f"/api/v1/cardholders/{holder_id}/credentials",
        json={"card_number": "77777", "type": "card_plus_pin", "pin": "1234"},
        headers=admin_headers,
    )
    assert cred.status_code == 201
    door_id = setup_access["doors"][0]["id"]
    assert swipe(client, operator_headers, door_id, "77777")["reason"] == "wrong_pin"
    assert swipe(client, operator_headers, door_id, "77777", pin="0000")["reason"] == "wrong_pin"
    assert swipe(client, operator_headers, door_id, "77777", pin="1234")["granted"] is True


def test_pin_only_requires_pin(client, admin_headers, operator_headers, setup_access):
    """A PIN-only credential must not be granted on the card number alone."""
    holder_id = setup_access["holder"]["id"]
    cred = client.post(
        f"/api/v1/cardholders/{holder_id}/credentials",
        json={"card_number": "88888", "type": "pin", "pin": "4321"},
        headers=admin_headers,
    )
    assert cred.status_code == 201
    door_id = setup_access["doors"][0]["id"]
    # No PIN and wrong PIN are both denied...
    assert swipe(client, operator_headers, door_id, "88888")["reason"] == "wrong_pin"
    assert swipe(client, operator_headers, door_id, "88888", pin="0000")["reason"] == "wrong_pin"
    # ...only the correct PIN opens.
    assert swipe(client, operator_headers, door_id, "88888", pin="4321")["granted"] is True


def test_swipe_events_recorded(client, admin_headers, operator_headers, setup_access):
    door_id = setup_access["doors"][0]["id"]
    swipe(client, operator_headers, door_id, "55555")
    swipe(client, operator_headers, door_id, "99999")
    granted = client.get("/api/v1/events", params={"type": "access_granted"}, headers=admin_headers).json()
    denied = client.get("/api/v1/events", params={"type": "access_denied"}, headers=admin_headers).json()
    assert granted["total"] == 1
    assert denied["total"] == 1
    assert denied["items"][0]["details"]["reason"] == "unknown_credential"


def test_event_card_number_is_masked(client, admin_headers, operator_headers, setup_access):
    """Card numbers must be masked in events/audit (invariant #6), not stored raw."""
    door_id = setup_access["doors"][0]["id"]
    swipe(client, operator_headers, door_id, "99999")  # unknown card
    denied = client.get("/api/v1/events", params={"type": "access_denied"}, headers=admin_headers).json()
    stored = denied["items"][0]["details"]["card_number"]
    assert stored == "*9999"
    assert "99999" not in stored


def test_duplicate_card_number_rejected(client, admin_headers, setup_access):
    holder_id = setup_access["holder"]["id"]
    resp = client.post(
        f"/api/v1/cardholders/{holder_id}/credentials",
        json={"card_number": "55555"},
        headers=admin_headers,
    )
    assert resp.status_code == 409
