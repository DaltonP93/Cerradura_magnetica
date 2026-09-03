"""Events are only broadcast after the transaction commits (no phantom events)."""
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Event, EventType
from app.services import events as events_mod

_PENDING = "pending_event_broadcasts"


def test_commit_flushes_then_clears_pending(seeded):
    db = SessionLocal()
    try:
        events_mod.record_event(
            db, organization_id=seeded["org_a"], type=EventType.REMOTE_OPEN, message="y"
        )
        assert db.info.get(_PENDING)  # buffered, not yet broadcast
        db.commit()
        assert not db.info.get(_PENDING)  # after_commit dispatched and cleared
    finally:
        db.close()


def test_rollback_discards_pending_and_event(seeded):
    db = SessionLocal()
    try:
        events_mod.record_event(
            db, organization_id=seeded["org_a"], type=EventType.REMOTE_OPEN, message="x"
        )
        assert db.info.get(_PENDING)
        db.rollback()
        # No phantom broadcast, and the event row never persisted.
        assert not db.info.get(_PENDING)
        assert db.execute(select(func.count()).select_from(Event)).scalar_one() == 0
    finally:
        db.close()
