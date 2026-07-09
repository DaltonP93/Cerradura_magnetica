import os
import tempfile

import pytest

# Configure an isolated database before the app modules are imported.
_tmpdir = tempfile.mkdtemp(prefix="acp-tests-")
os.environ["ACP_DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["ACP_SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Organization, User, UserRole  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def seeded(clean_db):
    """Two organizations with an admin each, plus a platform super admin."""
    db = SessionLocal()
    try:
        org_a = Organization(name="Org A", slug="org-a")
        org_b = Organization(name="Org B", slug="org-b")
        db.add_all([org_a, org_b])
        db.flush()
        users = {
            "super": User(
                email="super@test.com", full_name="Super", role=UserRole.SUPER_ADMIN,
                hashed_password=hash_password("password123"), organization_id=None,
            ),
            "admin_a": User(
                email="admin-a@test.com", full_name="Admin A", role=UserRole.ADMIN,
                hashed_password=hash_password("password123"), organization_id=org_a.id,
            ),
            "operator_a": User(
                email="operator-a@test.com", full_name="Operator A", role=UserRole.OPERATOR,
                hashed_password=hash_password("password123"), organization_id=org_a.id,
            ),
            "viewer_a": User(
                email="viewer-a@test.com", full_name="Viewer A", role=UserRole.VIEWER,
                hashed_password=hash_password("password123"), organization_id=org_a.id,
            ),
            "admin_b": User(
                email="admin-b@test.com", full_name="Admin B", role=UserRole.ADMIN,
                hashed_password=hash_password("password123"), organization_id=org_b.id,
            ),
        }
        db.add_all(users.values())
        db.commit()
        return {"org_a": org_a.id, "org_b": org_b.id}
    finally:
        db.close()


def login(client: TestClient, email: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client, seeded):
    return login(client, "admin-a@test.com")


@pytest.fixture
def operator_headers(client, seeded):
    return login(client, "operator-a@test.com")


@pytest.fixture
def viewer_headers(client, seeded):
    return login(client, "viewer-a@test.com")


@pytest.fixture
def admin_b_headers(client, seeded):
    return login(client, "admin-b@test.com")


@pytest.fixture
def super_headers(client, seeded):
    return login(client, "super@test.com")


@pytest.fixture
def controller_with_doors(client, admin_headers):
    resp = client.post(
        "/api/v1/controllers",
        json={"name": "Board 1", "serial_number": "223011111", "ip_address": "10.0.0.5"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
