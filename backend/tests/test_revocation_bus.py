"""Cross-worker session revocation over Redis Pub/Sub.

Exercised with fakeredis (no live server). The manager's close_* methods are
spied/stubbed so we assert routing without needing live WebSockets.
"""
import json
import time
from unittest.mock import patch

import fakeredis

from app.services import revocation_bus


def test_enabled_is_false_without_redis_url():
    # The test settings do not set ACP_REDIS_URL.
    assert revocation_bus.enabled() is False


def test_revoke_is_local_only_without_redis():
    """Without Redis, revoke_* just closes locally and never touches a client."""
    with patch.object(revocation_bus.manager, "close_user", return_value=3) as close_user, patch.object(
        revocation_bus, "_client"
    ) as client:
        assert revocation_bus.revoke_user(9) == 3
        close_user.assert_called_once_with(9)
        client.assert_not_called()


def test_dispatch_routes_by_kind():
    with patch.object(revocation_bus.manager, "close_session", return_value=0) as cs:
        revocation_bus.dispatch({"kind": "session", "value": "sid-1"})
        cs.assert_called_once_with("sid-1")
    with patch.object(revocation_bus.manager, "close_user", return_value=0) as cu:
        revocation_bus.dispatch({"kind": "user", "value": 42})
        cu.assert_called_once_with(42)
    with patch.object(revocation_bus.manager, "close_org", return_value=0) as co:
        revocation_bus.dispatch({"kind": "org", "value": "7"})  # value coerced to int
        co.assert_called_once_with(7)


def test_dispatch_ignores_unknown_or_incomplete_messages():
    with patch.object(revocation_bus.manager, "close_session") as cs, patch.object(
        revocation_bus.manager, "close_user"
    ) as cu, patch.object(revocation_bus.manager, "close_org") as co:
        revocation_bus.dispatch({"kind": "nope", "value": 1})
        revocation_bus.dispatch({"kind": "session"})  # no value
        cs.assert_not_called()
        cu.assert_not_called()
        co.assert_not_called()


def test_publish_failure_does_not_break_revocation(monkeypatch):
    """A Redis outage must not stop the (already-applied) local revocation."""
    monkeypatch.setattr(revocation_bus, "enabled", lambda: True)

    class Boom:
        def publish(self, *a, **k):
            raise ConnectionError("redis down")

    monkeypatch.setattr(revocation_bus, "_client", lambda: Boom())
    with patch.object(revocation_bus.manager, "close_session", return_value=2) as cs:
        assert revocation_bus.revoke_session("s1") == 2
        cs.assert_called_once_with("s1")


def test_publish_serializes_and_a_subscriber_receives(monkeypatch):
    server = fakeredis.FakeServer()
    pub = fakeredis.FakeStrictRedis(server=server, decode_responses=True)
    sub = fakeredis.FakeStrictRedis(server=server, decode_responses=True)
    pubsub = sub.pubsub()
    pubsub.subscribe(revocation_bus.CHANNEL)

    monkeypatch.setattr(revocation_bus, "enabled", lambda: True)
    monkeypatch.setattr(revocation_bus, "_client", lambda: pub)

    with patch.object(revocation_bus.manager, "close_org", return_value=0):
        revocation_bus.revoke_org(5)

    received = None
    for _ in range(20):
        msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
        if msg and msg.get("type") == "message":
            received = json.loads(msg["data"])
            break
    assert received == {"kind": "org", "value": 5}


def test_subscriber_thread_dispatches_incoming_revocation(monkeypatch):
    """End-to-end: a message published on the channel closes sockets on a worker
    running the background subscriber."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeStrictRedis(server=server, decode_responses=True)
    monkeypatch.setattr(revocation_bus, "enabled", lambda: True)
    monkeypatch.setattr(revocation_bus, "_client", lambda: client)

    closed: list[int] = []
    monkeypatch.setattr(
        revocation_bus.manager, "close_user", lambda uid: (closed.append(uid), 1)[1]
    )

    assert revocation_bus.start_subscriber() is True
    try:
        client.publish(revocation_bus.CHANNEL, json.dumps({"kind": "user", "value": 5}))
        for _ in range(60):
            if closed:
                break
            time.sleep(0.05)
        assert closed == [5]
    finally:
        revocation_bus.stop_subscriber()
