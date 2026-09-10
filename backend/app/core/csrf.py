"""Double-submit CSRF protection for cookie-authenticated requests.

Only requests that authenticate through the auth cookies are subject to CSRF:
an unsafe method carrying an auth cookie but no ``Authorization`` header must
also send the CSRF token both as the ``acp_csrf`` cookie and the ``X-CSRF-Token``
header, and the two must match. Bearer-authenticated (programmatic) requests are
not ambient-authority requests and are left untouched.
"""
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The auth bootstrap endpoints establish/rotate/clear the session itself. They
# are authenticated by credentials or the refresh cookie (not ambient app
# authority) and are already protected cross-site by SameSite=Lax, so requiring
# a CSRF token there only breaks legitimate (re-)login while adding no defense.
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    }
)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.method in _UNSAFE_METHODS
            and request.url.path not in _EXEMPT_PATHS
            and self._is_cookie_authenticated(request)
        ):
            header_token = request.headers.get(CSRF_HEADER)
            cookie_token = request.cookies.get(CSRF_COOKIE)
            if not header_token or not cookie_token or not secrets.compare_digest(header_token, cookie_token):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"},
                )
        return await call_next(request)

    @staticmethod
    def _is_cookie_authenticated(request: Request) -> bool:
        if "authorization" in request.headers:
            return False  # bearer clients are not cookie/ambient auth
        return bool(request.cookies.get(ACCESS_COOKIE) or request.cookies.get(REFRESH_COOKIE))
