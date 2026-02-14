"""HTTP caching middleware for the web component."""

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
