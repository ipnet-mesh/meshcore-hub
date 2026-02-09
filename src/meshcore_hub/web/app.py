"""FastAPI application for MeshCore Hub Web Dashboard."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from meshcore_hub import __version__
from meshcore_hub.common.schemas import RadioConfig
from meshcore_hub.web.pages import PageLoader

logger = logging.getLogger(__name__)

# Directory paths
PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def _create_timezone_filters(tz_name: str) -> dict:
    """Create Jinja2 filters for timezone-aware date formatting.

    Args:
        tz_name: IANA timezone name (e.g., "America/New_York", "Europe/London")

    Returns:
        Dict of filter name -> filter function
    """
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"Invalid timezone '{tz_name}', falling back to UTC")
        tz = ZoneInfo("UTC")

    def format_datetime(
        value: str | datetime | None,
        fmt: str = "%Y-%m-%d %H:%M:%S %Z",
    ) -> str:
        """Format a UTC datetime string or object to the configured timezone.

        Args:
            value: ISO 8601 UTC datetime string or datetime object
            fmt: strftime format string

        Returns:
            Formatted datetime string in configured timezone
        """
        if value is None:
            return "-"

        try:
            if isinstance(value, str):
                # Parse ISO 8601 string (assume UTC if no timezone)
                value = value.replace("Z", "+00:00")
                if "+" not in value and "-" not in value[10:]:
                    # No timezone info, assume UTC
                    dt = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("UTC"))
                else:
                    dt = datetime.fromisoformat(value)
            else:
                dt = value
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))

            # Convert to target timezone
            local_dt = dt.astimezone(tz)
            return local_dt.strftime(fmt)
        except Exception:
            # Fallback to original value if parsing fails
            return str(value)[:19].replace("T", " ") if value else "-"

    def format_time(value: str | datetime | None, fmt: str = "%H:%M:%S %Z") -> str:
        """Format just the time portion in the configured timezone."""
        return format_datetime(value, fmt)

    def format_date(value: str | datetime | None, fmt: str = "%Y-%m-%d") -> str:
        """Format just the date portion in the configured timezone."""
        return format_datetime(value, fmt)

    return {
        "localtime": format_datetime,
        "localtime_short": lambda v: format_datetime(v, "%Y-%m-%d %H:%M %Z"),
        "localdate": format_date,
        "localtimeonly": format_time,
        "localtimeonly_short": lambda v: format_time(v, "%H:%M %Z"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Create HTTP client for API calls
    api_url = getattr(app.state, "api_url", "http://localhost:8000")
    api_key = getattr(app.state, "api_key", None)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    app.state.http_client = httpx.AsyncClient(
        base_url=api_url,
        headers=headers,
        timeout=30.0,
    )

    logger.info(f"Web dashboard started, API URL: {api_url}")

    yield

    # Cleanup
    await app.state.http_client.aclose()
    logger.info("Web dashboard stopped")


def create_app(
    api_url: str | None = None,
    api_key: str | None = None,
    admin_enabled: bool | None = None,
    network_name: str | None = None,
    network_city: str | None = None,
    network_country: str | None = None,
    network_radio_config: str | None = None,
    network_contact_email: str | None = None,
    network_contact_discord: str | None = None,
    network_contact_github: str | None = None,
    network_contact_youtube: str | None = None,
    network_welcome_text: str | None = None,
) -> FastAPI:
    """Create and configure the web dashboard application.

    When called without arguments (e.g., in reload mode), settings are loaded
    from environment variables via the WebSettings class.

    Args:
        api_url: Base URL of the MeshCore Hub API
        api_key: API key for authentication
        admin_enabled: Enable admin interface at /a/
        network_name: Display name for the network
        network_city: City where the network is located
        network_country: Country where the network is located
        network_radio_config: Radio configuration description
        network_contact_email: Contact email address
        network_contact_discord: Discord invite/server info
        network_contact_github: GitHub repository URL
        network_contact_youtube: YouTube channel URL
        network_welcome_text: Welcome text for homepage

    Returns:
        Configured FastAPI application
    """
    # Load settings from environment if not provided
    from meshcore_hub.common.config import get_web_settings

    settings = get_web_settings()

    app = FastAPI(
        title="MeshCore Hub Dashboard",
        description="Web dashboard for MeshCore network visualization",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,  # Disable docs for web app
        redoc_url=None,
    )

    # Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) for HTTPS detection
    # This ensures url_for() generates correct HTTPS URLs behind a reverse proxy
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # Store configuration in app state (use args if provided, else settings)
    app.state.api_url = api_url or settings.api_base_url
    app.state.api_key = api_key or settings.api_key
    app.state.admin_enabled = (
        admin_enabled if admin_enabled is not None else settings.web_admin_enabled
    )
    app.state.network_name = network_name or settings.network_name
    app.state.network_city = network_city or settings.network_city
    app.state.network_country = network_country or settings.network_country
    app.state.network_radio_config = (
        network_radio_config or settings.network_radio_config
    )
    app.state.network_contact_email = (
        network_contact_email or settings.network_contact_email
    )
    app.state.network_contact_discord = (
        network_contact_discord or settings.network_contact_discord
    )
    app.state.network_contact_github = (
        network_contact_github or settings.network_contact_github
    )
    app.state.network_contact_youtube = (
        network_contact_youtube or settings.network_contact_youtube
    )
    app.state.network_welcome_text = (
        network_welcome_text or settings.network_welcome_text
    )

    # Set up templates with whitespace control
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.trim_blocks = True  # Remove first newline after block tags
    templates.env.lstrip_blocks = True  # Remove leading whitespace before block tags

    # Register timezone-aware date formatting filters
    app.state.timezone = settings.tz
    tz_filters = _create_timezone_filters(settings.tz)
    for name, func in tz_filters.items():
        templates.env.filters[name] = func

    app.state.templates = templates

    # Initialize page loader for custom markdown pages
    page_loader = PageLoader(settings.effective_pages_home)
    page_loader.load_pages()
    app.state.page_loader = page_loader

    # Check for custom logo and store media path
    media_home = Path(settings.effective_media_home)
    custom_logo_path = media_home / "images" / "logo.svg"
    if custom_logo_path.exists():
        app.state.logo_url = "/media/images/logo.svg"
        logger.info(f"Using custom logo from {custom_logo_path}")
    else:
        app.state.logo_url = "/static/img/logo.svg"

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Mount custom media files if directory exists
    if media_home.exists() and media_home.is_dir():
        app.mount("/media", StaticFiles(directory=str(media_home)), name="media")

    # Include routers
    from meshcore_hub.web.routes import web_router

    app.include_router(web_router)

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        """Basic health check."""
        return {"status": "healthy", "version": __version__}

    @app.get("/health/ready", tags=["Health"])
    async def health_ready(request: Request) -> dict:
        """Readiness check including API connectivity."""
        try:
            response = await request.app.state.http_client.get("/health")
            if response.status_code == 200:
                return {"status": "ready", "api": "connected"}
            return {"status": "not_ready", "api": f"status {response.status_code}"}
        except Exception as e:
            return {"status": "not_ready", "api": str(e)}

    def _get_https_base_url(request: Request) -> str:
        """Get base URL, ensuring HTTPS is used for public-facing URLs."""
        base_url = str(request.base_url).rstrip("/")
        # Ensure HTTPS for sitemaps and robots.txt (SEO requires canonical URLs)
        if base_url.startswith("http://"):
            base_url = "https://" + base_url[7:]
        return base_url

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots_txt(request: Request) -> str:
        """Serve robots.txt to control search engine crawling."""
        base_url = _get_https_base_url(request)
        return f"User-agent: *\nDisallow:\n\nSitemap: {base_url}/sitemap.xml\n"

    @app.get("/sitemap.xml")
    async def sitemap_xml(request: Request) -> Response:
        """Generate dynamic sitemap including all node pages."""
        base_url = _get_https_base_url(request)

        # Static pages
        static_pages = [
            ("", "daily", "1.0"),
            ("/dashboard", "hourly", "0.9"),
            ("/nodes", "hourly", "0.9"),
            ("/advertisements", "hourly", "0.8"),
            ("/messages", "hourly", "0.8"),
            ("/map", "daily", "0.7"),
            ("/members", "weekly", "0.6"),
        ]

        urls = []
        for path, changefreq, priority in static_pages:
            urls.append(
                f"  <url>\n"
                f"    <loc>{base_url}{path}</loc>\n"
                f"    <changefreq>{changefreq}</changefreq>\n"
                f"    <priority>{priority}</priority>\n"
                f"  </url>"
            )

        # Fetch infrastructure nodes for dynamic pages
        try:
            response = await request.app.state.http_client.get(
                "/api/v1/nodes", params={"limit": 500, "role": "infra"}
            )
            if response.status_code == 200:
                nodes = response.json().get("items", [])
                for node in nodes:
                    public_key = node.get("public_key")
                    if public_key:
                        # Use 8-char prefix (route handles redirect to full key)
                        urls.append(
                            f"  <url>\n"
                            f"    <loc>{base_url}/nodes/{public_key[:8]}</loc>\n"
                            f"    <changefreq>daily</changefreq>\n"
                            f"    <priority>0.5</priority>\n"
                            f"  </url>"
                        )
            else:
                logger.warning(
                    f"Failed to fetch nodes for sitemap: {response.status_code}"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch nodes for sitemap: {e}")

        # Add custom pages to sitemap
        page_loader = request.app.state.page_loader
        for page in page_loader.get_menu_pages():
            urls.append(
                f"  <url>\n"
                f"    <loc>{base_url}{page.url}</loc>\n"
                f"    <changefreq>weekly</changefreq>\n"
                f"    <priority>0.6</priority>\n"
                f"  </url>"
            )

        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls)
            + "\n</urlset>"
        )

        return Response(content=xml, media_type="application/xml")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> HTMLResponse:
        """Handle HTTP exceptions with custom error pages."""
        if exc.status_code == 404:
            context = get_network_context(request)
            context["request"] = request
            context["detail"] = exc.detail if exc.detail != "Not Found" else None
            return templates.TemplateResponse(
                "errors/404.html", context, status_code=404
            )
        # For other errors, return a simple response
        return HTMLResponse(
            content=f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>",
            status_code=exc.status_code,
        )

    return app


def get_templates(request: Request) -> Jinja2Templates:
    """Get templates from app state."""
    templates: Jinja2Templates = request.app.state.templates
    return templates


def get_network_context(request: Request) -> dict:
    """Get network configuration context for templates."""
    # Parse radio config from comma-delimited string
    radio_config = RadioConfig.from_config_string(
        request.app.state.network_radio_config
    )

    # Get custom pages for navigation
    page_loader = request.app.state.page_loader
    custom_pages = page_loader.get_menu_pages()

    return {
        "network_name": request.app.state.network_name,
        "network_city": request.app.state.network_city,
        "network_country": request.app.state.network_country,
        "network_radio_config": radio_config,
        "network_contact_email": request.app.state.network_contact_email,
        "network_contact_discord": request.app.state.network_contact_discord,
        "network_contact_github": request.app.state.network_contact_github,
        "network_contact_youtube": request.app.state.network_contact_youtube,
        "network_welcome_text": request.app.state.network_welcome_text,
        "admin_enabled": request.app.state.admin_enabled,
        "custom_pages": custom_pages,
        "logo_url": request.app.state.logo_url,
        "version": __version__,
        "timezone": request.app.state.timezone,
    }
