"""Gateway factory: selects the hardware backend from configuration."""
import asyncio
from collections.abc import Coroutine
from functools import lru_cache
from typing import Any, TypeVar

from app.core.config import get_settings
from app.services.gateway.base import ControllerGateway, GatewayResult
from app.services.gateway.l04_udp import L04UdpGateway
from app.services.gateway.simulated import SimulatedGateway

__all__ = ["ControllerGateway", "GatewayResult", "call_gateway", "get_gateway"]

_T = TypeVar("_T")


def call_gateway(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async gateway coroutine to completion from a synchronous endpoint.

    The gateway-calling endpoints are plain ``def`` handlers, so FastAPI runs
    them in a worker thread that never blocks the main event loop. That thread
    has no running loop, so ``asyncio.run`` spins a private loop for the single
    network round-trip. Callers release the DB transaction *before* invoking
    this, so no connection is held across the I/O.
    """
    return asyncio.run(coro)


@lru_cache
def get_gateway() -> ControllerGateway:
    settings = get_settings()
    if settings.gateway_mode == "tcp":
        return L04UdpGateway()
    return SimulatedGateway()
