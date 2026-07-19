"""API CLI commands."""

import click


@click.command()
@click.option(
    "--host",
    type=str,
    default="0.0.0.0",
    envvar="API_HOST",
    help="API server host",
)
@click.option(
    "--port",
    type=int,
    default=8000,
    envvar="API_PORT",
    help="API server port",
)
@click.option(
    "--data-home",
    type=str,
    default=None,
    envvar="DATA_HOME",
    help="Base data directory (default: ./data)",
)
@click.option(
    "--database-url",
    type=str,
    default=None,
    envvar="DATABASE_URL",
    help="Database connection URL (default: sqlite:///{data_home}/collector/meshcore.db)",
)
@click.option(
    "--read-key",
    type=str,
    default=None,
    envvar="API_READ_KEY",
    help="Read-only API key (optional, enables read-level auth)",
)
@click.option(
    "--admin-key",
    type=str,
    default=None,
    envvar="API_ADMIN_KEY",
    help="Admin API key (optional, enables admin-level auth)",
)
@click.option(
    "--mqtt-host",
    type=str,
    default="localhost",
    envvar="MQTT_HOST",
    help="MQTT broker host for commands",
)
@click.option(
    "--mqtt-port",
    type=int,
    default=1883,
    envvar="MQTT_PORT",
    help="MQTT broker port",
)
@click.option(
    "--mqtt-username",
    type=str,
    default=None,
    envvar="MQTT_USERNAME",
    help="MQTT username",
)
@click.option(
    "--mqtt-password",
    type=str,
    default=None,
    envvar="MQTT_PASSWORD",
    help="MQTT password",
)
@click.option(
    "--mqtt-prefix",
    type=str,
    default="meshcore",
    envvar=["MQTT_PREFIX", "MQTT_TOPIC_PREFIX"],
    help="MQTT topic prefix",
)
@click.option(
    "--mqtt-tls",
    is_flag=True,
    default=False,
    envvar="MQTT_TLS",
    help="Enable TLS/SSL for MQTT connection",
)
@click.option(
    "--mqtt-transport",
    type=click.Choice(["tcp", "websockets"], case_sensitive=False),
    default="websockets",
    envvar="MQTT_TRANSPORT",
    help="MQTT transport protocol",
)
@click.option(
    "--mqtt-ws-path",
    type=str,
    default="/",
    envvar="MQTT_WS_PATH",
    help="MQTT WebSocket path (used when transport=websockets)",
)
@click.option(
    "--cors-origins",
    type=str,
    default=None,
    envvar="CORS_ORIGINS",
    help="Comma-separated list of allowed CORS origins",
)
@click.option(
    "--metrics-enabled/--no-metrics",
    default=True,
    envvar="METRICS_ENABLED",
    help="Enable Prometheus metrics endpoint at /metrics",
)
@click.option(
    "--metrics-cache-ttl",
    type=int,
    default=60,
    envvar="METRICS_CACHE_TTL",
    help="Seconds to cache metrics output (reduces database load)",
)
@click.option(
    "--redis-enabled/--no-redis",
    default=False,
    envvar="REDIS_ENABLED",
    help="Enable Redis API response caching",
)
@click.option(
    "--redis-host",
    type=str,
    default="localhost",
    envvar="REDIS_HOST",
    help="Redis server host",
)
@click.option(
    "--redis-port",
    type=int,
    default=6379,
    envvar="REDIS_PORT",
    help="Redis server port",
)
@click.option(
    "--redis-db",
    type=int,
    default=0,
    envvar="REDIS_DB",
    help="Redis database number",
)
@click.option(
    "--redis-password",
    type=str,
    default=None,
    envvar="REDIS_PASSWORD",
    help="Redis password (optional)",
)
@click.option(
    "--redis-key-prefix",
    type=str,
    default="hub",
    envvar="REDIS_KEY_PREFIX",
    help="Prefix for all Redis cache keys",
)
@click.option(
    "--redis-cache-ttl",
    type=int,
    default=30,
    envvar="REDIS_CACHE_TTL",
    help="Default cache TTL in seconds",
)
@click.option(
    "--redis-cache-ttl-dashboard",
    type=int,
    default=3600,
    envvar="REDIS_CACHE_TTL_DASHBOARD",
    help=(
        "Cache TTL in seconds for dashboard endpoints, /routes/{id} detail, "
        "and per-route health history"
    ),
)
@click.option(
    "--api-cache-control-enabled/--no-api-cache-control",
    default=True,
    envvar="API_CACHE_CONTROL_ENABLED",
    help=(
        "Emit HTTP Cache-Control headers on /api/v1/* responses and ETag / "
        "If-None-Match handling on @cached endpoints"
    ),
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
@click.option(
    "--workers",
    type=int,
    default=1,
    envvar="API_WORKERS",
    help=(
        "Number of worker processes (default: 1). Values >1 run multiple "
        "processes for multi-core concurrency; workers are built from the "
        "environment via the app factory, so configure via env vars (not "
        "CLI flags) when scaling. Ignored in --reload mode."
    ),
)
@click.pass_context
def api(
    ctx: click.Context,
    host: str,
    port: int,
    data_home: str | None,
    database_url: str | None,
    read_key: str | None,
    admin_key: str | None,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    mqtt_prefix: str,
    mqtt_tls: bool,
    mqtt_transport: str,
    mqtt_ws_path: str,
    cors_origins: str | None,
    metrics_enabled: bool,
    metrics_cache_ttl: int,
    redis_enabled: bool,
    redis_host: str,
    redis_port: int,
    redis_db: int,
    redis_password: str | None,
    redis_key_prefix: str,
    redis_cache_ttl: int,
    redis_cache_ttl_dashboard: int,
    api_cache_control_enabled: bool,
    reload: bool,
    workers: int,
) -> None:
    """Run the REST API server.

    Provides REST API endpoints for querying mesh network data and sending
    commands to devices via MQTT.

    Examples:

        # Run with defaults (no auth)
        meshcore-hub api

        # Run with authentication
        meshcore-hub api --read-key secret --admin-key supersecret

        # Run with CORS for web frontend
        meshcore-hub api --cors-origins "http://localhost:8080,http://localhost:3000"

        # Development mode with auto-reload
        meshcore-hub api --reload
    """
    import uvicorn

    from meshcore_hub.common.config import get_api_settings
    from meshcore_hub.api.app import create_app

    # Get settings to compute effective values
    settings = get_api_settings()

    # Override data_home if provided
    if data_home:
        settings = settings.model_copy(update={"data_home": data_home})

    # Use effective database URL if not explicitly provided
    effective_db_url = database_url if database_url else settings.effective_database_url
    effective_data_home = data_home or settings.data_home

    click.echo("=" * 50)
    click.echo("MeshCore Hub API Server")
    click.echo("=" * 50)
    click.echo(f"Host: {host}")
    click.echo(f"Port: {port}")
    click.echo(f"Data home: {effective_data_home}")
    click.echo(f"Database: {effective_db_url}")
    click.echo(f"MQTT: {mqtt_host}:{mqtt_port} (prefix: {mqtt_prefix})")
    click.echo(f"MQTT transport: {mqtt_transport} (ws_path: {mqtt_ws_path})")
    click.echo(f"Read key configured: {read_key is not None}")
    click.echo(f"Admin key configured: {admin_key is not None}")
    click.echo(f"CORS origins: {cors_origins or 'none'}")
    click.echo(f"Metrics enabled: {metrics_enabled}")
    click.echo(f"Metrics cache TTL: {metrics_cache_ttl}s")
    click.echo(f"Redis enabled: {redis_enabled}")
    if redis_enabled:
        click.echo(f"Redis: {redis_host}:{redis_port}/{redis_db}")
        click.echo(f"Redis key prefix: {redis_key_prefix}")
        click.echo(
            f"Redis cache TTL: {redis_cache_ttl}s "
            f"(dashboard: {redis_cache_ttl_dashboard}s)"
        )
    click.echo(f"API Cache-Control enabled: {api_cache_control_enabled}")
    click.echo(f"Reload mode: {reload}")
    click.echo(f"Workers: {workers}")
    click.echo("=" * 50)

    # Parse CORS origins
    origins_list: list[str] | None = None
    if cors_origins:
        origins_list = [o.strip() for o in cors_origins.split(",")]

    if reload:
        # For development, use uvicorn's reload feature
        # We need to pass app as string for reload to work
        click.echo("\nStarting in development mode with auto-reload...")
        click.echo("Note: Using default settings for reload mode.")
        click.echo("Note: Redis defaults to disabled in reload mode.")

        uvicorn.run(
            "meshcore_hub.api.app:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
    elif workers > 1:
        # Multiple worker processes require an import string so uvicorn can
        # re-import the app in each forked worker. Workers rebuild the app from
        # the environment via the factory, so configuration must come from env
        # vars — CLI flags do not propagate to the workers.
        click.echo(f"\nStarting API server with {workers} workers...")
        uvicorn.run(
            "meshcore_hub.api.app:create_app_from_env",
            host=host,
            port=port,
            workers=workers,
            factory=True,
        )
    else:
        # Single process: build the app directly so CLI flags apply.
        app = create_app(
            database_url=effective_db_url,
            read_key=read_key,
            admin_key=admin_key,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_username=mqtt_username,
            mqtt_password=mqtt_password,
            mqtt_prefix=mqtt_prefix,
            mqtt_tls=mqtt_tls,
            mqtt_transport=mqtt_transport,
            mqtt_ws_path=mqtt_ws_path,
            cors_origins=origins_list,
            metrics_enabled=metrics_enabled,
            metrics_cache_ttl=metrics_cache_ttl,
            redis_enabled=redis_enabled,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password,
            redis_key_prefix=redis_key_prefix,
            redis_cache_ttl=redis_cache_ttl,
            redis_cache_ttl_dashboard=redis_cache_ttl_dashboard,
            api_cache_control_enabled=api_cache_control_enabled,
        )

        click.echo("\nStarting API server...")
        uvicorn.run(app, host=host, port=port)
