"""Request correlation id middleware (Fase 7 operational hardening)."""


def test_response_carries_a_request_id(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid and len(rid) >= 8


def test_inbound_request_id_is_echoed(client):
    resp = client.get("/health", headers={"X-Request-ID": "corr-123"})
    assert resp.headers.get("X-Request-ID") == "corr-123"


def test_request_ids_differ_between_requests(client):
    a = client.get("/health").headers["X-Request-ID"]
    b = client.get("/health").headers["X-Request-ID"]
    assert a != b
