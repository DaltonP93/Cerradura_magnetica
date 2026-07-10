"""Legacy iCCard3000.mdb importer (mdb-export output is simulated)."""
import io

import pytest

from app.services import legacy_mdb


@pytest.fixture
def fake_mdb(monkeypatch):
    """Simulate mdbtools for a typical iCCard3000 database layout."""
    tables = ["Department", "Consumer", "SwipeRecord"]
    exports = {
        "Department": b'"DepartmentNO","Department"\n1,"Ventas"\n',
        "Consumer": (
            b'"ConsumerNO","Name","CardID","Department"\n'
            b'"E-1","Laura Marquez","60001","Ventas"\n'
            b'"E-2","Nico Bravo","60002","Deposito"\n'
        ),
        "SwipeRecord": b'"RecordNO","CardID","Time"\n1,"60001","2024-01-01 09:00:00"\n',
    }

    def fake_run(cmd: list[str]) -> bytes:
        if cmd[0] == "mdb-tables":
            return ("\n".join(tables) + "\n").encode()
        if cmd[0] == "mdb-export":
            return exports[cmd[2]]
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(legacy_mdb, "_run", fake_run)
    return exports


def upload_mdb(client, headers, content: bytes = b"fake-mdb-bytes", filename: str = "iCCard3000.mdb"):
    return client.post(
        "/api/v1/cardholders/import-mdb",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        headers=headers,
    )


def test_mdb_import_detects_consumer_table(client, admin_headers, fake_mdb):
    resp = upload_mdb(client, admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 2

    people = client.get("/api/v1/cardholders", headers=admin_headers).json()
    assert people["total"] == 2
    laura = next(p for p in people["items"] if p["first_name"] == "Laura")
    assert laura["credentials"][0]["card_number"] == "60001"
    departments = client.get("/api/v1/departments", headers=admin_headers).json()
    assert {d["name"] for d in departments["items"]} == {"Ventas", "Deposito"}


def test_mdb_import_rejects_wrong_extension(client, admin_headers, fake_mdb):
    resp = upload_mdb(client, admin_headers, filename="datos.xlsx")
    assert resp.status_code == 400


def test_mdb_import_no_consumer_table(client, admin_headers, monkeypatch):
    def fake_run(cmd: list[str]) -> bytes:
        if cmd[0] == "mdb-tables":
            return b"OnlyLogs\n"
        return b'"A","B"\n1,2\n'

    monkeypatch.setattr(legacy_mdb, "_run", fake_run)
    resp = upload_mdb(client, admin_headers)
    assert resp.status_code == 400
    assert "No table with consumer columns" in resp.json()["detail"]


def test_mdb_import_without_mdbtools(client, admin_headers, monkeypatch):
    def fake_run(cmd: list[str]) -> bytes:
        raise legacy_mdb.MdbToolsNotAvailable("mdbtools is not installed on the server")

    monkeypatch.setattr(legacy_mdb, "_run", fake_run)
    resp = upload_mdb(client, admin_headers)
    assert resp.status_code == 501
    assert "mdbtools" in resp.json()["detail"]
