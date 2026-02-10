"""FastAPI application for MeshCore Hub Web Dashboard (SPA)."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from meshcore_hub import __version__
from meshcore_hub.common.schemas import RadioConfig
from meshcore_hub.web.pages import PageLoader

logger = logging.getLogger(__name__)

# Directory paths
PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


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


def _build_config_json(app: FastAPI, request: Request) -> str:
    """Build the JSON config object to embed in the SPA shell.

    Args:
        app: The FastAPI application instance.
        request: The current HTTP request.

    Returns:
        JSON string with app configuration.
    """
    # Parse radio config
    radio_config = RadioConfig.from_config_string(app.state.network_radio_config)
    radio_config_dict = None
    if radio_config:
        radio_config_dict = {
            "frequency": radio_config.frequency,
            "bandwidth": radio_config.bandwidth,
            "spreading_factor": radio_config.spreading_factor,
            "coding_rate": radio_config.coding_rate,
        }

    # Get custom pages for navigation
    page_loader = app.state.page_loader
    custom_pages = [
        {
            "slug": p.slug,
            "title": p.title,
            "url": p.url,
            "menu_order": p.menu_order,
        }
        for p in page_loader.get_menu_pages()
    ]

    config = {
        "network_name": app.state.network_name,
        "network_city": app.state.network_city,
        "network_country": app.state.network_country,
        "network_radio_config": radio_config_dict,
        "network_contact_email": app.state.network_contact_email,
        "network_contact_discord": app.state.network_contact_discord,
        "network_contact_github": app.state.network_contact_github,
        "network_contact_youtube": app.state.network_contact_youtube,
        "network_welcome_text": app.state.network_welcome_text,
        "admin_enabled": app.state.admin_enabled,
        "custom_pages": custom_pages,
        "logo_url": app.state.logo_url,
        "version": __version__,
        "timezone": app.state.timezone_abbr,
        "timezone_iana": app.state.timezone,
        "is_authenticated": bool(request.headers.get("X-Forwarded-User")),
    }

    return json.dumps(config)


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

    # Set up templates (for SPA shell only)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.trim_blocks = True
    templates.env.lstrip_blocks = True
    app.state.templates = templates

    # Compute timezone
    app.state.timezone = settings.tz
    try:
        tz = ZoneInfo(settings.tz)
        app.state.timezone_abbr = datetime.now(tz).strftime("%Z")
    except Exception:
        app.state.timezone_abbr = "UTC"

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

    # --- API Proxy ---
    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        tags=["API Proxy"],
    )
    async def api_proxy(request: Request, path: str) -> Response:
        """Proxy API requests to the backend API server."""
        client: httpx.AsyncClient = request.app.state.http_client
        url = f"/api/{path}"

        # Forward query parameters
        params = dict(request.query_params)

        # Forward body for write methods
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

        # Forward content-type header
        headers: dict[str, str] = {}
        if "content-type" in request.headers:
            headers["content-type"] = request.headers["content-type"]

        # Forward auth proxy headers for admin operations
        for h in ("x-forwarded-user", "x-forwarded-email", "x-forwarded-groups"):
            if h in request.headers:
                headers[h] = request.headers[h]

        try:
            response = await client.request(
                method=request.method,
                url=url,
                params=params,
                content=body,
                headers=headers,
            )

            # Filter response headers (remove hop-by-hop headers)
            resp_headers: dict[str, str] = {}
            for k, v in response.headers.items():
                if k.lower() not in (
                    "transfer-encoding",
                    "connection",
                    "keep-alive",
                    "content-encoding",
                ):
                    resp_headers[k] = v

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=resp_headers,
            )
        except httpx.ConnectError:
            return JSONResponse(
                {"detail": "API server unavailable"},
                status_code=502,
            )
        except Exception as e:
            logger.error(f"API proxy error: {e}")
            return JSONResponse(
                {"detail": "API proxy error"},
                status_code=502,
            )

    # --- Map Data Endpoint (server-side aggregation) ---
    @app.get("/map/data", tags=["Map"])
    async def map_data(request: Request) -> JSONResponse:
        """Return node location data as JSON for the map."""
        nodes_with_location: list[dict[str, Any]] = []
        members_list: list[dict[str, Any]] = []
        members_by_id: dict[str, dict[str, Any]] = {}
        error: str | None = None
        total_nodes = 0
        nodes_with_coords = 0

        try:
            # Fetch all members to build lookup by member_id
            members_response = await request.app.state.http_client.get(
                "/api/v1/members", params={"limit": 500}
            )
            if members_response.status_code == 200:
                members_data = members_response.json()
                for member in members_data.get("items", []):
                    member_info = {
                        "member_id": member.get("member_id"),
                        "name": member.get("name"),
                        "callsign": member.get("callsign"),
                    }
                    members_list.append(member_info)
                    if member.get("member_id"):
                        members_by_id[member["member_id"]] = member_info

            # Fetch all nodes from API
            response = await request.app.state.http_client.get(
                "/api/v1/nodes", params={"limit": 500}
            )
            if response.status_code == 200:
                data = response.json()
                nodes = data.get("items", [])
                total_nodes = len(nodes)

                for node in nodes:
                    tags = node.get("tags", [])
                    tag_lat = None
                    tag_lon = None
                    friendly_name = None
                    role = None
                    node_member_id = None

                    for tag in tags:
                        key = tag.get("key")
                        if key == "lat":
                            try:
                                tag_lat = float(tag.get("value"))
                            except (ValueError, TypeError):
                                pass
                        elif key == "lon":
                            try:
                                tag_lon = float(tag.get("value"))
                            except (ValueError, TypeError):
                                pass
                        elif key == "friendly_name":
                            friendly_name = tag.get("value")
                        elif key == "role":
                            role = tag.get("value")
                        elif key == "member_id":
                            node_member_id = tag.get("value")

                    lat = tag_lat if tag_lat is not None else node.get("lat")
                    lon = tag_lon if tag_lon is not None else node.get("lon")

                    if lat is None or lon is None:
                        continue
                    if lat == 0.0 and lon == 0.0:
                        continue

                    nodes_with_coords += 1
                    display_name = (
                        friendly_name
                        or node.get("name")
                        or node.get("public_key", "")[:12]
                    )
                    public_key = node.get("public_key")
                    owner = (
                        members_by_id.get(node_member_id) if node_member_id else None
                    )

                    nodes_with_location.append(
                        {
                            "public_key": public_key,
                            "name": display_name,
                            "adv_type": node.get("adv_type"),
                            "lat": lat,
                            "lon": lon,
                            "last_seen": node.get("last_seen"),
                            "role": role,
                            "is_infra": role == "infra",
                            "member_id": node_member_id,
                            "owner": owner,
                        }
                    )
            else:
                error = f"API returned status {response.status_code}"

        except Exception as e:
            error = str(e)
            logger.warning(f"Failed to fetch nodes for map: {e}")

        infra_nodes = [n for n in nodes_with_location if n.get("is_infra")]
        infra_count = len(infra_nodes)

        center_lat = 0.0
        center_lon = 0.0
        if nodes_with_location:
            center_lat = sum(n["lat"] for n in nodes_with_location) / len(
                nodes_with_location
            )
            center_lon = sum(n["lon"] for n in nodes_with_location) / len(
                nodes_with_location
            )

        infra_center: dict[str, float] | None = None
        if infra_nodes:
            infra_center = {
                "lat": sum(n["lat"] for n in infra_nodes) / len(infra_nodes),
                "lon": sum(n["lon"] for n in infra_nodes) / len(infra_nodes),
            }

        return JSONResponse(
            {
                "nodes": nodes_with_location,
                "members": members_list,
                "center": {"lat": center_lat, "lon": center_lon},
                "infra_center": infra_center,
                "debug": {
                    "total_nodes": total_nodes,
                    "nodes_with_coords": nodes_with_coords,
                    "infra_nodes": infra_count,
                    "error": error,
                },
            }
        )

    # --- Custom Pages API ---
    @app.get("/spa/pages/{slug}", tags=["SPA"])
    async def get_custom_page(request: Request, slug: str) -> JSONResponse:
        """Get a custom page by slug."""
        page_loader = request.app.state.page_loader
        page = page_loader.get_page(slug)
        if not page:
            return JSONResponse({"detail": "Page not found"}, status_code=404)
        return JSONResponse(
            {
                "slug": page.slug,
                "title": page.title,
                "content_html": page.content_html,
            }
        )

    # --- Health Endpoints ---
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

    # --- SEO Endpoints ---
    def _get_https_base_url(request: Request) -> str:
        """Get base URL, ensuring HTTPS is used for public-facing URLs."""
        base_url = str(request.base_url).rstrip("/")
        if base_url.startswith("http://"):
            base_url = "https://" + base_url[7:]
        return base_url

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots_txt(request: Request) -> str:
        """Serve robots.txt."""
        base_url = _get_https_base_url(request)
        return f"User-agent: *\nDisallow:\n\nSitemap: {base_url}/sitemap.xml\n"

    @app.get("/sitemap.xml")
    async def sitemap_xml(request: Request) -> Response:
        """Generate dynamic sitemap including all node pages."""
        base_url = _get_https_base_url(request)

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

        try:
            response = await request.app.state.http_client.get(
                "/api/v1/nodes", params={"limit": 500, "role": "infra"}
            )
            if response.status_code == 200:
                nodes = response.json().get("items", [])
                for node in nodes:
                    public_key = node.get("public_key")
                    if public_key:
                        urls.append(
                            f"  <url>\n"
                            f"    <loc>{base_url}/nodes/{public_key[:8]}</loc>\n"
                            f"    <changefreq>daily</changefreq>\n"
                            f"    <priority>0.5</priority>\n"
                            f"  </url>"
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch nodes for sitemap: {e}")

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

    # --- SPA Catch-All (MUST be last) ---
    @app.api_route("/{path:path}", methods=["GET"], tags=["SPA"])
    async def spa_catchall(request: Request, path: str = "") -> HTMLResponse:
        """Serve the SPA shell for all non-API routes."""
        templates_inst: Jinja2Templates = request.app.state.templates
        page_loader = request.app.state.page_loader
        custom_pages = page_loader.get_menu_pages()

        config_json = _build_config_json(request.app, request)

        return templates_inst.TemplateResponse(
            "spa.html",
            {
                "request": request,
                "network_name": request.app.state.network_name,
                "network_city": request.app.state.network_city,
                "network_country": request.app.state.network_country,
                "network_contact_email": request.app.state.network_contact_email,
                "network_contact_discord": request.app.state.network_contact_discord,
                "network_contact_github": request.app.state.network_contact_github,
                "network_contact_youtube": request.app.state.network_contact_youtube,
                "network_welcome_text": request.app.state.network_welcome_text,
                "admin_enabled": request.app.state.admin_enabled,
                "custom_pages": custom_pages,
                "logo_url": request.app.state.logo_url,
                "version": __version__,
                "config_json": config_json,
            },
        )

    return app
