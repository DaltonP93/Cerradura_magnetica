"""Gateway factory: selects the hardware backend from configuration."""
from functools import lru_cache

from app.core.config import get_settings
from app.services.gateway.base import ControllerGateway, GatewayResult
from app.services.gateway.l04_udp import L04UdpGateway
from app.services.gateway.simulated import SimulatedGateway

__all__ = ["ControllerGateway", "GatewayResult", "get_gateway"]


@lru_cache
def get_gateway() -> ControllerGateway:
    settings = get_settings()
    if settings.gateway_mode == "tcp":
        return L04UdpGateway()
    return SimulatedGateway()
