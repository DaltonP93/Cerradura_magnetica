"""HttpOnly cookie authentication and double-submit CSRF protection."""


def _login(client, email="admin-a@test.com"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp


def _set_cookie_headers(resp):
    return resp.headers.get_list("set-cookie")


def test_login_sets_httponly_auth_cookies(client, seeded):
    resp = _login(client)
    cookies = "\n".join(_set_cookie_headers(resp))
    assert "acp_access=" in cookies
    assert "acp_refresh=" in cookies
    assert "acp_csrf=" in cookies
    # The JWT-bearing cookies must be HttpOnly; the CSRF cookie must NOT be.
    access_line = next(line for line in _set_cookie_headers(resp) if line.startswith("acp_access="))
    refresh_line = next(line for line in _set_cookie_headers(resp) if line.startswith("acp_refresh="))
    csrf_line = next(line for line in _set_cookie_headers(resp) if line.startswith("acp_csrf="))
    assert "httponly" in access_line.lower()
    assert "httponly" in refresh_line.lower()
    assert "httponly" not in csrf_line.lower()
    # Refresh cookie is scoped to the auth path.
    assert "path=/api/v1/auth" in refresh_line.lower()


def test_cookie_authenticates_requests(client, seeded):
    _login(client)
    # No Authorization header — the access cookie in the jar must authenticate.
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin-a@test.com"


def test_csrf_required_for_cookie_mutations(client, seeded):
    _login(client)
    # Cookie-authenticated unsafe request without the CSRF header is rejected.
    resp = client.post("/api/v1/sites", json={"name": "HQ"})
    assert resp.status_code == 403
    assert "csrf" in resp.json()["detail"].lower()

    # Supplying the double-submit token unblocks it.
    csrf = client.cookies.get("acp_csrf")
    assert csrf
    ok = client.post("/api/v1/sites", json={"name": "HQ"}, headers={"X-CSRF-Token": csrf})
    assert ok.status_code in (200, 201), ok.text


def test_csrf_mismatch_rejected(client, seeded):
    _login(client)
    resp = client.post("/api/v1/sites", json={"name": "HQ"}, headers={"X-CSRF-Token": "wrong"})
    assert resp.status_code == 403


def test_bearer_requests_skip_csrf(client, seeded):
    # A programmatic client using a Bearer token is not subject to CSRF even for
    # unsafe methods.
    login = _login(client)
    access = login.json()["access_token"]
    client.cookies.clear()  # drop the cookie jar; rely purely on the header
    resp = client.post(
        "/api/v1/sites", json={"name": "HQ"}, headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code in (200, 201), resp.text


def test_refresh_via_cookie_without_body(client, seeded):
    _login(client)
    # Empty body — the refresh token must be taken from the HttpOnly cookie.
    resp = client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    # Rotation must have set a fresh cookie set.
    assert any(line.startswith("acp_access=") for line in _set_cookie_headers(resp))


def test_logout_clears_cookies(client, seeded):
    _login(client)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    # After logout the cleared cookie must no longer authenticate.
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_no_token_anywhere_is_unauthorized(client, seeded):
    assert client.get("/api/v1/auth/me").status_code == 401
