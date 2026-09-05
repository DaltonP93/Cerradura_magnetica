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


# --- Metrics ---
def test_metrics_endpoint_exposes_prometheus_text(client):
    client.get("/health")  # generate at least one request
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "acp_http_requests_total" in resp.text
    assert "acp_http_request_duration_seconds_count" in resp.text


def test_metrics_token_gate(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.metrics_token
    settings.metrics_token = "s3cret"
    try:
        assert client.get("/metrics").status_code == 401
        ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
        ok2 = client.get("/metrics", headers={"X-Metrics-Token": "s3cret"})
        assert ok2.status_code == 200
    finally:
        settings.metrics_token = original


# --- Audit correlation ---
def test_audit_row_carries_request_id(client, admin_headers):
    from app.core.database import SessionLocal
    from app.models import AuditLog

    resp = client.post(
        "/api/v1/sites", json={"name": "HQ"},
        headers={**admin_headers, "X-Request-ID": "corr-audit-1"},
    )
    assert resp.status_code == 201, resp.text
    db = SessionLocal()
    try:
        row = db.query(AuditLog).filter_by(request_id="corr-audit-1", action="create").one()
        assert row.resource_type == "site"
    finally:
        db.close()
