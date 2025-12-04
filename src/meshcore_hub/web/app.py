"""FastAPI application for MeshCore Hub Web Dashboard."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meshcore_hub import __version__
from meshcore_hub.common.schemas import RadioConfig

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
    network_welcome_text: str | None = None,
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

    # Store configuration in app state (use args if provided, else settings)
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
    app.state.network_welcome_text = (
        network_welcome_text or settings.network_welcome_text
    )

    # Set up templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

    return {
        "network_name": request.app.state.network_name,
        "network_city": request.app.state.network_city,
        "network_country": request.app.state.network_country,
        "network_radio_config": radio_config,
        "network_contact_email": request.app.state.network_contact_email,
        "network_contact_discord": request.app.state.network_contact_discord,
        "network_contact_github": request.app.state.network_contact_github,
        "network_welcome_text": request.app.state.network_welcome_text,
        "version": __version__,
    }
