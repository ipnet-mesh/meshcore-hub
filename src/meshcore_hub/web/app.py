"""FastAPI application for MeshCore Hub Web Dashboard."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meshcore_hub import __version__

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
    api_url: str = "http://localhost:8000",
    api_key: str | None = None,
    network_name: str = "MeshCore Network",
    network_city: str | None = None,
    network_country: str | None = None,
    network_location: tuple[float, float] | None = None,
    network_radio_config: str | None = None,
    network_contact_email: str | None = None,
    network_contact_discord: str | None = None,
    members_file: str | None = None,
) -> FastAPI:
    """Create and configure the web dashboard application.

    Args:
        api_url: Base URL of the MeshCore Hub API
        api_key: API key for authentication
        network_name: Display name for the network
        network_city: City where the network is located
        network_country: Country where the network is located
        network_location: (lat, lon) tuple for map centering
        network_radio_config: Radio configuration description
        network_contact_email: Contact email address
        network_contact_discord: Discord invite/server info
        members_file: Path to members JSON file

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="MeshCore Hub Dashboard",
        description="Web dashboard for MeshCore network visualization",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,  # Disable docs for web app
        redoc_url=None,
    )

    # Store configuration in app state
    app.state.api_url = api_url
    app.state.api_key = api_key
    app.state.network_name = network_name
    app.state.network_city = network_city
    app.state.network_country = network_country
    app.state.network_location = network_location or (0.0, 0.0)
    app.state.network_radio_config = network_radio_config
    app.state.network_contact_email = network_contact_email
    app.state.network_contact_discord = network_contact_discord
    app.state.members_file = members_file

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
    return request.app.state.templates


def get_network_context(request: Request) -> dict:
    """Get network configuration context for templates."""
    return {
        "network_name": request.app.state.network_name,
        "network_city": request.app.state.network_city,
        "network_country": request.app.state.network_country,
        "network_location": request.app.state.network_location,
        "network_radio_config": request.app.state.network_radio_config,
        "network_contact_email": request.app.state.network_contact_email,
        "network_contact_discord": request.app.state.network_contact_discord,
        "version": __version__,
    }
