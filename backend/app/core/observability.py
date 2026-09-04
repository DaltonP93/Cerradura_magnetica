"""Operational observability: per-request correlation id and structured logs.

A middleware assigns each request a correlation id (honoring an inbound
``X-Request-ID`` from the edge, else generating one), exposes it via a
ContextVar and echoes it on the response, and logs one structured line per
request (method, path, status, duration). Set ``ACP_JSON_LOGS=true`` to emit
logs as JSON for ingestion by a log pipeline; otherwise a concise text line is
used (dev-friendly, unchanged test output).
"""
import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

access_logger = logging.getLogger("acp.access")


def get_request_id() -> str:
    return _request_id.get()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", _request_id.get()),
        }
        for key in ("method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(json_logs: bool) -> None:
    """Attach a JSON formatter to the root handlers when structured logs are on."""
    if not json_logs:
        return
    formatter = _JsonFormatter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setFormatter(formatter)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex
        token = _request_id.set(request_id)
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            access_logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code if response is not None else 500,
                    "duration_ms": duration_ms,
                },
            )
            if response is not None:
                response.headers[REQUEST_ID_HEADER] = request_id
            _request_id.reset(token)
