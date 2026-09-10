"""Recoverable PINs are encrypted at rest with a key external to the database.

Phase 1 item 5.
"""
from sqlalchemy import text

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.database import SessionLocal
from app.models import Credential


def _add_pin_credential(client, admin_headers, *, card, pin, level_ids=None):
    holder = client.post(
        "/api/v1/cardholders",
        json={"first_name": "Pina", "last_name": "Torres", "access_level_ids": level_ids or []},
        headers=admin_headers,
    ).json()
    resp = client.post(
        f"/api/v1/cardholders/{holder['id']}/credentials",
        json={"card_number": card, "type": "card_plus_pin", "pin": pin},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return holder, resp.json()


def test_crypto_roundtrip_and_rejects_garbage():
    token = encrypt_secret("1234")
    assert token != "1234"
    assert decrypt_secret(token) == "1234"
    assert decrypt_secret("not-a-valid-token") is None


def test_pin_is_ciphertext_in_the_database(client, admin_headers):
    _add_pin_credential(client, admin_headers, card="70001", pin="4321")
    db = SessionLocal()
    try:
        raw = db.execute(
            text("SELECT pin FROM credentials WHERE card_number = :c"), {"c": "70001"}
        ).scalar_one()
    finally:
        db.close()
    # The raw column holds ciphertext, never the plaintext PIN...
    assert raw is not None and raw != "4321"
    # ...and it decrypts back to the original PIN.
    assert decrypt_secret(raw) == "4321"


def test_pin_decrypts_transparently_via_orm(client, admin_headers):
    _add_pin_credential(client, admin_headers, card="70002", pin="8765")
    db = SessionLocal()
    try:
        cred = db.query(Credential).filter_by(card_number="70002").one()
        assert cred.pin == "8765"
    finally:
        db.close()


def test_credential_response_never_exposes_pin(client, admin_headers):
    _, cred = _add_pin_credential(client, admin_headers, card="70004", pin="2468")
    assert "pin" not in cred


def test_access_requires_correct_pin(client, admin_headers, operator_headers, controller_with_doors):
    doors = controller_with_doors["doors"]
    level = client.post(
        "/api/v1/access-levels",
        json={"name": "PIN door", "door_rules": [{"door_id": doors[0]["id"]}]},
        headers=admin_headers,
    ).json()
    _add_pin_credential(client, admin_headers, card="70003", pin="1357", level_ids=[level["id"]])

    def swipe(pin):
        return client.post(
            "/api/v1/events/swipe",
            json={"door_id": doors[0]["id"], "card_number": "70003", "pin": pin},
            headers=operator_headers,
        ).json()

    assert swipe("1357")["granted"] is True
    denied = swipe("0000")
    assert denied["granted"] is False and denied["reason"] == "wrong_pin"
    assert swipe(None)["granted"] is False  # missing PIN is denied too
