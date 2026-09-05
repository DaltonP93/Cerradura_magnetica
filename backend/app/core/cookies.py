"""HttpOnly auth cookies and the companion CSRF token.

Browser sessions never expose the JWTs to JavaScript: the access and refresh
tokens live in HttpOnly cookies, and a separate, JS-readable CSRF token is sent
back on every unsafe request (double-submit) so a cookie-authenticated request
cannot be forged cross-site. Programmatic clients may still use the
``Authorization: Bearer`` header, which is not subject to CSRF.
"""
import secrets

from fastapi import Response

from app.core.config import get_settings

ACCESS_COOKIE = "acp_access"
REFRESH_COOKIE = "acp_refresh"
CSRF_COOKIE = "acp_csrf"
CSRF_HEADER = "X-CSRF-Token"

# The refresh cookie is only ever needed by the auth endpoints, so scope it
# there to keep it off every other request.
_REFRESH_PATH = "/api/v1/auth"
_ROOT_PATH = "/"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(response: Response, *, access: str, refresh: str, csrf: str) -> None:
    settings = get_settings()
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite.lower()
    domain = settings.cookie_domain
    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 24 * 3600

    response.set_cookie(
        ACCESS_COOKIE, access, max_age=access_max_age, path=_ROOT_PATH,
        httponly=True, secure=secure, samesite=samesite, domain=domain,
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=refresh_max_age, path=_REFRESH_PATH,
        httponly=True, secure=secure, samesite=samesite, domain=domain,
    )
    # The CSRF token mirrors the session lifetime but is deliberately readable
    # by JS so the SPA can echo it back in the CSRF header.
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=refresh_max_age, path=_ROOT_PATH,
        httponly=False, secure=secure, samesite=samesite, domain=domain,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    domain = settings.cookie_domain
    response.delete_cookie(ACCESS_COOKIE, path=_ROOT_PATH, domain=domain)
    response.delete_cookie(REFRESH_COOKIE, path=_REFRESH_PATH, domain=domain)
    response.delete_cookie(CSRF_COOKIE, path=_ROOT_PATH, domain=domain)
