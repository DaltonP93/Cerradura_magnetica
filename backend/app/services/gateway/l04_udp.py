"""EXPERIMENTAL UDP gateway for 4-door TCP/IP access control boards.

Implements the public 64-byte binary packet protocol used by
UHPPOTE-compatible 4-door controllers on UDP port 60000. The legacy N3000
boards of this project use the same port, but their wire protocol has NOT
been verified against this implementation — confirm it with the vendor SDK
or a traffic capture before using this mode in production (see
docs/HARDWARE.md). Every packet:

    offset 0   : 0x17            (packet type)
    offset 1   : function code   (0x20 status, 0x30 set time, 0x40 open door,
                                  0x50 put card, 0x94 discover)
    offset 4-7 : controller serial number, little-endian uint32
    offset 8.. : function payload
    total      : 64 bytes

If your board revision uses different opcodes, adjust ``FUNC_*`` below to
match the vendor SDK — the rest of the platform is unaffected.
"""
import asyncio
import logging
import struct
from datetime import datetime

from app.models import Controller, Door
from app.services.gateway.base import ControllerGateway, GatewayResult

logger = logging.getLogger(__name__)

PACKET_TYPE = 0x17
FUNC_STATUS = 0x20
FUNC_SET_TIME = 0x30
FUNC_OPEN_DOOR = 0x40
FUNC_PUT_CARD = 0x50
FUNC_DISCOVER = 0x94

PACKET_SIZE = 64
DEFAULT_TIMEOUT = 3.0


def _bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def _build_packet(function: int, serial: int, payload: bytes = b"") -> bytes:
    packet = bytearray(PACKET_SIZE)
    packet[0] = PACKET_TYPE
    packet[1] = function
    struct.pack_into("<I", packet, 4, serial)
    packet[8 : 8 + len(payload)] = payload
    return bytes(packet)


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
            response = await self._send(controller, _build_packet(FUNC_STATUS, serial))
            if len(response) >= 8 and response[0] == PACKET_TYPE:
                return GatewayResult(True, "Board responded", {"raw_status": response[:32].hex()})
            return GatewayResult(False, "Unexpected response from board")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Board unreachable: {exc}")

    async def open_door(self, controller: Controller, door: Door) -> GatewayResult:
        try:
            serial = self._serial(controller)
            payload = bytes([door.number])
            response = await self._send(controller, _build_packet(FUNC_OPEN_DOOR, serial, payload))
            ok = len(response) >= 9 and response[8] == 1
            return GatewayResult(ok, "Open command accepted" if ok else "Board rejected open command")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Open command failed: {exc}")

    async def sync_time(self, controller: Controller) -> GatewayResult:
        try:
            serial = self._serial(controller)
            now = datetime.now()
            payload = bytes(
                [
                    _bcd(now.year // 100),
                    _bcd(now.year % 100),
                    _bcd(now.month),
                    _bcd(now.day),
                    _bcd(now.hour),
                    _bcd(now.minute),
                    _bcd(now.second),
                    _bcd(now.isoweekday() % 7),
                ]
            )
            await self._send(controller, _build_packet(FUNC_SET_TIME, serial, payload))
            return GatewayResult(True, f"Board time set to {now:%Y-%m-%d %H:%M:%S}")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Time sync failed: {exc}")

    async def sync_permissions(self, controller: Controller, cards: list[dict]) -> GatewayResult:
        try:
            serial = self._serial(controller)
            sent = 0
            for card in cards:
                number = int("".join(ch for ch in str(card["card_number"]) if ch.isdigit()) or 0)
                doors: list[int] = card.get("doors", [1, 2, 3, 4])
                valid_from = card.get("valid_from")
                valid_to = card.get("valid_to")
                payload = struct.pack("<I", number & 0xFFFFFFFF)
                payload += _date_bcd(valid_from) + _date_bcd(valid_to)
                payload += bytes(1 if d in doors else 0 for d in (1, 2, 3, 4))
                await self._send(controller, _build_packet(FUNC_PUT_CARD, serial, payload))
                sent += 1
            return GatewayResult(True, f"{sent} card permissions uploaded")
        except (TimeoutError, OSError, ConnectionError, ValueError) as exc:
            return GatewayResult(False, f"Permission sync failed: {exc}")


def _date_bcd(value) -> bytes:
    if value is None:
        return bytes([_bcd(20), _bcd(0), _bcd(1), _bcd(1)])  # 2000-01-01 = unrestricted
    return bytes([_bcd(value.year // 100), _bcd(value.year % 100), _bcd(value.month), _bcd(value.day)])
