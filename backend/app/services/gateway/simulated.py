"""In-memory gateway used in development and tests: every board responds."""
from datetime import UTC, datetime

from app.models import Controller, Door
from app.services.gateway.base import ControllerGateway, GatewayResult


class SimulatedGateway(ControllerGateway):
    def __init__(self) -> None:
        self.opened_doors: list[tuple[str, int]] = []  # (serial, door number) log for tests
        self.synced: list[str] = []

    async def ping(self, controller: Controller) -> GatewayResult:
        return GatewayResult(
            True,
            "Simulated board online",
            {"serial": controller.serial_number, "time": datetime.now(UTC).isoformat()},
        )

    async def open_door(self, controller: Controller, door: Door) -> GatewayResult:
        self.opened_doors.append((controller.serial_number, door.number))
        return GatewayResult(True, f"Door {door.number} opened for {door.open_duration_seconds}s (simulated)")

    async def sync_time(self, controller: Controller) -> GatewayResult:
        self.synced.append(controller.serial_number)
        return GatewayResult(True, "Board time synchronized (simulated)")

    async def sync_permissions(self, controller: Controller, cards: list[dict]) -> GatewayResult:
        return GatewayResult(True, f"{len(cards)} card permissions uploaded (simulated)")
