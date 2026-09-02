"""Symmetric encryption for recoverable secrets stored at rest (e.g. PINs).

PINs must be recoverable — the access engine compares them and, on real
hardware, they are uploaded to the controller — so they cannot be hashed. They
are instead encrypted with Fernet (AES-128-CBC + HMAC) using a key that lives
outside the database: either an explicit ``ACP_PIN_ENCRYPTION_KEY`` or, by
default, a key derived from ``ACP_SECRET_KEY`` via HKDF with a dedicated info
label (so it is distinct from the JWT signing key). The ciphertext is stored;
the plaintext never touches the database.

The :class:`EncryptedString` SQLAlchemy type encrypts on the way in and
decrypts on the way out, so model attributes keep working with plaintext.
"""
import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings

_HKDF_INFO = b"acp-pin-encryption-v1"


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    configured = settings.pin_encryption_key
    if configured:
        # Must be a urlsafe-base64-encoded 32-byte Fernet key.
        return Fernet(configured.encode() if isinstance(configured, str) else configured)
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO
    ).derive(settings.secret_key.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str | None:
    """Decrypt a stored token; returns None if it cannot be decrypted."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


class EncryptedString(TypeDecorator):
    """A string column whose value is transparently encrypted at rest."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_secret(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return decrypt_secret(value)
