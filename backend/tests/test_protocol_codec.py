"""Pure unit tests for the experimental 64-byte protocol codec (Fase 2).

No hardware, no network: these validate the wire format and round-trips only.
The hex vectors are SYNTHETIC (constructed from the public layout), not captures
from a real board.
"""
from datetime import date, datetime

import pytest

from app.services.protocol import (
    FUNC_OPEN_DOOR,
    FUNC_SET_TIME,
    CardRecord,
    ProtocolError,
    build_open_door,
    build_put_card,
    build_set_time,
    build_status_request,
    decode_card,
    decode_date,
    decode_frame,
    encode_card,
    encode_date,
    encode_frame,
    from_bcd,
    parse_ack,
    to_bcd,
)
from app.services.protocol.frames import Frame

SERIAL = 0x12345678  # 305419896


def test_frame_is_64_bytes_with_marker_and_le_serial():
    raw = encode_frame(build_open_door(SERIAL, 1))
    assert len(raw) == 64
    # marker, function, reserved, serial (LE), door byte
    assert raw[:9].hex() == "174000007856341201"
    assert raw[40:44] == b"\x00\x00\x00\x00"  # xid


def test_xid_is_encoded_little_endian_and_round_trips():
    raw = encode_frame(Frame(function=FUNC_OPEN_DOOR, serial=SERIAL, data=b"\x01", xid=0x0A0B0C0D))
    assert raw[40:44] == bytes([0x0D, 0x0C, 0x0B, 0x0A])
    assert decode_frame(raw).xid == 0x0A0B0C0D


def test_frame_bytes_round_trip():
    original = encode_frame(build_set_time(SERIAL, datetime(2026, 9, 1, 8, 30, 15), xid=7))
    frame = decode_frame(original)
    assert frame.function == FUNC_SET_TIME
    assert frame.serial == SERIAL
    assert frame.xid == 7
    assert encode_frame(frame) == original  # bytes -> frame -> bytes identity


def test_decode_rejects_bad_length_and_marker():
    with pytest.raises(ProtocolError):
        decode_frame(b"\x17" * 63)  # too short
    with pytest.raises(ProtocolError):
        decode_frame(b"\x00" + b"\x00" * 63)  # wrong marker


def test_open_door_validates_range():
    for bad in (0, 5, -1):
        with pytest.raises(ProtocolError):
            build_open_door(SERIAL, bad)


def test_bcd_round_trip_and_validation():
    for n in (0, 5, 42, 99):
        assert from_bcd(to_bcd(n)) == n
    with pytest.raises(ProtocolError):
        to_bcd(100)
    with pytest.raises(ProtocolError):
        from_bcd(0x1A)  # not valid BCD


def test_date_round_trip_and_unrestricted():
    d = date(2026, 12, 31)
    assert decode_date(encode_date(d)) == d
    assert decode_date(encode_date(None)) is None  # 2000-01-01 sentinel


def test_card_record_round_trip():
    card = CardRecord(number=10001, doors=(1, 3), valid_from=date(2026, 1, 1), valid_to=date(2026, 6, 30))
    decoded = decode_card(encode_card(card))
    assert decoded.number == 10001
    assert decoded.doors == (1, 3)
    assert decoded.valid_from == date(2026, 1, 1)
    assert decoded.valid_to == date(2026, 6, 30)


def test_put_card_frame_carries_16_byte_payload():
    frame = decode_frame(encode_frame(build_put_card(SERIAL, CardRecord(number=42))))
    assert frame.function == 0x50
    assert decode_card(frame.data).number == 42


def test_parse_ack_true_and_false():
    ack = encode_frame(Frame(function=FUNC_OPEN_DOOR, serial=SERIAL, data=b"\x01"))
    nak = encode_frame(Frame(function=FUNC_OPEN_DOOR, serial=SERIAL, data=b"\x00"))
    assert parse_ack(ack) is True
    assert parse_ack(nak) is False


def test_status_request_has_empty_payload():
    frame = decode_frame(encode_frame(build_status_request(SERIAL)))
    assert frame.function == 0x20
    assert frame.data == b"\x00" * 32  # no payload


def test_synthetic_open_door_vector_decodes():
    """A hand-built (synthetic) open-door frame decodes to the expected fields."""
    raw = bytes.fromhex(
        "17" "40" "0000" "78563412" "01" + "00" * 31 + "00000000" + "00" * 20
    )
    assert len(raw) == 64
    frame = decode_frame(raw)
    assert frame.function == FUNC_OPEN_DOOR
    assert frame.serial == SERIAL
    assert frame.data[0] == 1
    assert parse_ack(raw) is True
