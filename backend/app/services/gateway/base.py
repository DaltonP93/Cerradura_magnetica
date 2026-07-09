"""Hardware gateway abstraction.

The platform talks to L04-style access control boards through this interface,
so the rest of the code never depends on the wire protocol. Two
implementations exist:

* ``SimulatedGateway`` – in-memory, used for development, demos and tests.
* ``L04UdpGateway`` – speaks the 64-byte UDP packet protocol used by common
  4-door TCP/IP boards (default port 60000).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models import Controller, Door


@dataclass
class GatewayResult:
    success: bool
    message: str
    data: dict | None = None


class ControllerGateway(ABC):
    @abstractmethod
    async def ping(self, controller: Controller) -> GatewayResult:
        """Query the board; used for online/offline detection."""

    @abstractmethod
    async def open_door(self, controller: Controller, door: Door) -> GatewayResult:
        """Pulse the lock relay for the door's configured open duration."""

    @abstractmethod
    async def sync_time(self, controller: Controller) -> GatewayResult:
        """Set the board clock to the server's current time."""

    @abstractmethod
    async def sync_permissions(self, controller: Controller, cards: list[dict]) -> GatewayResult:
        """Upload card permissions to the board for offline decision-making.

        ``cards`` items: {card_number, doors: [1..4], valid_from: date, valid_to: date}
        """
