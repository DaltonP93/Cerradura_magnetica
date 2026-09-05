"""In-process sliding-window rate limiting for auth endpoints.

A lightweight per-key limiter used to throttle authentication requests per
client IP. It is in-memory, so in a multi-worker deployment each worker keeps
its own window; combined with the per-account lockout (which is database-backed
and therefore shared) it provides defense in depth. For a hard cross-process
limit, front the app with a shared store (e.g. Redis) — documented here rather
than pulled in as a dependency.
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


auth_limiter = RateLimiter(get_settings().auth_rate_limit_per_minute)


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency: throttle auth requests per client IP."""
    ip = request.client.host if request.client else "unknown"
    if not auth_limiter.allow(f"auth:{ip}"):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many authentication attempts; slow down and try again shortly.",
        )
