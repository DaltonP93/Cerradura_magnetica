"""64-byte control frame: pure encode/decode with validation.

Structure of the public UHPPOTE-compatible 64-byte packet (little-endian):

    offset 0     : 0x17                 start-of-message marker
    offset 1     : function code        (see codec.FUNC_*)
    offset 2-3   : reserved (0x0000)
    offset 4-7   : device serial number (uint32 LE)
    offset 8-39  : function data        (32 bytes, zero-padded)
    offset 40-43 : xID / sequence id    (uint32 LE)
    offset 44-63 : reserved (0)

This module performs NO I/O. It is the single source of truth for the wire
layout so the transport (services/gateway/l04_udp.py) and the tests share the
exact same encoding. EXPERIMENTAL: reconstructed from the public protocol, not
verified against the project's N3000 boards.
"""
import struct
from dataclasses import dataclass

PACKET_TYPE = 0x17
PACKET_SIZE = 64

_FUNCTION_OFF = 1
_SERIAL_OFF = 4
_DATA_OFF = 8
_DATA_LEN = 32
_XID_OFF = 40

_UINT32_MAX = 0xFFFFFFFF


class ProtocolError(ValueError):
    """A frame is malformed or a field is out of range."""


@dataclass(frozen=True)
class Frame:
    """A decoded control frame. ``data`` holds the function payload only."""

    function: int
    serial: int
    data: bytes = b""
    xid: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.function <= 0xFF:
            raise ProtocolError(f"function out of range: {self.function}")
        if not 0 <= self.serial <= _UINT32_MAX:
            raise ProtocolError(f"serial out of range: {self.serial}")
        if not 0 <= self.xid <= _UINT32_MAX:
            raise ProtocolError(f"xid out of range: {self.xid}")
        if len(self.data) > _DATA_LEN:
            raise ProtocolError(f"data exceeds {_DATA_LEN} bytes: {len(self.data)}")


def encode_frame(frame: Frame) -> bytes:
    """Serialize a frame to exactly 64 bytes (data zero-padded to 32)."""
    buf = bytearray(PACKET_SIZE)
    buf[0] = PACKET_TYPE
    buf[_FUNCTION_OFF] = frame.function
    struct.pack_into("<I", buf, _SERIAL_OFF, frame.serial)
    buf[_DATA_OFF : _DATA_OFF + len(frame.data)] = frame.data
    struct.pack_into("<I", buf, _XID_OFF, frame.xid)
    return bytes(buf)


def decode_frame(raw: bytes) -> Frame:
    """Parse 64 bytes into a Frame, validating length and marker.

    ``data`` is returned as the full 32-byte payload window (trailing zero
    padding included); function-level parsers slice the fields they need.
    """
    if len(raw) != PACKET_SIZE:
        raise ProtocolError(f"expected {PACKET_SIZE} bytes, got {len(raw)}")
    if raw[0] != PACKET_TYPE:
        raise ProtocolError(f"bad packet marker {raw[0]:#04x}, expected {PACKET_TYPE:#04x}")
    function = raw[_FUNCTION_OFF]
    serial = struct.unpack_from("<I", raw, _SERIAL_OFF)[0]
    data = bytes(raw[_DATA_OFF : _DATA_OFF + _DATA_LEN])
    xid = struct.unpack_from("<I", raw, _XID_OFF)[0]
    return Frame(function=function, serial=serial, data=data, xid=xid)
