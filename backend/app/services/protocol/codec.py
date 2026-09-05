"""Function-level builders and parsers over the 64-byte frame.

Pure and side-effect free. Covers the publicly documented functions the
platform uses (status, open door, set time, put card, discover). Fields whose
real layout is unknown for the N3000 boards (e.g. per-card weekly time
profiles) are intentionally left out rather than invented — see docs/HARDWARE.md
and the project rule "no inventar el protocolo".
"""
import struct
from dataclasses import dataclass
from datetime import date, datetime

from app.services.protocol.frames import Frame, ProtocolError, decode_frame

# Function codes (public UHPPOTE-compatible set; adjust to the vendor SDK once
# the real protocol is confirmed).
FUNC_STATUS = 0x20
FUNC_SET_TIME = 0x30
FUNC_OPEN_DOOR = 0x40
FUNC_PUT_CARD = 0x50
FUNC_DISCOVER = 0x94

_DOORS = (1, 2, 3, 4)


# --- BCD and date/time helpers ------------------------------------------------
def to_bcd(value: int) -> int:
    """Encode a 0-99 integer as a single packed-BCD byte."""
    if not 0 <= value <= 99:
        raise ProtocolError(f"BCD value out of range 0-99: {value}")
    return ((value // 10) << 4) | (value % 10)


def from_bcd(byte: int) -> int:
    hi, lo = (byte >> 4) & 0xF, byte & 0xF
    if hi > 9 or lo > 9:
        raise ProtocolError(f"invalid BCD byte: {byte:#04x}")
    return hi * 10 + lo


_UNRESTRICTED = bytes([to_bcd(20), to_bcd(0), to_bcd(1), to_bcd(1)])  # 2000-01-01


def encode_date(value: date | None) -> bytes:
    """4-byte BCD date (century, year, month, day). None => unrestricted."""
    if value is None:
        return _UNRESTRICTED
    return bytes([to_bcd(value.year // 100), to_bcd(value.year % 100), to_bcd(value.month), to_bcd(value.day)])


def decode_date(raw: bytes) -> date | None:
    if len(raw) != 4:
        raise ProtocolError(f"date must be 4 bytes, got {len(raw)}")
    year = from_bcd(raw[0]) * 100 + from_bcd(raw[1])
    month, day = from_bcd(raw[2]), from_bcd(raw[3])
    if raw == _UNRESTRICTED:
        return None
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ProtocolError(f"invalid date {year}-{month}-{day}") from exc


def encode_datetime(now: datetime) -> bytes:
    """7-byte BCD timestamp used by set-time (no weekday)."""
    return bytes(
        [
            to_bcd(now.year // 100),
            to_bcd(now.year % 100),
            to_bcd(now.month),
            to_bcd(now.day),
            to_bcd(now.hour),
            to_bcd(now.minute),
            to_bcd(now.second),
        ]
    )


# --- Card record --------------------------------------------------------------
@dataclass(frozen=True)
class CardRecord:
    number: int
    doors: tuple[int, ...] = _DOORS
    valid_from: date | None = None
    valid_to: date | None = None


def encode_card(card: CardRecord) -> bytes:
    """16-byte put-card payload: number(LE u32) + from(4) + to(4) + door flags(4)."""
    if not 0 <= card.number <= 0xFFFFFFFF:
        raise ProtocolError(f"card number out of range: {card.number}")
    for d in card.doors:
        if d not in _DOORS:
            raise ProtocolError(f"door out of range 1-4: {d}")
    payload = struct.pack("<I", card.number)
    payload += encode_date(card.valid_from) + encode_date(card.valid_to)
    payload += bytes(1 if d in card.doors else 0 for d in _DOORS)
    return payload


def decode_card(payload: bytes) -> CardRecord:
    if len(payload) < 16:
        raise ProtocolError(f"card payload must be >= 16 bytes, got {len(payload)}")
    number = struct.unpack_from("<I", payload, 0)[0]
    valid_from = decode_date(payload[4:8])
    valid_to = decode_date(payload[8:12])
    doors = tuple(d for i, d in enumerate(_DOORS) if payload[12 + i] == 1)
    return CardRecord(number=number, doors=doors, valid_from=valid_from, valid_to=valid_to)


# --- Frame builders -----------------------------------------------------------
def build_discover(xid: int = 0) -> Frame:
    return Frame(function=FUNC_DISCOVER, serial=0, xid=xid)


def build_status_request(serial: int, xid: int = 0) -> Frame:
    return Frame(function=FUNC_STATUS, serial=serial, xid=xid)


def build_open_door(serial: int, door: int, xid: int = 0) -> Frame:
    if door not in _DOORS:
        raise ProtocolError(f"door out of range 1-4: {door}")
    return Frame(function=FUNC_OPEN_DOOR, serial=serial, data=bytes([door]), xid=xid)


def build_set_time(serial: int, now: datetime, xid: int = 0) -> Frame:
    return Frame(function=FUNC_SET_TIME, serial=serial, data=encode_datetime(now), xid=xid)


def build_put_card(serial: int, card: CardRecord, xid: int = 0) -> Frame:
    return Frame(function=FUNC_PUT_CARD, serial=serial, data=encode_card(card), xid=xid)


# --- Response parsers ---------------------------------------------------------
def parse_ack(raw: bytes) -> bool:
    """Boolean acknowledgement: first payload byte == 1 (open door / put card)."""
    frame = decode_frame(raw)
    return len(frame.data) >= 1 and frame.data[0] == 1


def parse_status(raw: bytes) -> dict:
    """Best-effort status parse: exposes the raw payload for the caller to log."""
    frame = decode_frame(raw)
    return {"function": frame.function, "serial": frame.serial, "payload": frame.data.hex()}
