"""Card-number masking for events and audit (invariant #6)."""
from app.core.masking import mask_card


def test_mask_keeps_last_four():
    assert mask_card("1234567890") == "******7890"


def test_mask_short_card_fully_hidden():
    assert mask_card("1234") == "****"
    assert mask_card("55") == "**"


def test_mask_empty_and_none():
    assert mask_card("") == ""
    assert mask_card(None) == ""
