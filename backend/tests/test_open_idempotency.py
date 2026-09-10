"""F-11: remote-open idempotency via a client Idempotency-Key (bridge mode)."""
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import GatewayCommand, GatewayCommandType


def _open_command_count(org_id: int) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(GatewayCommand)
            .filter_by(organization_id=org_id, type=GatewayCommandType.OPEN_DOOR)
            .count()
        )
    finally:
        db.close()


def test_idempotency_key_collapses_double_submit(client, operator_headers, seeded, controller_with_doors):
    settings = get_settings()
    original = settings.command_dispatch
    settings.command_dispatch = "bridge"
    try:
        door = controller_with_doors["doors"][0]
        headers = {**operator_headers, "Idempotency-Key": "open-abc"}
        r1 = client.post(f"/api/v1/doors/{door['id']}/open", headers=headers)
        r2 = client.post(f"/api/v1/doors/{door['id']}/open", headers=headers)
        assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
        # Both submits collapse onto a single queued command (no double pulse).
        assert _open_command_count(seeded["org_a"]) == 1
    finally:
        settings.command_dispatch = original


def test_without_key_two_submits_create_two_commands(client, operator_headers, seeded, controller_with_doors):
    settings = get_settings()
    original = settings.command_dispatch
    settings.command_dispatch = "bridge"
    try:
        door = controller_with_doors["doors"][0]
        client.post(f"/api/v1/doors/{door['id']}/open", headers=operator_headers)
        client.post(f"/api/v1/doors/{door['id']}/open", headers=operator_headers)
        # No idempotency key → two distinct operator actions → two commands.
        assert _open_command_count(seeded["org_a"]) == 2
    finally:
        settings.command_dispatch = original
