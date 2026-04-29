"""FastAPI application for MeshCore Hub Web Dashboard (SPA)."""

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from meshcore_hub import __version__
from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder
from meshcore_hub.common.i18n import load_locale, t
from meshcore_hub.common.schemas import RadioConfig
from meshcore_hub.web.middleware import CacheControlMiddleware
from meshcore_hub.web.oidc import (
    get_session_roles,
    get_session_user,
    init_oidc,
    oauth,
    strip_userinfo,
    validate_discovery,
)
from meshcore_hub.web.pages import PageLoader

logger = logging.getLogger(__name__)

# Directory paths
PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


# Per-endpoint, per-method role access mapping for the API proxy.
# Key: URL path prefix (after /api/), Value: {method -> allowed roles}.
# _OPEN = unconditional access (OIDC on or off, anonymous OK).
# Method not listed = denied. No prefix match = denied.
_OPEN: frozenset[str] = frozenset()


def _build_endpoint_access(
    role_admin: str,
    role_operator: str = "operator",
    role_member: str = "member",
) -> dict[str, dict[str, frozenset[str]]]:
    """Build the per-endpoint access mapping using configured role names.

    Args:
        role_admin: The IdP role name that grants admin access.
        role_operator: The IdP role name that grants operator access.
        role_member: The IdP role name that grants member access.

    Returns:
        Endpoint access mapping dict.
    """
    admin = frozenset({role_admin})
    any_authenticated = frozenset({role_admin, role_operator, role_member})
    operator_admin = frozenset({role_admin, role_operator})
    return {
        "v1/nodes": {
            "GET": _OPEN,
        },
        "v1/nodes/": {
            "GET": _OPEN,
            "POST": admin,
            "PUT": admin,
            "DELETE": admin,
        },
        "v1/members": {
            "GET": _OPEN,
            "POST": admin,
            "PUT": admin,
            "DELETE": admin,
        },
        "v1/messages": {
            "GET": _OPEN,
        },
        "v1/advertisements": {
            "GET": _OPEN,
        },
        "v1/dashboard": {
            "GET": _OPEN,
        },
        "v1/trace-paths": {
            "GET": _OPEN,
        },
        "v1/telemetry": {
            "GET": _OPEN,
        },
        "v1/adoptions": {
            "POST": operator_admin,
            "DELETE": operator_admin,
        },
        "v1/user/profile": {
            "GET": any_authenticated,
            "PUT": any_authenticated,
        },
    }


def check_api_access(
    path: str,
    method: str,
    oidc_enabled: bool,
    user_roles: frozenset[str],
    mapping: dict[str, dict[str, frozenset[str]]],
) -> bool:
    """Check if user has required role for the given API path + method.

    Longest prefix wins. Method must be explicitly listed.
    _OPEN means unconditional access. Specific roles require OIDC on + role match.
    """
    for prefix in sorted(mapping, key=len, reverse=True):
        if path.startswith(prefix):
            required = mapping[prefix].get(method)
            if required is None:
                return False
            if not required:
                return True
            if not oidc_enabled:
                return False
            return bool(user_roles & required)
    return False


def _parse_decoder_key_entries(raw: str | None) -> list[str]:
    """Parse COLLECTOR_CHANNEL_KEYS into key entries."""
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]


