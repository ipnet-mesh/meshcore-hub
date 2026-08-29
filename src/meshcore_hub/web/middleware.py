"""HTTP caching and security header middleware for the web component."""

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Middleware to set appropriate Cache-Control headers based on resource type."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
        """
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process the request and add appropriate caching headers.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The response with cache headers added.
        """
        response: Response = await call_next(request)

        # Skip if Cache-Control already set (explicit override)
        if "cache-control" in response.headers:
            return response

        path = request.url.path
        query_params = request.url.query

        # Health endpoints - never cache
        if path.startswith("/health"):
            response.headers["cache-control"] = "no-cache, no-store, must-revalidate"

        # Static files with version parameter - long-term cache
        elif path.startswith("/static/") and "v=" in query_params:
            response.headers["cache-control"] = "public, max-age=31536000, immutable"

        # Static dist/ files use content-hashed filenames — immutable
        elif path.startswith("/static/dist/"):
            response.headers["cache-control"] = "public, max-age=31536000, immutable"

        # Vendored font files - stable names referenced from CSS - long-term cache
        elif path.startswith("/static/vendor/fonts/"):
            response.headers["cache-control"] = "public, max-age=31536000, immutable"

        # Static files without version - short cache as fallback
        elif path.startswith("/static/"):
            response.headers["cache-control"] = "public, max-age=3600"

        # Media files with version parameter - long-term cache
        elif path.startswith("/media/") and "v=" in query_params:
            response.headers["cache-control"] = "public, max-age=31536000, immutable"

        # Media files without version - short cache (user may update)
        elif path.startswith("/media/"):
            response.headers["cache-control"] = "public, max-age=3600"

        # Map data - short cache (5 minutes)
        elif path == "/map/data":
            response.headers["cache-control"] = "public, max-age=300"

        # Custom pages - moderate cache (1 hour)
        elif path.startswith("/spa/pages/"):
            response.headers["cache-control"] = "public, max-age=3600"

        # SEO files - moderate cache (1 hour)
        elif path in ("/robots.txt", "/sitemap.xml"):
            response.headers["cache-control"] = "public, max-age=3600"

        # API proxy - don't add headers (pass through backend)
        elif path.startswith("/api/"):
            pass

        # SPA shell HTML (catch-all for client-side routes) - no cache
        elif response.headers.get("content-type", "").startswith("text/html"):
            response.headers["cache-control"] = "no-cache, public"

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware adding security headers and a nonce-based CSP to responses.

    Generates a per-request CSP nonce, exposes it to handlers via
    ``request.state.csp_nonce`` (the SPA shell template applies it to its
    inline scripts), and sets standard hardening headers plus a
    Content-Security-Policy on every response.

    Notes on the policy:
      - ``style-src 'unsafe-inline'``: the SPA shell conditionally emits one
        small inline ``<style>`` block; style injection is low-risk.
      - ``img-src ... https:``: custom markdown pages may embed external
        https images; map tiles load from *.tile.openstreetmap.org.
      - ``script-src`` allows only same-origin scripts plus nonce'd inline
        scripts (theme bootstrap + ``window.__APP_CONFIG__``).
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        csp_extra: str | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
            enabled: When False, skip all header setting (kill switch).
            csp_extra: Extra CSP directives appended to the default policy.
        """
        super().__init__(app)
        self.enabled = enabled
        self.csp_extra = csp_extra.strip().rstrip(";") if csp_extra else None

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process the request and add security headers to the response.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The response with security headers added.
        """
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response: Response = await call_next(request)

        if self.enabled:
            csp = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "frame-ancestors 'none'"
            )
            if self.csp_extra:
                csp = f"{csp}; {self.csp_extra}"
            response.headers["content-security-policy"] = csp
            response.headers["x-content-type-options"] = "nosniff"
            response.headers["x-frame-options"] = "DENY"
            response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
            response.headers["permissions-policy"] = (
                "camera=(), microphone=(), geolocation=()"
            )

        return response
