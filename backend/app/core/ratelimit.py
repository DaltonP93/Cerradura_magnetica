"""Rate limiting for auth endpoints.

Two interchangeable limiters share one ``allow(key) -> bool`` contract:

* :class:`RateLimiter` — in-process sliding window. Fine for a single worker;
  in a multi-worker deployment each worker keeps its own window, so the
  effective limit is multiplied by the worker count.
* :class:`RedisRateLimiter` — a fixed window backed by Redis, so the per-IP
  limit is enforced **across every worker/process**. Selected automatically
  when ``ACP_REDIS_URL`` is set.

Either way the database-backed per-account lockout remains the shared,
authoritative brute-force control; the IP limiter is defense in depth.
"""
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._last_sweep = time.monotonic()

    def _sweep(self, cutoff: float) -> None:
        """Drop keys whose window is empty so idle IPs don't accumulate."""
        stale = [k for k, hits in self._hits.items() if not [t for t in hits if t >= cutoff]]
        for k in stale:
            del self._hits[k]

    def allow(self, key: str) -> bool:
        if self.limit <= 0:  # disabled
            return True
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            # Periodically evict idle keys to bound memory under many client IPs.
            if now - self._last_sweep >= self.window:
                self._sweep(cutoff)
                self._last_sweep = now
            hits = self._hits[key]
            hits[:] = [t for t in hits if t >= cutoff]
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


class RedisRateLimiter:
    """Cross-process fixed-window limiter backed by Redis.

    Each key counts requests in a ``window``-second bucket via an atomic
    ``INCR`` (with ``EXPIRE`` set on first hit). Because the counter lives in
    Redis, every worker shares it, so the per-IP limit holds for the whole
    deployment rather than per process. Fixed windows (vs. the in-memory
    sliding window) are the standard, race-free choice for a shared store.

    Fails open: if Redis is unreachable the request is allowed, so a Redis
    outage degrades throttling to "off" rather than locking every user out
    (the DB-backed per-account lockout still applies).
    """

    def __init__(self, client, limit: int, window_seconds: float = 60.0, *, namespace: str = "acp:rl:") -> None:
        self._redis = client
        self.limit = limit
        self.window = int(window_seconds)
        self._ns = namespace

    def reset(self) -> None:
        keys = list(self._redis.scan_iter(match=f"{self._ns}*"))
        if keys:
            self._redis.delete(*keys)

    def allow(self, key: str) -> bool:
        if self.limit <= 0:  # disabled
            return True
        redis_key = f"{self._ns}{key}"
        try:
            pipe = self._redis.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, self.window, nx=True)
            count, _ = pipe.execute()
        except Exception:  # noqa: BLE001 — Redis down: fail open (see docstring)
            return True
        return int(count) <= self.limit


def _build_auth_limiter():
    """In-memory by default; Redis-backed when ``ACP_REDIS_URL`` is configured."""
    settings = get_settings()
    limit = settings.auth_rate_limit_per_minute
    if settings.redis_url:
        import redis  # imported only when a Redis URL is configured

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return RedisRateLimiter(client, limit, namespace="acp:rl:auth-ip:")
    return RateLimiter(limit)


auth_limiter = _build_auth_limiter()


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency: throttle auth requests per client IP."""
    ip = request.client.host if request.client else "unknown"
    if not auth_limiter.allow(f"auth:{ip}"):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many authentication attempts; slow down and try again shortly.",
        )