def _build_channel_labels() -> dict[str, str]:
    """Build UI channel labels from built-in + configured decoder keys."""
    raw_keys = os.getenv("COLLECTOR_CHANNEL_KEYS")
    include_test = os.getenv("COLLECTOR_INCLUDE_TEST_CHANNEL", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    decoder = LetsMeshPacketDecoder(
        channel_keys=_parse_decoder_key_entries(raw_keys),
    )
    labels = decoder.channel_labels_by_index()
    if not include_test:
        labels.pop(LetsMeshPacketDecoder.TEST_CHANNEL_IDX, None)
    return {str(idx): label for idx, label in sorted(labels.items())}


def _resolve_logo(media_home: Path) -> tuple[str, bool, Path | None]:
    """Resolve logo URL and whether light-mode inversion should be applied.

    Returns:
        tuple of (logo_url, invert_in_light_mode, resolved_path)
    """
    custom_logo_candidates = (
        ("logo-invert.svg", "/media/images/logo-invert.svg", True),
        ("logo.svg", "/media/images/logo.svg", False),
    )
    for filename, url, invert_in_light_mode in custom_logo_candidates:
        path = media_home / "images" / filename
        if path.exists():
            cache_buster = int(path.stat().st_mtime)
            return f"{url}?v={cache_buster}", invert_in_light_mode, path

    # Default packaged logo is monochrome and needs darkening in light mode.
    return "/static/img/logo.svg", True, None


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

    if getattr(app.state, "oidc_enabled", False):
        ok = await validate_discovery()
        if not ok:
            logger.warning(
                "OIDC discovery failed — login will not work until IdP is reachable"
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
            "profile": radio_config.profile,
            "frequency": radio_config.frequency,
            "bandwidth": radio_config.bandwidth,
            "spreading_factor": radio_config.spreading_factor,
            "coding_rate": radio_config.coding_rate,
            "tx_power": radio_config.tx_power,
        }

    # Get feature flags
    features = app.state.features

    # Get custom pages for navigation (empty when pages feature is disabled)
    page_loader = app.state.page_loader
    custom_pages = (
        [
            {
                "slug": p.slug,
                "title": p.title,
                "url": p.url,
                "menu_order": p.menu_order,
            }
            for p in page_loader.get_menu_pages()
        ]
        if features.get("pages", True)
        else []
    )

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
        "features": features,
        "custom_pages": custom_pages,
        "logo_url": app.state.logo_url,
        "version": __version__,
        "timezone": app.state.timezone_abbr,
        "timezone_iana": app.state.timezone,
        "default_theme": app.state.web_theme,
        "locale": app.state.web_locale,
        "datetime_locale": app.state.web_datetime_locale,
        "auto_refresh_seconds": app.state.auto_refresh_seconds,
        "channel_labels": app.state.channel_labels,
        "logo_invert_light": app.state.logo_invert_light,
        "debug": app.state.web_debug,
    }

    role_names = {
        "admin": app.state.oidc_role_admin,
        "operator": app.state.oidc_role_operator,
        "member": app.state.oidc_role_member,
    }

    if getattr(app.state, "oidc_enabled", False):
        user = get_session_user(request)
        roles = get_session_roles(request, app.state.oidc_roles_claim)
        config.update(
            oidc_enabled=True,
            user=user,
            roles=roles,
            role_names=role_names,
        )
    else:
        config.update(
            oidc_enabled=False,
            user=None,
            roles=[],
            role_names=role_names,
        )

    # Escape "</script>" sequences to prevent XSS breakout from the
    # <script> block where this JSON is embedded via |safe in the
    # Jinja2 template.  "<\/" is valid JSON per the spec and parsed
    # correctly by JavaScript's JSON.parse().
    return json.dumps(config).replace("</", "<\\/")


