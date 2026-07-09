def test_create_controller_creates_doors(client, admin_headers, controller_with_doors):
    controller = controller_with_doors
    assert controller["model"] == "L04"
    assert len(controller["doors"]) == 4
    assert [d["number"] for d in controller["doors"]] == [1, 2, 3, 4]


def test_duplicate_serial_rejected(client, admin_headers, controller_with_doors):
    resp = client.post(
        "/api/v1/controllers",
        json={"name": "Board 2", "serial_number": controller_with_doors["serial_number"]},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_update_door_config(client, admin_headers, controller_with_doors):
    door = controller_with_doors["doors"][0]
    resp = client.patch(
        f"/api/v1/doors/{door['id']}",
        json={"name": "Main Gate", "open_duration_seconds": 10, "mode": "normally_closed"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Main Gate"
    assert body["open_duration_seconds"] == 10
    assert body["mode"] == "normally_closed"


def test_remote_open_door_records_event(client, operator_headers, admin_headers, controller_with_doors):
    door = controller_with_doors["doors"][0]
    resp = client.post(f"/api/v1/doors/{door['id']}/open", headers=operator_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    events = client.get("/api/v1/events", params={"type": "remote_open"}, headers=admin_headers).json()
    assert events["total"] == 1
    assert events["items"][0]["door_id"] == door["id"]


def test_ping_marks_controller_online(client, operator_headers, controller_with_doors):
    resp = client.post(f"/api/v1/controllers/{controller_with_doors['id']}/ping", headers=operator_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    detail = client.get(f"/api/v1/controllers/{controller_with_doors['id']}", headers=operator_headers).json()
    assert detail["status"] == "online"
    assert detail["last_seen_at"] is not None


def test_viewer_cannot_open_door(client, viewer_headers, controller_with_doors):
    door = controller_with_doors["doors"][0]
    resp = client.post(f"/api/v1/doors/{door['id']}/open", headers=viewer_headers)
    assert resp.status_code == 403


def test_tenant_isolation(client, admin_b_headers, controller_with_doors):
    resp = client.get(f"/api/v1/controllers/{controller_with_doors['id']}", headers=admin_b_headers)
    assert resp.status_code == 404
    listing = client.get("/api/v1/controllers", headers=admin_b_headers).json()
    assert listing["total"] == 0
