"""FastAPI application for MeshCore Hub API."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from meshcore_hub import __version__
from meshcore_hub.common.database import DatabaseManager

logger = logging.getLogger(__name__)

# Global database manager (set during startup)
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Get the global database manager."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized")
    return _db_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    global _db_manager

    # Get database URL from app state
    database_url = getattr(app.state, "database_url", "sqlite:///./meshcore.db")

    # Initialize database (schema managed by Alembic migrations)
    logger.info(f"Initializing database: {database_url}")
    _db_manager = DatabaseManager(database_url)

    yield

    # Cleanup
    if _db_manager:
        _db_manager.dispose()
        _db_manager = None
    logger.info("Database connection closed")


def create_app(
    database_url: str = "sqlite:///./meshcore.db",
    read_key: str | None = None,
    admin_key: str | None = None,
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    mqtt_prefix: str = "meshcore",
    mqtt_tls: bool = False,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        database_url: Database connection URL
        read_key: Read-only API key
        admin_key: Admin API key
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_prefix: MQTT topic prefix
        mqtt_tls: Enable TLS/SSL for MQTT connection
        cors_origins: Allowed CORS origins

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="MeshCore Hub API",
        description="REST API for querying MeshCore network data and sending commands",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Store configuration in app state
    app.state.database_url = database_url
    app.state.read_key = read_key
    app.state.admin_key = admin_key
    app.state.mqtt_host = mqtt_host
    app.state.mqtt_port = mqtt_port
    app.state.mqtt_prefix = mqtt_prefix
    app.state.mqtt_tls = mqtt_tls

    # Configure CORS
    if cors_origins is None:
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from meshcore_hub.api.routes import api_router

    app.include_router(api_router, prefix="/api/v1")

    # Health check endpoints
    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        """Basic health check."""
        return {"status": "healthy", "version": __version__}

    @app.get("/health/ready", tags=["Health"])
    async def health_ready() -> dict:
        """Readiness check including database."""
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                session.execute(text("SELECT 1"))
            return {"status": "ready", "database": "connected"}
        except Exception as e:
            return {"status": "not_ready", "database": str(e)}

    return app
