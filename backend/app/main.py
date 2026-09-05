import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.router import api_router, ws_router
from app.core import metrics
from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.database import Base, engine, get_db
from app.core.observability import RequestContextMiddleware, configure_logging
from app.services.events import set_main_loop

logging.basicConfig(level=logging.INFO)
settings = get_settings()
configure_logging(settings.json_logs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables when running without Alembic (dev/tests). Production is
    # schema-managed by `alembic upgrade head`, so never auto-create there.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
    set_main_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Multi-tenant SaaS platform for managing L04-style 4-door access control boards: "
        "controllers, doors, cardholders, credentials, schedules, access levels, "
        "real-time monitoring and reporting."
    ),
    lifespan=lifespan,
)

# CSRF is added before CORS so that, in the final middleware stack, CORS runs
# first (outermost) and still answers preflight requests.
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added last so it is the outermost middleware: every request gets a correlation
# id and one structured access-log line, wrapping CORS/CSRF and the handlers.
app.add_middleware(RequestContextMiddleware)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
def health():
    """Liveness: the process is up (no dependency checks)."""
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/health/ready", tags=["health"])
def readiness(db: Session = Depends(get_db)):
    """Readiness: the app can serve traffic, i.e. the database is reachable."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - report any DB failure as not-ready
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics", tags=["health"])
def prometheus_metrics(request: Request):
    """Prometheus metrics. Gated by ACP_METRICS_TOKEN when configured."""
    token = settings.metrics_token
    if token:
        header = request.headers.get("authorization", "")
        presented = header[7:] if header.lower().startswith("bearer ") else request.headers.get("x-metrics-token")
        if presented != token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid metrics token")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
