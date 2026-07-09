"""Organizations, users, dashboard and audit trail."""


def test_super_admin_manages_organizations(client, super_headers):
    resp = client.post(
        "/api/v1/organizations",
        json={"name": "New Tenant", "slug": "new-tenant", "plan": "pro"},
        headers=super_headers,
    )
    assert resp.status_code == 201
    org_id = resp.json()["id"]

    listing = client.get("/api/v1/organizations", headers=super_headers).json()
    assert any(o["id"] == org_id for o in listing["items"])

    resp = client.patch(
        f"/api/v1/organizations/{org_id}", json={"plan": "enterprise"}, headers=super_headers
    )
    assert resp.json()["plan"] == "enterprise"


def test_org_admin_cannot_manage_organizations(client, admin_headers):
    resp = client.get("/api/v1/organizations", headers=admin_headers)
    assert resp.status_code == 403


def test_admin_creates_users_in_own_org(client, admin_headers, seeded):
    resp = client.post(
        "/api/v1/users",
        json={
            "email": "new-op@test.com",
            "full_name": "New Operator",
            "password": "password123",
            "role": "operator",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["organization_id"] == seeded["org_a"]

    # duplicate email rejected
    resp = client.post(
        "/api/v1/users",
        json={
            "email": "new-op@test.com",
            "full_name": "Dup",
            "password": "password123",
            "role": "viewer",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_admin_cannot_grant_super_admin(client, admin_headers):
    resp = client.post(
        "/api/v1/users",
        json={
            "email": "evil@test.com",
            "full_name": "Evil",
            "password": "password123",
            "role": "super_admin",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 403


def test_dashboard_stats(client, admin_headers, operator_headers, controller_with_doors):
    door_id = controller_with_doors["doors"][0]["id"]
    client.post(
        "/api/v1/events/swipe",
        json={"door_id": door_id, "card_number": "00000"},
        headers=operator_headers,
    )
    stats = client.get("/api/v1/dashboard", headers=admin_headers).json()
    assert stats["controllers_total"] == 1
    assert stats["doors_total"] == 4
    assert stats["access_denied_today"] == 1
    assert stats["events_today"] >= 1
    assert len(stats["recent_events"]) >= 1


def test_audit_trail(client, admin_headers):
    client.post("/api/v1/sites", json={"name": "Audited Site"}, headers=admin_headers)
    logs = client.get("/api/v1/audit-logs", headers=admin_headers).json()
    actions = [(entry["action"], entry["resource_type"]) for entry in logs["items"]]
    assert ("create", "site") in actions
    assert ("login", "user") in actions


def test_super_admin_requires_org_param(client, super_headers):
    resp = client.get("/api/v1/cardholders", headers=super_headers)
    assert resp.status_code == 400
    resp = client.get("/api/v1/cardholders", params={"organization_id": 1}, headers=super_headers)
    assert resp.status_code == 200
