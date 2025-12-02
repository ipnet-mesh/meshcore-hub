"""Web dashboard CLI commands."""

import click


@click.command()
@click.option(
    "--host",
    type=str,
    default="0.0.0.0",
    envvar="WEB_HOST",
    help="Web server host",
)
@click.option(
    "--port",
    type=int,
    default=8080,
    envvar="WEB_PORT",
    help="Web server port",
)
@click.option(
    "--api-url",
    type=str,
    default="http://localhost:8000",
    envvar="API_BASE_URL",
    help="API server base URL",
)
@click.option(
    "--api-key",
    type=str,
    default=None,
    envvar="API_KEY",
    help="API key for queries",
)
@click.option(
    "--network-name",
    type=str,
    default="MeshCore Network",
    envvar="NETWORK_NAME",
    help="Network display name",
)
@click.option(
    "--network-city",
    type=str,
    default=None,
    envvar="NETWORK_CITY",
    help="Network city location",
)
@click.option(
    "--network-country",
    type=str,
    default=None,
    envvar="NETWORK_COUNTRY",
    help="Network country",
)
@click.option(
    "--network-lat",
    type=float,
    default=0.0,
    envvar="NETWORK_LAT",
    help="Network center latitude",
)
@click.option(
    "--network-lon",
    type=float,
    default=0.0,
    envvar="NETWORK_LON",
    help="Network center longitude",
)
@click.option(
    "--network-radio-config",
    type=str,
    default=None,
    envvar="NETWORK_RADIO_CONFIG",
    help="Radio configuration description",
)
@click.option(
    "--network-contact-email",
    type=str,
    default=None,
    envvar="NETWORK_CONTACT_EMAIL",
    help="Contact email address",
)
@click.option(
    "--network-contact-discord",
    type=str,
    default=None,
    envvar="NETWORK_CONTACT_DISCORD",
    help="Discord server info",
)
@click.option(
    "--members-file",
    type=str,
    default=None,
    envvar="MEMBERS_FILE",
    help="Path to members JSON file",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
@click.pass_context
def web(
    ctx: click.Context,
    host: str,
    port: int,
    api_url: str,
    api_key: str | None,
    network_name: str,
    network_city: str | None,
    network_country: str | None,
    network_lat: float,
    network_lon: float,
    network_radio_config: str | None,
    network_contact_email: str | None,
    network_contact_discord: str | None,
    members_file: str | None,
    reload: bool,
) -> None:
    """Run the web dashboard.

    Provides a web interface for visualizing network status, browsing nodes,
    viewing messages, and displaying a node map.

    Examples:

        # Run with defaults
        meshcore-hub web

        # Run with custom network name and location
        meshcore-hub web --network-name "My Mesh" --network-city "New York" --network-country "USA"

        # Run with API authentication
        meshcore-hub web --api-url http://api.example.com --api-key secret

        # Run with members file
        meshcore-hub web --members-file /path/to/members.json

        # Development mode with auto-reload
        meshcore-hub web --reload
    """
    import uvicorn

    from meshcore_hub.web.app import create_app

    click.echo("=" * 50)
    click.echo("MeshCore Hub Web Dashboard")
    click.echo("=" * 50)
    click.echo(f"Host: {host}")
    click.echo(f"Port: {port}")
    click.echo(f"API URL: {api_url}")
    click.echo(f"API key configured: {api_key is not None}")
    click.echo(f"Network: {network_name}")
    if network_city and network_country:
        click.echo(f"Location: {network_city}, {network_country}")
    if network_lat != 0.0 or network_lon != 0.0:
        click.echo(f"Map center: {network_lat}, {network_lon}")
    if members_file:
        click.echo(f"Members file: {members_file}")
    click.echo(f"Reload mode: {reload}")
    click.echo("=" * 50)

    network_location = (network_lat, network_lon)

    if reload:
        # For development, use uvicorn's reload feature
        click.echo("\nStarting in development mode with auto-reload...")
        click.echo("Note: Using default settings for reload mode.")

        uvicorn.run(
            "meshcore_hub.web.app:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
    else:
        # For production, create app directly
        app = create_app(
            api_url=api_url,
            api_key=api_key,
            network_name=network_name,
            network_city=network_city,
            network_country=network_country,
            network_location=network_location,
            network_radio_config=network_radio_config,
            network_contact_email=network_contact_email,
            network_contact_discord=network_contact_discord,
            members_file=members_file,
        )

        click.echo("\nStarting web dashboard...")
        uvicorn.run(app, host=host, port=port)
