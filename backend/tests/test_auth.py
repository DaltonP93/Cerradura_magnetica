from tests.conftest import login


def test_login_success(client, seeded):
    resp = client.post(
        "/api/v1/auth/login", json={"email": "admin-a@test.com", "password": "password123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password(client, seeded):
    resp = client.post("/api/v1/auth/login", json={"email": "admin-a@test.com", "password": "nope-nope"})
    assert resp.status_code == 401


def test_me(client, admin_headers):
    resp = client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin-a@test.com"
    assert resp.json()["role"] == "admin"


def test_refresh_flow(client, seeded):
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "admin-a@test.com", "password": "password123"}
    ).json()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    # An access token must not be usable as a refresh token
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


def test_requires_auth(client, seeded):
    assert client.get("/api/v1/cardholders").status_code == 401


def test_change_password(client, seeded):
    headers = login(client, "viewer-a@test.com")
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "newpassword1"},
        headers=headers,
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/auth/login", json={"email": "viewer-a@test.com", "password": "newpassword1"}
    )
    assert resp.status_code == 200


def test_viewer_cannot_create(client, viewer_headers):
    resp = client.post("/api/v1/sites", json={"name": "X"}, headers=viewer_headers)
    assert resp.status_code == 403


def test_operator_cannot_manage_users(client, operator_headers):
    resp = client.get("/api/v1/users", headers=operator_headers)
    assert resp.status_code == 403
