"""Redis-backed auth rate limiter (cross-worker).

Exercised against an in-memory fakeredis server, so no live Redis is required.
Two limiter instances pointed at the same server stand in for two workers and
must share one budget — the property the in-memory limiter cannot provide.
"""
import fakeredis
import pytest

from app.core.ratelimit import RateLimiter, RedisRateLimiter


@pytest.fixture
def server():
    return fakeredis.FakeServer()


def _client(server):
    return fakeredis.FakeStrictRedis(server=server, decode_responses=True)


def test_redis_limiter_enforces_fixed_window(server):
    rl = RedisRateLimiter(_client(server), limit=3, window_seconds=60)
    assert [rl.allow("auth:1.2.3.4") for _ in range(5)] == [True, True, True, False, False]
    # A different key has its own budget.
    assert rl.allow("auth:9.9.9.9") is True


def test_redis_limiter_shared_across_workers(server):
    """Two limiters on the same Redis share the budget (unlike in-memory)."""
    worker_a = RedisRateLimiter(_client(server), limit=3, window_seconds=60)
    worker_b = RedisRateLimiter(_client(server), limit=3, window_seconds=60)
    key = "auth:5.5.5.5"
    assert worker_a.allow(key) is True   # 1
    assert worker_b.allow(key) is True   # 2 (seen by the other worker)
    assert worker_a.allow(key) is True   # 3
    assert worker_b.allow(key) is False  # 4 — over the shared limit
    assert worker_a.allow(key) is False


def test_in_memory_limiter_is_per_process(server):
    """Contrast: two in-memory limiters do NOT share a budget."""
    a = RateLimiter(limit=1, window_seconds=60)
    b = RateLimiter(limit=1, window_seconds=60)
    assert a.allow("auth:x") is True
    assert b.allow("auth:x") is True  # b never saw a's hit


def test_redis_limiter_expires_window(server):
    rl = RedisRateLimiter(_client(server), limit=1, window_seconds=60)
    key = "auth:7.7.7.7"
    assert rl.allow(key) is True
    assert rl.allow(key) is False
    # Simulate the fixed window elapsing by dropping the bucket the limiter uses.
    rl._redis.delete(f"{rl._ns}{key}")
    assert rl.allow(key) is True


def test_redis_limiter_disabled_when_limit_zero(server):
    rl = RedisRateLimiter(_client(server), limit=0, window_seconds=60)
    assert all(rl.allow("auth:1.1.1.1") for _ in range(10))


def test_redis_limiter_fails_open_when_backend_errors():
    class Boom:
        def pipeline(self):
            raise ConnectionError("redis down")

    rl = RedisRateLimiter(Boom(), limit=1, window_seconds=60)
    # Backend unreachable → allow (fail open); DB lockout still protects accounts.
    assert rl.allow("auth:1.1.1.1") is True


def test_reset_clears_namespace(server):
    client = _client(server)
    rl = RedisRateLimiter(client, limit=1, window_seconds=60)
    rl.allow("auth:2.2.2.2")
    assert rl.allow("auth:2.2.2.2") is False
    rl.reset()
    assert rl.allow("auth:2.2.2.2") is True
