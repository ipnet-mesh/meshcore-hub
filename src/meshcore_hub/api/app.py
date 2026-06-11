"""FastAPI application for MeshCore Hub API."""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
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

    # Initialize Redis cache
    redis_enabled = getattr(app.state, "redis_enabled", False)
    if redis_enabled:
        from meshcore_hub.common.redis import RedisCacheBackend

        redis_cache = RedisCacheBackend(
            host=getattr(app.state, "redis_host", "localhost"),
            port=getattr(app.state, "redis_port", 6379),
            db=getattr(app.state, "redis_db", 0),
            password=getattr(app.state, "redis_password", None),
            key_prefix=getattr(app.state, "redis_key_prefix", "hub"),
        )
        app.state.redis_cache = redis_cache
        logger.info("Redis cache enabled")
    else:
        from meshcore_hub.common.redis import NullCache

        app.state.redis_cache = NullCache()
        logger.info("Redis cache disabled")

    yield

    # Cleanup
    _cache = getattr(app.state, "redis_cache", None)
    if _cache is not None and hasattr(_cache, "close"):
        _cache.close()
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
    mqtt_username: str | None = None,
    mqtt_password: str | None = None,
    mqtt_prefix: str = "meshcore",
    mqtt_tls: bool = False,
    mqtt_transport: str = "websockets",
    mqtt_ws_path: str = "/",
    cors_origins: list[str] | None = None,
    metrics_enabled: bool = True,
    metrics_cache_ttl: int = 60,
    redis_enabled: bool = False,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: str | None = None,
    redis_key_prefix: str = "hub",
    redis_cache_ttl: int = 30,
    redis_cache_ttl_dashboard: int = 30,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        database_url: Database connection URL
        read_key: Read-only API key
        admin_key: Admin API key
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix
        mqtt_tls: Enable TLS/SSL for MQTT connection
        mqtt_transport: MQTT transport protocol (tcp or websockets)
        mqtt_ws_path: WebSocket path (used when transport=websockets)
        cors_origins: Allowed CORS origins
        metrics_enabled: Enable Prometheus metrics endpoint at /metrics
        metrics_cache_ttl: Seconds to cache metrics output
        redis_enabled: Enable Redis API response caching
        redis_host: Redis server host
        redis_port: Redis server port
        redis_db: Redis database number
        redis_password: Redis password (optional)
        redis_key_prefix: Prefix for all cache keys
        redis_cache_ttl: Default cache TTL in seconds
        redis_cache_ttl_dashboard: Cache TTL for dashboard endpoints

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
    app.state.mqtt_username = mqtt_username
    app.state.mqtt_password = mqtt_password
    app.state.mqtt_prefix = mqtt_prefix
    app.state.mqtt_tls = mqtt_tls
    app.state.mqtt_transport = mqtt_transport
    app.state.mqtt_ws_path = mqtt_ws_path
    app.state.metrics_cache_ttl = metrics_cache_ttl
    app.state.redis_enabled = redis_enabled
    app.state.redis_host = redis_host
    app.state.redis_port = redis_port
    app.state.redis_db = redis_db
    app.state.redis_password = redis_password
    app.state.redis_key_prefix = redis_key_prefix
    app.state.redis_cache_ttl = redis_cache_ttl
    app.state.redis_cache_ttl_dashboard = redis_cache_ttl_dashboard

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

    @app.middleware("http")
    async def cache_header_middleware(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        cache_status = getattr(request.state, "cache_status", None)
        if cache_status is not None:
            response.headers["X-Cache"] = cache_status
        return response

    # Include routers
    from meshcore_hub.api.routes import api_router

    app.include_router(api_router, prefix="/api/v1")

    # Include Prometheus metrics endpoint
    if metrics_enabled:
        from meshcore_hub.api.metrics import router as metrics_router

        app.include_router(metrics_router)

    # Health check endpoints
    @app.get("/health", tags=["Health"])
    def health() -> dict:
        """Basic health check."""
        return {"status": "healthy", "version": __version__}

    @app.get("/health/ready", tags=["Health"])
    def health_ready() -> dict:
        """Readiness check including database and optional Redis."""
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                session.execute(text("SELECT 1"))
            result: dict[str, str] = {"status": "ready", "database": "connected"}
        except Exception as e:
            result = {"status": "not_ready", "database": str(e)}

        redis_cache = getattr(app.state, "redis_cache", None)
        redis_enabled = getattr(app.state, "redis_enabled", False)
        if redis_enabled and redis_cache is not None:
            if redis_cache.ping():
                result["redis"] = "connected"
            else:
                result["redis"] = "unreachable"

        return result

    return app


def create_app_from_env() -> FastAPI:
    """Build the application purely from environment configuration.

    This factory is used when running multiple uvicorn workers: each forked
    worker re-imports and calls it with no arguments, so all configuration
    must come from the environment (CLI flags do not propagate to workers).
    It mirrors the resolution the ``api`` CLI command performs for its
    single-process path, drawing structured config from ``APISettings`` plus
    the few env vars the CLI handles directly (CORS / metrics).
    """
    import os

    from meshcore_hub.common.config import get_api_settings

    settings = get_api_settings()

    cors_env = os.environ.get("CORS_ORIGINS")
    cors_origins = [o.strip() for o in cors_env.split(",")] if cors_env else None

    def _env_bool(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")

    metrics_enabled = _env_bool("METRICS_ENABLED", True)
    metrics_cache_ttl = int(os.environ.get("METRICS_CACHE_TTL", "60"))

    # mqtt_transport is an enum on the settings object; create_app wants a str.
    mqtt_transport = getattr(settings.mqtt_transport, "value", settings.mqtt_transport)

    return create_app(
        database_url=settings.effective_database_url,
        read_key=settings.api_read_key,
        admin_key=settings.api_admin_key,
        mqtt_host=settings.mqtt_host,
        mqtt_port=settings.mqtt_port,
        mqtt_username=settings.mqtt_username,
        mqtt_password=settings.mqtt_password,
        mqtt_prefix=settings.mqtt_prefix,
        mqtt_tls=settings.mqtt_tls,
        mqtt_transport=mqtt_transport,
        mqtt_ws_path=settings.mqtt_ws_path,
        cors_origins=cors_origins,
        metrics_enabled=metrics_enabled,
        metrics_cache_ttl=metrics_cache_ttl,
        redis_enabled=settings.redis_enabled,
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
        redis_db=settings.redis_db,
        redis_password=settings.redis_password,
        redis_key_prefix=settings.redis_key_prefix,
        redis_cache_ttl=settings.redis_cache_ttl,
        redis_cache_ttl_dashboard=settings.redis_cache_ttl_dashboard,
    )
