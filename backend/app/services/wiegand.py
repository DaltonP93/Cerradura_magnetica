"""Reader/Wiegand helpers (grounded in the reader datasheets, see docs/HARDWARE.md).

A keypad reader in "virtual card number" mode emits a typed PIN as a 10-digit
decimal card number, zero-padded (e.g. PIN 999999 -> "0000999999"). This lets
the access engine resolve such a swipe back to the PIN credential that produced
it.
"""

VIRTUAL_CARD_DIGITS = 10


def virtual_card_number(pin: str) -> str:
    """The 10-digit card number a keypad emits for a numeric PIN (zero-padded)."""
    return pin.zfill(VIRTUAL_CARD_DIGITS)


def looks_like_virtual_card(card_number: str) -> bool:
    """True if the value has the shape a keypad emits for a PIN."""
    return card_number.isdigit() and len(card_number) == VIRTUAL_CARD_DIGITS
