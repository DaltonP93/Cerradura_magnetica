"""CSV bulk import (mirrors manual section 5.3: Import from Excel)."""
import io


def upload(client, headers, content: str, filename: str = "personal.csv"):
    return client.post(
        "/api/v1/cardholders/import",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")},
        headers=headers,
    )


def test_import_creates_cardholders_and_departments(client, admin_headers):
    csv_content = (
        "ConsumerNO,Name,CardID,Department\n"
        "E-100,Juan Perez,20001,Ventas\n"
        "E-101,Maria Del Carmen Gomez,20002,Ventas\n"
        "E-102,Pedro Lopez,20003,Sistemas\n"
    )
    resp = upload(client, admin_headers, csv_content)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 3
    assert body["errors"] == []

    people = client.get("/api/v1/cardholders", headers=admin_headers).json()
    assert people["total"] == 3
    maria = next(p for p in people["items"] if p["first_name"] == "Maria")
    assert maria["last_name"] == "Del Carmen Gomez"
    assert maria["credentials"][0]["card_number"] == "20002"

    departments = client.get("/api/v1/departments", headers=admin_headers).json()
    assert {d["name"] for d in departments["items"]} == {"Ventas", "Sistemas"}


def test_import_semicolon_and_spanish_headers(client, admin_headers):
    csv_content = "Legajo;Nombre;Tarjeta;Departamento\nE-1;Ana Diaz;30001;RRHH\n"
    resp = upload(client, admin_headers, csv_content)
    assert resp.status_code == 200
    assert resp.json()["created"] == 1


def test_import_reports_errors_and_duplicates(client, admin_headers):
    first = upload(client, admin_headers, "Name,CardID\nCarlos Ruiz,40001\n")
    assert first.json()["created"] == 1

    csv_content = (
        "Name,CardID\n"
        "Carlos Ruiz,40001\n"   # duplicate card
        ",40002\n"              # missing name
        "Luisa Vega,\n"         # missing card
        "Sofia Blanco,40003\n"  # valid
    )
    resp = upload(client, admin_headers, csv_content)
    body = resp.json()
    assert body["created"] == 1
    reasons = [e["reason"] for e in body["errors"]]
    assert any("already assigned" in r for r in reasons)
    assert any("Missing name" in r for r in reasons)
    assert any("Missing card" in r for r in reasons)


def test_import_rejects_missing_columns_and_bad_extension(client, admin_headers):
    resp = upload(client, admin_headers, "Foo,Bar\n1,2\n")
    assert resp.json()["created"] == 0
    assert "Missing required columns" in resp.json()["errors"][0]["reason"]

    resp = upload(client, admin_headers, "Name,CardID\nX Y,1\n", filename="datos.xlsx")
    assert resp.status_code == 400


def test_viewer_cannot_import(client, viewer_headers):
    resp = upload(client, viewer_headers, "Name,CardID\nX Y,50001\n")
    assert resp.status_code == 403
