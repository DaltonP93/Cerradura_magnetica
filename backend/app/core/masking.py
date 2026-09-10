"""Helpers to keep sensitive identifiers out of events, audit logs and messages.

Invariant #6 forbids exposing card data. Events and audit rows are operational
and queryable, so card numbers are stored masked (last four digits only). The
real card of a *known* swipe is still recoverable through the event's
``credential_id`` relation, which is access-controlled.
"""


def mask_card(card: str | None) -> str:
    """Return a card number with all but the last four digits masked.

    Cards of four digits or fewer are fully masked so short numbers are never
    revealed in the clear.
    """
    if not card:
        return ""
    tail = card[-4:] if len(card) > 4 else ""
    return ("*" * (len(card) - len(tail))) + tail
