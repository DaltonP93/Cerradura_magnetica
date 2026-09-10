"""Reader/Wiegand helpers."""
from app.services.wiegand import looks_like_virtual_card, virtual_card_number


def test_virtual_card_number_zero_pads_to_ten():
    assert virtual_card_number("999999") == "0000999999"
    assert virtual_card_number("4321") == "0000004321"


def test_looks_like_virtual_card():
    assert looks_like_virtual_card("0000004321") is True
    assert looks_like_virtual_card("4321") is False        # not 10 digits
    assert looks_like_virtual_card("ABC0004321") is False  # not numeric
