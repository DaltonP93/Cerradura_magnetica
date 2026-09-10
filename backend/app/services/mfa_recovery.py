"""One-time MFA recovery codes (F-5).

A user who loses their TOTP device would otherwise be locked out permanently.
At enable (and on demand) we hand out a set of single-use recovery codes and
store only their SHA-256 hashes. At login, if the TOTP code fails, a recovery
code can be presented instead; a matching code is consumed (removed) so it can
never be reused. Plaintext codes are shown to the user exactly once — they are
never stored and never returned again.
"""
import secrets

from app.core.security import hash_token
from app.models import User

CODE_COUNT = 10
# 8 random bytes -> 16 hex chars; ~64 bits of entropy per single-use code.
_CODE_BYTES = 8


def generate() -> tuple[list[str], list[str]]:
    """Return ``(plaintext_codes, hashes)``. Persist only the hashes."""
    codes = [secrets.token_hex(_CODE_BYTES) for _ in range(CODE_COUNT)]
    return codes, [hash_token(c) for c in codes]


def consume(user: User, presented: str) -> bool:
    """Consume ``presented`` if it matches an unused recovery code.

    Returns True and removes the matched hash (reassigning the list so the ORM
    flushes the change). The scan is constant-time per stored entry and always
    visits every entry, so it does not leak which position matched.
    """
    stored = list(user.mfa_recovery_hashes or [])
    if not stored or not presented:
        return False
    target = hash_token(presented.strip())
    matched: str | None = None
    for h in stored:
        if secrets.compare_digest(h, target):
            matched = h
    if matched is None:
        return False
    user.mfa_recovery_hashes = [h for h in stored if h != matched]
    return True


def remaining(user: User) -> int:
    return len(user.mfa_recovery_hashes or [])
