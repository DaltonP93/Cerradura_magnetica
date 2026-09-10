"""Minimal in-process metrics in Prometheus text exposition format.

Dependency-free and thread-safe. Counts HTTP requests by method and status and
accumulates request-duration sum/count (for average latency). In a multi-worker
deployment each worker keeps its own counters (same caveat as the in-memory
rate limiter); scrape per worker or front with a shared collector if needed.
"""
import threading
from collections import defaultdict

_lock = threading.Lock()
_requests_total: dict[tuple[str, str], int] = defaultdict(int)
_duration_sum: float = 0.0
_duration_count: int = 0


def observe_request(method: str, status: int, duration_seconds: float) -> None:
    global _duration_sum, _duration_count
    with _lock:
        _requests_total[(method.upper(), str(status))] += 1
        _duration_sum += duration_seconds
        _duration_count += 1


def reset() -> None:
    """Clear all metrics (used by tests)."""
    global _duration_sum, _duration_count
    with _lock:
        _requests_total.clear()
        _duration_sum = 0.0
        _duration_count = 0


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render() -> str:
    lines = [
        "# HELP acp_http_requests_total Total HTTP requests processed.",
        "# TYPE acp_http_requests_total counter",
    ]
    with _lock:
        for (method, status), count in sorted(_requests_total.items()):
            lines.append(
                f'acp_http_requests_total{{method="{_escape(method)}",status="{_escape(status)}"}} {count}'
            )
        lines.append("# HELP acp_http_request_duration_seconds Cumulative request duration.")
        lines.append("# TYPE acp_http_request_duration_seconds summary")
        lines.append(f"acp_http_request_duration_seconds_sum {_duration_sum}")
        lines.append(f"acp_http_request_duration_seconds_count {_duration_count}")
    return "\n".join(lines) + "\n"
