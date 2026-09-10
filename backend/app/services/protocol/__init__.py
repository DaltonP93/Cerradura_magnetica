"""EXPERIMENTAL protocol codec for 4-door access controllers (Fase 2).

A pure, I/O-free encoder/decoder for the public 64-byte UHPPOTE-compatible
packet used on UDP port 60000. It is the single source of truth for the wire
format; the transport layer (services/gateway/l04_udp.py) builds/parses frames
through it.

NOT verified against this project's N3000 boards — do not treat a green codec
test as hardware validation. Confirm the real protocol with the vendor SDK or a
traffic capture before enabling the ``tcp`` gateway in production. Functions
whose real layout is unknown (e.g. per-card weekly time profiles) are left
unimplemented rather than invented.
"""
from app.services.protocol.codec import (
    FUNC_DISCOVER,
    FUNC_OPEN_DOOR,
    FUNC_PUT_CARD,
    FUNC_SET_TIME,
    FUNC_STATUS,
    CardRecord,
    build_discover,
    build_open_door,
    build_put_card,
    build_set_time,
    build_status_request,
    decode_card,
    decode_date,
    encode_card,
    encode_date,
    encode_datetime,
    from_bcd,
    parse_ack,
    parse_status,
    to_bcd,
)
from app.services.protocol.frames import (
    PACKET_SIZE,
    PACKET_TYPE,
    Frame,
    ProtocolError,
    decode_frame,
    encode_frame,
)

__all__ = [
    "PACKET_SIZE",
    "PACKET_TYPE",
    "Frame",
    "ProtocolError",
    "encode_frame",
    "decode_frame",
    "CardRecord",
    "FUNC_STATUS",
    "FUNC_SET_TIME",
    "FUNC_OPEN_DOOR",
    "FUNC_PUT_CARD",
    "FUNC_DISCOVER",
    "build_discover",
    "build_status_request",
    "build_open_door",
    "build_set_time",
    "build_put_card",
    "parse_ack",
    "parse_status",
    "encode_card",
    "decode_card",
    "encode_date",
    "decode_date",
    "encode_datetime",
    "to_bcd",
    "from_bcd",
]
