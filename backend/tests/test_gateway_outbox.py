"""Gateway command outbox: idempotent enqueue, atomic lease, idempotent ack."""
from datetime import UTC, datetime, timedelta

import pytest

from app.core.database import SessionLocal
from app.models import Controller, GatewayCommand, GatewayCommandStatus, GatewayCommandType
from app.services import gateway_outbox as outbox


@pytest.fixture
def controller_id(seeded):
    db = SessionLocal()
    try:
        ctrl = Controller(organization_id=seeded["org_a"], name="Board", serial_number="900000001")
        db.add(ctrl)
        db.commit()
        return ctrl.id
    finally:
        db.close()


def _enqueue(db, org_id, controller_id, key, door=1):
    return outbox.enqueue(
        db, organization_id=org_id, controller_id=controller_id,
        type=GatewayCommandType.OPEN_DOOR, idempotency_key=key, payload={"door": door},
    )


def test_enqueue_is_idempotent(seeded, controller_id):
    db = SessionLocal()
    try:
        first = _enqueue(db, seeded["org_a"], controller_id, "k-1")
        db.commit()
        second = _enqueue(db, seeded["org_a"], controller_id, "k-1")
        db.commit()
        assert first.id == second.id
        count = db.query(GatewayCommand).filter_by(idempotency_key="k-1").count()
        assert count == 1
    finally:
        db.close()


def test_claim_leases_and_blocks_second_worker(seeded, controller_id):
    db = SessionLocal()
    try:
        _enqueue(db, seeded["org_a"], controller_id, "k-1")
        db.commit()
        leased = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w1")
        db.commit()
        assert len(leased) == 1
        cmd = leased[0]
        assert cmd.status == GatewayCommandStatus.LEASED
        assert cmd.lease_token == "w1"
        assert cmd.attempts == 1

        # A second worker sees nothing while the lease is valid.
        again = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w2")
        db.commit()
        assert again == []
    finally:
        db.close()


def test_expired_lease_can_be_reclaimed(seeded, controller_id):
    db = SessionLocal()
    try:
        _enqueue(db, seeded["org_a"], controller_id, "k-1")
        db.commit()
        first = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w1")
        db.commit()
        # Expire the lease.
        cmd = db.get(GatewayCommand, first[0].id)
        cmd.leased_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        reclaimed = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w2")
        db.commit()
        assert len(reclaimed) == 1
        assert reclaimed[0].lease_token == "w2"
        assert reclaimed[0].attempts == 2  # delivery attempts accumulate
    finally:
        db.close()


def test_acknowledge_success_is_terminal_and_idempotent(seeded, controller_id):
    db = SessionLocal()
    try:
        _enqueue(db, seeded["org_a"], controller_id, "k-1")
        db.commit()
        cmd = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w1")[0]
        db.commit()

        outbox.acknowledge(db, command=cmd, worker_token="w1", success=True, result={"ok": True})
        db.commit()
        assert cmd.status == GatewayCommandStatus.SUCCEEDED
        assert cmd.result == {"ok": True}
        assert cmd.lease_token is None

        # A repeated ack is a no-op (idempotent).
        outbox.acknowledge(db, command=cmd, worker_token="w1", success=False, error="late")
        db.commit()
        assert cmd.status == GatewayCommandStatus.SUCCEEDED
        assert cmd.last_error is None
    finally:
        db.close()


def test_acknowledge_failure_retries_then_fails(seeded, controller_id):
    db = SessionLocal()
    try:
        outbox.enqueue(
            db, organization_id=seeded["org_a"], controller_id=controller_id,
            type=GatewayCommandType.PING, idempotency_key="k-1", max_attempts=2,
        )
        db.commit()

        # First delivery fails -> back to PENDING for retry.
        c1 = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w1")[0]
        db.commit()
        outbox.acknowledge(db, command=c1, worker_token="w1", success=False, error="boom")
        db.commit()
        assert c1.status == GatewayCommandStatus.PENDING
        assert c1.last_error == "boom"

        # Second delivery reaches max_attempts -> FAILED.
        c2 = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w2")[0]
        db.commit()
        assert c2.attempts == 2
        outbox.acknowledge(db, command=c2, worker_token="w2", success=False, error="boom2")
        db.commit()
        assert c2.status == GatewayCommandStatus.FAILED
        assert c2.last_error == "boom2"
    finally:
        db.close()


def test_acknowledge_rejects_wrong_worker(seeded, controller_id):
    db = SessionLocal()
    try:
        _enqueue(db, seeded["org_a"], controller_id, "k-1")
        db.commit()
        cmd = outbox.claim(db, organization_id=seeded["org_a"], worker_token="w1")[0]
        db.commit()
        with pytest.raises(outbox.OutboxError):
            outbox.acknowledge(db, command=cmd, worker_token="intruder", success=True)
    finally:
        db.close()


def test_claim_filters_by_controller_and_limit(seeded, controller_id):
    db = SessionLocal()
    try:
        for i in range(3):
            _enqueue(db, seeded["org_a"], controller_id, f"k-{i}")
        db.commit()
        leased = outbox.claim(
            db, organization_id=seeded["org_a"], worker_token="w1",
            controller_id=controller_id, limit=2,
        )
        db.commit()
        assert len(leased) == 2  # limit respected
    finally:
        db.close()
