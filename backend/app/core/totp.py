"""TOTP (RFC 6238) helpers for multi-factor authentication."""
import pyotp

from app.core.config import get_settings


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    """otpauth:// URI for authenticator apps (render as a QR on the client)."""
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=get_settings().app_name)


def verify_code(secret: str | None, code: str | None) -> bool:
    if not secret or not code:
        return False
    # Allow a +/-1 step window for clock skew.
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