def create_app(
    api_url: str | None = None,
    api_key: str | None = None,
    network_name: str | None = None,
    network_city: str | None = None,
    network_country: str | None = None,
    network_radio_config: str | None = None,
    network_contact_email: str | None = None,
    network_contact_discord: str | None = None,
    network_contact_github: str | None = None,
    network_contact_youtube: str | None = None,
    network_welcome_text: str | None = None,
    features: dict[str, bool] | None = None,
) -> FastAPI:
    """Create and configure the web dashboard application.

    When called without arguments (e.g., in reload mode), settings are loaded
    from environment variables via the WebSettings class.

    Args:
        api_url: Base URL of the MeshCore Hub API
        api_key: API key for authentication
        network_name: Display name for the network
        network_city: City where the network is located
        network_country: Country where the network is located
        network_radio_config: Radio configuration description
        network_contact_email: Contact email address
        network_contact_discord: Discord invite/server info
        network_contact_github: GitHub repository URL
        network_contact_youtube: YouTube channel URL
        network_welcome_text: Welcome text for homepage
        features: Feature flags dict (default: all enabled from settings)

    Returns:
        Configured FastAPI application

    When OIDC is enabled via environment variables (OIDC_ENABLED=true),
    the app adds SessionMiddleware and registers auth routes (/auth/login,
    /auth/callback, /auth/logout, /auth/user). Write methods through the
    API proxy require admin session when OIDC is enabled.
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

    # Add cache control headers based on resource type
    app.add_middleware(CacheControlMiddleware)

    # OIDC / session middleware
    if settings.oidc_enabled:
        app.add_middleware(
            SessionMiddleware,
            secret_key=settings.oidc_session_secret or "insecure-dev-secret",
            session_cookie="meshcore-session",
            max_age=settings.oidc_session_max_age,
            same_site="lax",
            https_only=settings.oidc_cookie_secure,
        )
        init_oidc(
            client_id=settings.oidc_client_id or "",
            client_secret=settings.oidc_client_secret or "",
            discovery_url=settings.oidc_discovery_url or "",
            scopes=settings.oidc_scopes,
        )
        app.state.oidc_enabled = True
        app.state.oidc_client_id = settings.oidc_client_id
        app.state.oidc_redirect_uri = settings.oidc_redirect_uri
        app.state.oidc_post_logout_redirect_uri = settings.oidc_post_logout_redirect_uri
        app.state.oidc_roles_claim = settings.oidc_roles_claim
        app.state.oidc_role_admin = settings.oidc_role_admin
        app.state.oidc_role_operator = settings.oidc_role_operator
        app.state.oidc_role_member = settings.oidc_role_member
    else:
        app.state.oidc_enabled = False
        app.state.oidc_role_admin = settings.oidc_role_admin
        app.state.oidc_role_operator = settings.oidc_role_operator
        app.state.oidc_role_member = settings.oidc_role_member

    app.state.endpoint_access = _build_endpoint_access(
        role_admin=settings.oidc_role_admin,
        role_operator=settings.oidc_role_operator,
        role_member=settings.oidc_role_member,
    )

    # Load i18n translations
    app.state.web_locale = settings.web_locale or "en"
    app.state.web_datetime_locale = settings.web_datetime_locale or "en-US"
    load_locale(app.state.web_locale)

    # Auto-refresh interval
    app.state.auto_refresh_seconds = settings.web_auto_refresh_seconds
    app.state.web_debug = settings.web_debug
    app.state.channel_labels = _build_channel_labels()

    # Store configuration in app state (use args if provided, else settings)
    app.state.web_theme = (
        settings.web_theme if settings.web_theme in ("dark", "light") else "dark"
    )
    app.state.api_url = api_url or settings.api_base_url
    app.state.api_key = api_key or settings.api_key
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

    # Store feature flags with automatic dependencies:
    # - Dashboard requires at least one of nodes/advertisements/messages
    # - Map requires nodes (map displays node locations)
    effective_features = features if features is not None else settings.features
    overrides: dict[str, bool] = {}
    has_dashboard_content = (
        effective_features.get("nodes", True)
        or effective_features.get("advertisements", True)
        or effective_features.get("messages", True)
    )
    if not has_dashboard_content:
        overrides["dashboard"] = False
    if not effective_features.get("nodes", True):
        overrides["map"] = False
    if overrides:
        effective_features = {**effective_features, **overrides}
    app.state.features = effective_features

    # Set up templates (for SPA shell only)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.trim_blocks = True
    templates.env.lstrip_blocks = True
    templates.env.globals["t"] = t
    app.state.templates = templates

    # --- Error handlers ---
    def _is_api_request(request: Request) -> bool:
        return request.url.path.startswith("/api/")

    def _render_error_html(
        request: Request, status_code: int, message: str, detail: str = ""
    ) -> Response:
        tmpl: Jinja2Templates = request.app.state.templates
        return tmpl.TemplateResponse(
            request,
            "error.html",
            {
                "status_code": status_code,
                "message": message,
                "detail": detail,
                "theme": getattr(request.app.state, "web_theme", "dark"),
                "network_name": getattr(
                    request.app.state, "network_name", "MeshCore Hub"
                ),
                "version": __version__,
            },
            status_code=status_code,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        if _is_api_request(request):
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
            )
        message_map = {
            404: "Page not found",
            405: "Method not allowed",
        }
        return _render_error_html(
            request,
            exc.status_code,
            message_map.get(exc.status_code, "Something went wrong"),
            str(exc.detail) if exc.detail else "",
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> Response:
        logger.exception("Unhandled exception on %s: %s", request.url.path, exc)
        if _is_api_request(request):
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=500,
            )
        return _render_error_html(
            request,
            500,
            "Internal server error",
            "",
        )

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
    logo_url, logo_invert_light, logo_path = _resolve_logo(media_home)
    app.state.logo_url = logo_url
    app.state.logo_invert_light = logo_invert_light
    if logo_path is not None:
        logger.info("Using custom logo from %s", logo_path)

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Mount custom media files if directory exists
    if media_home.exists() and media_home.is_dir():
        app.mount("/media", StaticFiles(directory=str(media_home)), name="media")

    # --- API Proxy ---
    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        tags=["API Proxy"],
    )
    async def api_proxy(request: Request, path: str) -> Response:
        """Proxy API requests to the backend API server."""
        oidc_enabled = getattr(request.app.state, "oidc_enabled", False)
        user_roles: frozenset[str] = frozenset()
        if oidc_enabled:
            roles_claim = getattr(request.app.state, "oidc_roles_claim", "roles")
            user_roles = frozenset(get_session_roles(request, roles_claim))
        if not check_api_access(
            path,
            request.method,
            oidc_enabled,
            user_roles,
            request.app.state.endpoint_access,
        ):
            return JSONResponse(
                {"detail": "Access denied", "code": "AUTH_REQUIRED"},
                status_code=403,
            )

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

        # Inject authenticated user identity when OIDC is enabled
        if oidc_enabled:
            user = get_session_user(request)
            if user and user.get("sub"):
                headers["X-User-Id"] = user["sub"]
                if user.get("name"):
                    headers["X-User-Name"] = user["name"]
                roles = get_session_roles(request, roles_claim)
                if roles:
                    headers["X-User-Roles"] = ",".join(roles)

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
        if not request.app.state.features.get("map", True):
            return JSONResponse({"detail": "Map feature is disabled"}, status_code=404)
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
        if not request.app.state.features.get("pages", True):
            return JSONResponse(
                {"detail": "Pages feature is disabled"}, status_code=404
            )
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
        features = request.app.state.features

        # Always disallow message and node detail pages
        disallow_lines = [
            "Disallow: /messages",
            "Disallow: /nodes/",
        ]

        # Add disallow for disabled features
        feature_paths = {
            "dashboard": "/dashboard",
            "nodes": "/nodes",
            "advertisements": "/advertisements",
            "map": "/map",
            "members": "/members",
            "pages": "/pages",
        }
        for feature, path in feature_paths.items():
            if not features.get(feature, True):
                line = f"Disallow: {path}"
                if line not in disallow_lines:
                    disallow_lines.append(line)

        disallow_block = "\n".join(disallow_lines)
        return f"User-agent: *\n{disallow_block}\n\nSitemap: {base_url}/sitemap.xml\n"

    @app.get("/sitemap.xml")
    async def sitemap_xml(request: Request) -> Response:
        """Generate dynamic sitemap."""
        base_url = _get_https_base_url(request)
        features = request.app.state.features

        # Home is always included; other pages depend on feature flags
        all_static_pages = [
            ("", "daily", "1.0", None),
            ("/dashboard", "hourly", "0.9", "dashboard"),
            ("/nodes", "hourly", "0.9", "nodes"),
            ("/advertisements", "hourly", "0.8", "advertisements"),
            ("/map", "daily", "0.7", "map"),
            ("/members", "weekly", "0.6", "members"),
        ]

        static_pages = [
            (path, freq, prio)
            for path, freq, prio, feature in all_static_pages
            if feature is None or features.get(feature, True)
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

        if features.get("pages", True):
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

    # --- Auth Routes (OIDC) ---
    @app.get("/auth/login", tags=["Auth"])
    async def auth_login(request: Request) -> Response:
        """Initiate OIDC login flow."""
        if not request.app.state.oidc_enabled:
            return JSONResponse({"detail": "OIDC not enabled"}, status_code=400)
        next_url = request.query_params.get("next", "/")
        request.session["next"] = next_url
        redirect_uri = getattr(request.app.state, "oidc_redirect_uri", None) or str(
            request.url_for("auth_callback")
        )
        response: Response = await oauth.oidc.authorize_redirect(request, redirect_uri)
        logger.info(
            "OIDC login: authorization URL=%s",
            response.headers.get("location", "unknown"),
        )
        return response

    @app.get("/auth/callback", tags=["Auth"], name="auth_callback")
    async def auth_callback(request: Request) -> Response:
        """Handle OIDC callback and store user in session."""
        if not request.app.state.oidc_enabled:
            return JSONResponse({"detail": "OIDC not enabled"}, status_code=400)
        token = await oauth.oidc.authorize_access_token(request)
        logger.info(
            "OIDC callback: token keys=%s, granted scope=%s",
            list(token.keys()),
            token.get("scope"),
        )

        userinfo = token.get("userinfo") or {}
        logger.info("OIDC callback: ID token userinfo=%s", dict(userinfo))

        if not userinfo.get("name") and not userinfo.get("email"):
            try:
                userinfo = await oauth.oidc.userinfo(token=token)
                logger.info("OIDC callback: /userinfo endpoint=%s", dict(userinfo))
            except Exception:
                logger.exception(
                    "OIDC userinfo fetch failed, using ID token claims only"
                )
        roles_claim = request.app.state.oidc_roles_claim
        session_user = strip_userinfo(userinfo, roles_claim)
        logger.info("OIDC callback: session user=%s", session_user)

        request.session["user"] = session_user
        request.session["id_token"] = token.get("id_token")
        next_url = request.session.pop("next", "/")
        from starlette.responses import RedirectResponse

        return RedirectResponse(url=next_url)

    @app.get("/auth/logout", tags=["Auth"])
    async def auth_logout(request: Request) -> Response:
        """Clear session and redirect to IdP end_session_endpoint."""
        if not request.app.state.oidc_enabled:
            return JSONResponse({"detail": "OIDC not enabled"}, status_code=400)
        from starlette.responses import RedirectResponse

        id_token_hint = request.session.get("id_token")
        client_id = request.app.state.oidc_client_id

        post_logout_uri = request.app.state.oidc_post_logout_redirect_uri
        if not post_logout_uri:
            redirect_uri = getattr(request.app.state, "oidc_redirect_uri", None)
            if redirect_uri:
                base = redirect_uri.rsplit("/auth/callback", 1)[0]
                post_logout_uri = base.rstrip("/") + "/"
            else:
                post_logout_uri = str(request.base_url).rstrip("/")

        logger.info(
            "OIDC logout: client_id=%s, id_token_hint=%s, post_logout_redirect_uri=%s",
            client_id,
            "present" if id_token_hint else "MISSING",
            post_logout_uri,
        )

        try:
            response: Response = await oauth.oidc.logout_redirect(
                request,
                post_logout_redirect_uri=post_logout_uri,
                id_token_hint=id_token_hint,
                client_id=client_id,
            )
        except Exception:
            logger.exception("OIDC logout_redirect failed, redirecting to /")
            response = RedirectResponse(url="/")

        request.session.clear()
        return response

    @app.get("/auth/user", tags=["Auth"])
    async def auth_user(request: Request) -> JSONResponse:
        """Return current user JSON or 401 when not logged in."""
        if not request.app.state.oidc_enabled:
            return JSONResponse({"detail": "OIDC not enabled"}, status_code=400)
        user = get_session_user(request)
        if not user:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        roles = get_session_roles(
            request,
            request.app.state.oidc_roles_claim,
        )
        return JSONResponse({"user": user, "roles": roles})

    # --- SPA Catch-All (MUST be last) ---
    @app.api_route("/{path:path}", methods=["GET"], tags=["SPA"], response_model=None)
    async def spa_catchall(request: Request, path: str = "") -> Response:
        """Serve the SPA shell for all non-API routes."""
        # Admin route protection when OIDC is enabled
        if path.startswith("admin") and (
            path == "admin" or path == "admin/" or path.startswith("admin/")
        ):
            if request.app.state.oidc_enabled:
                user = get_session_user(request)
                if not user:
                    from starlette.responses import RedirectResponse

                    return RedirectResponse(url=f"/auth/login?next=/{path}")
                logger.debug(
                    "Admin route access: path=%s, user=%s",
                    path,
                    user.get("name"),
                )

        templates_inst: Jinja2Templates = request.app.state.templates
        features = request.app.state.features
        page_loader = request.app.state.page_loader
        custom_pages = (
            page_loader.get_menu_pages() if features.get("pages", True) else []
        )

        config_json = _build_config_json(request.app, request)

        return templates_inst.TemplateResponse(
            request,
            "spa.html",
            {
                "network_name": request.app.state.network_name,
                "network_city": request.app.state.network_city,
                "network_country": request.app.state.network_country,
                "network_contact_email": request.app.state.network_contact_email,
                "network_contact_discord": request.app.state.network_contact_discord,
                "network_contact_github": request.app.state.network_contact_github,
                "network_contact_youtube": request.app.state.network_contact_youtube,
                "network_welcome_text": request.app.state.network_welcome_text,
                "oidc_enabled": request.app.state.oidc_enabled,
                "features": features,
                "custom_pages": custom_pages,
                "logo_url": request.app.state.logo_url,
                "logo_invert_light": request.app.state.logo_invert_light,
                "version": __version__,
                "default_theme": request.app.state.web_theme,
                "config_json": config_json,
            },
        )

    return app
