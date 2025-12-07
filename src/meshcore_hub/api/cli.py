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
    "--mqtt-prefix",
    type=str,
    default="meshcore",
    envvar="MQTT_TOPIC_PREFIX",
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
    "--cors-origins",
    type=str,
    default=None,
    envvar="CORS_ORIGINS",
    help="Comma-separated list of allowed CORS origins",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
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
    mqtt_prefix: str,
    mqtt_tls: bool,
    cors_origins: str | None,
    reload: bool,
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
    click.echo(f"Read key configured: {read_key is not None}")
    click.echo(f"Admin key configured: {admin_key is not None}")
    click.echo(f"CORS origins: {cors_origins or 'none'}")
    click.echo(f"Reload mode: {reload}")
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

        uvicorn.run(
            "meshcore_hub.api.app:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
    else:
        # For production, create app directly
        app = create_app(
            database_url=effective_db_url,
            read_key=read_key,
            admin_key=admin_key,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_prefix=mqtt_prefix,
            mqtt_tls=mqtt_tls,
            cors_origins=origins_list,
        )

        click.echo("\nStarting API server...")
        uvicorn.run(app, host=host, port=port)
