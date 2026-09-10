"""EXPERIMENTAL UDP gateway for 4-door TCP/IP access control boards.

Transport only: it sends/receives the 64-byte UDP packets on port 60000 and
delegates ALL encoding/decoding to the pure ``app.services.protocol`` codec.
The legacy N3000 boards of this project use the same port, but the wire
protocol has NOT been verified against this implementation — confirm it with
the vendor SDK or a traffic capture before using this mode in production (see
docs/HARDWARE.md).
"""
import asyncio
import logging
from datetime import date, datetime

from app.models import Controller, Door
from app.services.gateway.base import ControllerGateway, GatewayResult
from app.services.protocol import (
    CardRecord,
    build_open_door,
    build_put_card,
    build_set_time,
    build_status_request,
    encode_frame,
    parse_ack,
    parse_status,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 3.0


class _UdpExchange(asyncio.DatagramProtocol):
    def __init__(self, request: bytes) -> None:
        self.request = request
        self.response: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        transport.sendto(self.request)

    def datagram_received(self, data: bytes, addr) -> None:
        if not self.response.done():
            self.response.set_result(data)

    def error_received(self, exc: Exception) -> None:
        if not self.response.done():
            self.response.set_exception(exc)


class L04UdpGateway(ControllerGateway):
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    async def _send(self, controller: Controller, packet: bytes) -> bytes:
        if not controller.ip_address:
            raise ConnectionError("Controller has no IP address configured")
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UdpExchange(packet),
            remote_addr=(controller.ip_address, controller.port),
        )
        try:
            return await asyncio.wait_for(protocol.response, timeout=self.timeout)
        finally:
            transport.close()

    @staticmethod
    def _serial(controller: Controller) -> int:
        digits = "".join(ch for ch in controller.serial_number if ch.isdigit())
        if not digits:
            raise ValueError(f"Serial number {controller.serial_number!r} has no numeric part")
        return int(digits) & 0xFFFFFFFF

    async def ping(self, controller: Controller) -> GatewayResult:
        try:
            serial = self._serial(controller)
            response = await self._send(controller, encode_frame(build_status_request(serial)))
            status = parse_status(response)
            return GatewayResult(True, "Board responded", {"raw_status": status["payload"]})
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Board unreachable: {exc}")

    async def open_door(self, controller: Controller, door: Door) -> GatewayResult:
        try:
            serial = self._serial(controller)
            response = await self._send(controller, encode_frame(build_open_door(serial, door.number)))
            ok = parse_ack(response)
            return GatewayResult(ok, "Open command accepted" if ok else "Board rejected open command")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Open command failed: {exc}")

    async def sync_time(self, controller: Controller) -> GatewayResult:
        try:
            serial = self._serial(controller)
            now = datetime.now()
            await self._send(controller, encode_frame(build_set_time(serial, now)))
            return GatewayResult(True, f"Board time set to {now:%Y-%m-%d %H:%M:%S}")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Time sync failed: {exc}")

    async def sync_permissions(self, controller: Controller, cards: list[dict]) -> GatewayResult:
        try:
            serial = self._serial(controller)
            sent = 0
            for card in cards:
                record = _card_record(card)
                await self._send(controller, encode_frame(build_put_card(serial, record)))
                sent += 1
            return GatewayResult(True, f"{sent} card permissions uploaded")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Permission sync failed: {exc}")


def _card_record(card: dict) -> CardRecord:
    number = int("".join(ch for ch in str(card["card_number"]) if ch.isdigit()) or 0)
    doors = tuple(card.get("doors") or (1, 2, 3, 4))
    return CardRecord(
        number=number & 0xFFFFFFFF,
        doors=doors,
        valid_from=_as_date(card.get("valid_from")),
        valid_to=_as_date(card.get("valid_to")),
    )


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    return None
