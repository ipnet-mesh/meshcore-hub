"""Web dashboard CLI commands."""

import click


@click.command()
@click.option(
    "--host",
    type=str,
    default=None,
    envvar="WEB_HOST",
    help="Web server host (default: 0.0.0.0)",
)
@click.option(
    "--port",
    type=int,
    default=None,
    envvar="WEB_PORT",
    help="Web server port (default: 8080)",
)
@click.option(
    "--api-url",
    type=str,
    default=None,
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
    "--data-home",
    type=str,
    default=None,
    envvar="DATA_HOME",
    help="Base data directory (default: ./data)",
)
@click.option(
    "--network-name",
    type=str,
    default=None,
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
    "--network-radio-profile",
    type=str,
    default=None,
    envvar="NETWORK_RADIO_PROFILE",
    help="Radio profile name",
)
@click.option(
    "--network-radio-frequency",
    type=float,
    default=None,
    envvar="NETWORK_RADIO_FREQUENCY",
    help="Radio frequency in MHz",
)
@click.option(
    "--network-radio-bandwidth",
    type=float,
    default=None,
    envvar="NETWORK_RADIO_BANDWIDTH",
    help="Radio bandwidth in kHz",
)
@click.option(
    "--network-radio-spreading-factor",
    type=int,
    default=None,
    envvar="NETWORK_RADIO_SPREADING_FACTOR",
    help="Radio spreading factor",
)
@click.option(
    "--network-radio-coding-rate",
    type=int,
    default=None,
    envvar="NETWORK_RADIO_CODING_RATE",
    help="Radio coding rate",
)
@click.option(
    "--network-radio-tx-power",
    type=float,
    default=None,
    envvar="NETWORK_RADIO_TX_POWER",
    help="Radio TX power in dBm",
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
    "--network-contact-github",
    type=str,
    default=None,
    envvar="NETWORK_CONTACT_GITHUB",
    help="GitHub repository URL",
)
@click.option(
    "--network-contact-youtube",
    type=str,
    default=None,
    envvar="NETWORK_CONTACT_YOUTUBE",
    help="YouTube channel URL",
)
@click.option(
    "--network-welcome-text",
    type=str,
    default=None,
    envvar="NETWORK_WELCOME_TEXT",
    help="Welcome text for homepage",
)
@click.option(
    "--network-announcement",
    type=str,
    default=None,
    envvar="NETWORK_ANNOUNCEMENT",
    help="Markdown announcement text for flash banner",
)
@click.option(
    "--system-announcement",
    type=str,
    default=None,
    envvar="SYSTEM_ANNOUNCEMENT",
    help="Markdown text for the non-dismissable system announcement banner",
)
@click.option(
    "--system-maintenance/--no-system-maintenance",
    default=None,
    help="Enable maintenance mode (disables site functionality). "
    "Defaults to the SYSTEM_MAINTENANCE environment variable.",
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
    host: str | None,
    port: int | None,
    api_url: str | None,
    api_key: str | None,
    data_home: str | None,
    network_name: str | None,
    network_city: str | None,
    network_country: str | None,
    network_radio_profile: str | None,
    network_radio_frequency: float | None,
    network_radio_bandwidth: float | None,
    network_radio_spreading_factor: int | None,
    network_radio_coding_rate: int | None,
    network_radio_tx_power: float | None,
    network_contact_email: str | None,
    network_contact_discord: str | None,
    network_contact_github: str | None,
    network_contact_youtube: str | None,
    network_welcome_text: str | None,
    network_announcement: str | None,
    system_announcement: str | None,
    system_maintenance: bool | None,
    reload: bool,
) -> None:
    """Run the web dashboard.

    Provides a web interface for visualizing network status, browsing nodes,
    viewing messages, and displaying a node map.

    Members are fetched from the API (managed by the collector).

    Examples:

        # Run with defaults
        meshcore-hub web

        # Run with custom network name and location
        meshcore-hub web --network-name "My Mesh" --network-city "New York" --network-country "USA"

        # Run with API authentication
        meshcore-hub web --api-url http://api.example.com --api-key secret

        # Development mode with auto-reload
        meshcore-hub web --reload
    """
    import uvicorn
    from pathlib import Path

    from meshcore_hub.common.config import get_web_settings
    from meshcore_hub.web.app import create_app

    # Get settings for defaults and display
    settings = get_web_settings()

    # Use CLI args or fall back to settings
    effective_host = host or settings.web_host
    effective_port = port or settings.web_port
    effective_data_home = data_home or settings.data_home

    # Ensure web data directory exists
    web_data_dir = Path(effective_data_home) / "web"
    web_data_dir.mkdir(parents=True, exist_ok=True)

    # Display effective settings
    effective_network_name = network_name or settings.network_name

    click.echo("=" * 50)
    click.echo("MeshCore Hub Web Dashboard")
    click.echo("=" * 50)
    click.echo(f"Host: {effective_host}")
    click.echo(f"Port: {effective_port}")
    click.echo(f"Data home: {effective_data_home}")
    click.echo(f"API URL: {api_url or settings.api_base_url}")
    click.echo(f"API key configured: {(api_key or settings.api_key) is not None}")
    click.echo(f"Network: {effective_network_name}")
    effective_city = network_city or settings.network_city
    effective_country = network_country or settings.network_country
    if effective_city and effective_country:
        click.echo(f"Location: {effective_city}, {effective_country}")
    click.echo(f"Reload mode: {reload}")
    oidc_status = "enabled" if settings.oidc_enabled else "disabled"
    click.echo(f"OIDC: {oidc_status}")
    disabled_features = [
        name for name, enabled in settings.features.items() if not enabled
    ]
    if disabled_features:
        click.echo(f"Disabled features: {', '.join(disabled_features)}")
    click.echo("=" * 50)

    if reload:
        # For development, use uvicorn's reload feature
        click.echo("\nStarting in development mode with auto-reload...")
        click.echo("Note: Settings loaded from environment/config.")

        uvicorn.run(
            "meshcore_hub.web.app:create_app",
            host=effective_host,
            port=effective_port,
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
            network_radio_profile=network_radio_profile,
            network_radio_frequency=network_radio_frequency,
            network_radio_bandwidth=network_radio_bandwidth,
            network_radio_spreading_factor=network_radio_spreading_factor,
            network_radio_coding_rate=network_radio_coding_rate,
            network_radio_tx_power=network_radio_tx_power,
            network_contact_email=network_contact_email,
            network_contact_discord=network_contact_discord,
            network_contact_github=network_contact_github,
            network_contact_youtube=network_contact_youtube,
            network_welcome_text=network_welcome_text,
            network_announcement=network_announcement,
            system_announcement=system_announcement,
            system_maintenance=system_maintenance,
        )

        click.echo("\nStarting web dashboard...")
        uvicorn.run(app, host=effective_host, port=effective_port)
