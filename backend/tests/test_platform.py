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


def test_admin_cannot_hijack_super_admin(client, admin_headers, seeded):
    """A tenant admin must never modify or delete a platform super admin, even
    if one were mis-scoped into the admin's own organization."""
    from app.core.database import SessionLocal
    from app.models import User, UserRole

    # Plant a super admin inside org A (the dangerous, seed-bug scenario).
    db = SessionLocal()
    try:
        planted = User(
            email="planted-super@test.com", full_name="Planted Super",
            role=UserRole.SUPER_ADMIN, hashed_password="x", organization_id=seeded["org_a"],
        )
        db.add(planted)
        db.commit()
        planted_id = planted.id
    finally:
        db.close()

    # Admin A cannot reset its password...
    resp = client.patch(
        f"/api/v1/users/{planted_id}", json={"password": "hijacked123"}, headers=admin_headers
    )
    assert resp.status_code == 404
    # ...nor delete it.
    resp = client.delete(f"/api/v1/users/{planted_id}", headers=admin_headers)
    assert resp.status_code == 404


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


def test_admin_resets_user_mfa(client, admin_headers, seeded):
    """F-5 admin path: an admin can clear a user's MFA (lost device + codes)."""
    from app.core.database import SessionLocal
    from app.models import User

    uid = client.post(
        "/api/v1/users",
        json={"email": "mfa-op@test.com", "full_name": "MFA Op",
              "password": "password123", "role": "operator"},
        headers=admin_headers,
    ).json()["id"]

    # Simulate an enrolled second factor with recovery codes.
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        u.mfa_enabled = True
        u.mfa_secret = "SECRET"
        u.mfa_recovery_hashes = ["h1", "h2"]
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/v1/users/{uid}/reset-mfa", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mfa_enabled"] is False

    db = SessionLocal()
    try:
        u = db.get(User, uid)
        assert u.mfa_enabled is False
        assert u.mfa_secret is None
        assert u.mfa_recovery_hashes is None
    finally:
        db.close()


def test_reset_mfa_is_tenant_scoped(client, admin_b_headers, seeded):
    """An admin of org B cannot reset MFA of a user in org A (404)."""
    from app.core.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        victim = User(email="victim@test.com", full_name="Victim",
                      hashed_password="x", role="operator",
                      organization_id=seeded["org_a"], mfa_enabled=True)
        db.add(victim)
        db.commit()
        vid = victim.id
    finally:
        db.close()

    resp = client.post(f"/api/v1/users/{vid}/reset-mfa", headers=admin_b_headers)
    assert resp.status_code == 404


def test_operator_cannot_reset_mfa(client, operator_headers, seeded):
    resp = client.post("/api/v1/users/1/reset-mfa", headers=operator_headers)
    assert resp.status_code == 403
