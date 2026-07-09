import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router, ws_router
from app.core.config import get_settings
from app.core.database import Base, engine

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables when running without Alembic (dev/tests). In production,
    # run `alembic upgrade head` before starting the app.
    Base.metadata.create_all(bind=engine)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}
