from fastapi import APIRouter

from app.api.v1 import (
    access_levels,
    attendance,
    audit,
    auth,
    cardholders,
    controllers,
    dashboard,
    departments,
    doors,
    events,
    gateway_bridge,
    organizations,
    schedules,
    sites,
    users,
    ws,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(users.router)
api_router.include_router(sites.router)
api_router.include_router(controllers.router)
api_router.include_router(doors.router)
api_router.include_router(departments.router)
api_router.include_router(cardholders.router)
api_router.include_router(schedules.router)
api_router.include_router(access_levels.router)
api_router.include_router(attendance.router)
api_router.include_router(events.router)
api_router.include_router(dashboard.router)
api_router.include_router(audit.router)
api_router.include_router(gateway_bridge.router)

ws_router = ws.router
