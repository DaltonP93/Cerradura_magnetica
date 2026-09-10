"""Cross-worker session-revocation fan-out over Redis Pub/Sub.

Revoking a session (logout, refresh-reuse, password change, user suspension,
org suspension) must drop that user's *live* monitoring WebSockets. The
in-process signal in ``ConnectionManager`` only reaches sockets served by the
same worker; the periodic DB revalidation (``ws_revalidate_seconds``) is the
cross-worker safety net but is not instant.

When ``ACP_REDIS_URL`` is set, this module publishes each revocation to a Redis
channel and every worker subscribes, so a revocation performed on one worker
closes matching sockets on *all* workers within milliseconds. When Redis is not
configured this is a no-op and the DB revalidation remains the safety net.

Threading: publishing and dispatch both call the manager's ``close_*`` methods,
which only *signal* each connection (thread-safe via ``call_soon_threadsafe``),
so the subscriber can run in a plain daemon thread. Publishing is best-effort:
the local close already happened, so a Redis outage never blocks a revocation.
"""
import json
import logging
import threading

from app.core.config import get_settings
from app.services.events import manager

logger = logging.getLogger("acp.revocation")

CHANNEL = "acp:revocation"

_publisher = None  # lazily-created Redis client (publisher side)
_subscriber_thread: threading.Thread | None = None
_pubsub = None
_stop = threading.Event()


def enabled() -> bool:
    return bool(get_settings().redis_url)


def _client():
    global _publisher
    if _publisher is None:
        import redis  # imported only when Redis is configured

        _publisher = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _publisher


def _publish(kind: str, value: object) -> None:
    if not enabled():
        return
    try:
        _client().publish(CHANNEL, json.dumps({"kind": kind, "value": value}))
    except Exception:  # noqa: BLE001 — best effort: the local close already ran
        logger.warning("revocation publish failed (kind=%s); relying on DB revalidation", kind)


# --- revocation entry points (call these instead of manager.close_* directly) ---
def revoke_session(session_id: str) -> int:
    """Close the session's live sockets locally and fan the revocation out."""
    closed = manager.close_session(session_id)
    _publish("session", session_id)
    return closed


def revoke_user(user_id: int) -> int:
    closed = manager.close_user(user_id)
    _publish("user", user_id)
    return closed


def revoke_org(org_id: int) -> int:
    closed = manager.close_org(org_id)
    _publish("org", org_id)
    return closed


def dispatch(message: dict) -> None:
    """Apply a revocation received from the bus to this worker's sockets only.

    Never re-publishes (avoids an echo loop); closing an already-closed socket
    is a harmless no-op, so receiving our own publish back is fine.
    """
    kind = message.get("kind")
    value = message.get("value")
    if value is None:
        return
    if kind == "session":
        manager.close_session(str(value))
    elif kind == "user":
        manager.close_user(int(value))
    elif kind == "org":
        manager.close_org(int(value))


def _run() -> None:
    assert _pubsub is not None
    while not _stop.is_set():
        try:
            msg = _pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        except Exception:  # noqa: BLE001 — a transient Redis error must not kill the loop
            logger.warning("revocation subscriber read failed; retrying")
            if _stop.wait(1.0):
                break
            continue
        if not msg or msg.get("type") != "message":
            continue
        try:
            dispatch(json.loads(msg["data"]))
        except Exception:  # noqa: BLE001 — one bad message must not kill the loop
            logger.exception("revocation dispatch failed")


def start_subscriber() -> bool:
    """Start the background subscriber if Redis is configured. Idempotent."""
    global _subscriber_thread, _pubsub
    if not enabled() or (_subscriber_thread is not None and _subscriber_thread.is_alive()):
        return False
    _pubsub = _client().pubsub()
    _pubsub.subscribe(CHANNEL)
    _stop.clear()
    _subscriber_thread = threading.Thread(target=_run, name="revocation-bus", daemon=True)
    _subscriber_thread.start()
    logger.info("revocation bus subscriber started on channel %s", CHANNEL)
    return True


def stop_subscriber() -> None:
    _stop.set()
    thread, pubsub = _subscriber_thread, _pubsub
    if thread is not None:
        thread.join(timeout=2.0)
    if pubsub is not None:
        try:
            pubsub.close()
        except Exception:  # noqa: BLE001
            pass
