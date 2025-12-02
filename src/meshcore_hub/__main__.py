"""MeshCore Hub CLI entry point."""

import click

from meshcore_hub import __version__
from meshcore_hub.common.config import LogLevel
from meshcore_hub.common.logging import configure_logging


@click.group()
@click.version_option(version=__version__, prog_name="meshcore-hub")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="INFO",
    envvar="LOG_LEVEL",
    help="Set logging level",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """MeshCore Hub - Mesh network management and orchestration.

    A Python monorepo for managing and orchestrating MeshCore mesh networks.
    Provides components for interfacing with devices, collecting data,
    REST API access, and web dashboard visualization.
    """
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = LogLevel(log_level)
    configure_logging(level=ctx.obj["log_level"])


# Import and register component CLIs
from meshcore_hub.interface.cli import interface
from meshcore_hub.collector.cli import collector

cli.add_command(interface)
cli.add_command(collector)


@cli.command()
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
    "--database-url",
    type=str,
    default="sqlite:///./meshcore.db",
    envvar="DATABASE_URL",
    help="Database connection URL",
)
@click.option(
    "--read-key",
    type=str,
    default=None,
    envvar="API_READ_KEY",
    help="Read-only API key",
)
@click.option(
    "--admin-key",
    type=str,
    default=None,
    envvar="API_ADMIN_KEY",
    help="Admin API key",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
def api(
    host: str,
    port: int,
    database_url: str,
    read_key: str | None,
    admin_key: str | None,
    reload: bool,
) -> None:
    """Run the REST API server.

    Provides REST API endpoints for querying data and sending commands.
    """
    click.echo("Starting API server...")
    click.echo(f"Listening on: {host}:{port}")
    click.echo(f"Database: {database_url}")
    click.echo(f"Read key configured: {read_key is not None}")
    click.echo(f"Admin key configured: {admin_key is not None}")
    click.echo("API component not yet implemented.")


@cli.command()
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
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
def web(
    host: str,
    port: int,
    api_url: str,
    api_key: str | None,
    network_name: str,
    reload: bool,
) -> None:
    """Run the web dashboard.

    Provides a web interface for visualizing network status.
    """
    click.echo("Starting web dashboard...")
    click.echo(f"Listening on: {host}:{port}")
    click.echo(f"API URL: {api_url}")
    click.echo(f"Network name: {network_name}")
    click.echo("Web dashboard not yet implemented.")


@cli.group()
def db() -> None:
    """Database migration commands.

    Manage database schema migrations using Alembic.
    """
    pass


@db.command("upgrade")
@click.option(
    "--revision",
    type=str,
    default="head",
    help="Target revision (default: head)",
)
@click.option(
    "--database-url",
    type=str,
    default=None,
    envvar="DATABASE_URL",
    help="Database connection URL",
)
def db_upgrade(revision: str, database_url: str | None) -> None:
    """Upgrade database to a later version."""
    import os
    from alembic import command
    from alembic.config import Config

    click.echo(f"Upgrading database to revision: {revision}")

    alembic_cfg = Config("alembic.ini")
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    command.upgrade(alembic_cfg, revision)
    click.echo("Database upgrade complete.")


@db.command("downgrade")
@click.option(
    "--revision",
    type=str,
    required=True,
    help="Target revision",
)
@click.option(
    "--database-url",
    type=str,
    default=None,
    envvar="DATABASE_URL",
    help="Database connection URL",
)
def db_downgrade(revision: str, database_url: str | None) -> None:
    """Revert database to a previous version."""
    import os
    from alembic import command
    from alembic.config import Config

    click.echo(f"Downgrading database to revision: {revision}")

    alembic_cfg = Config("alembic.ini")
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    command.downgrade(alembic_cfg, revision)
    click.echo("Database downgrade complete.")


@db.command("revision")
@click.option(
    "-m",
    "--message",
    type=str,
    required=True,
    help="Revision message",
)
@click.option(
    "--autogenerate",
    is_flag=True,
    default=True,
    help="Autogenerate migration from models",
)
def db_revision(message: str, autogenerate: bool) -> None:
    """Create a new database migration."""
    from alembic import command
    from alembic.config import Config

    click.echo(f"Creating new revision: {message}")

    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, message=message, autogenerate=autogenerate)
    click.echo("Revision created.")


@db.command("current")
@click.option(
    "--database-url",
    type=str,
    default=None,
    envvar="DATABASE_URL",
    help="Database connection URL",
)
def db_current(database_url: str | None) -> None:
    """Show current database revision."""
    import os
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    command.current(alembic_cfg)


@db.command("history")
def db_history() -> None:
    """Show database migration history."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.history(alembic_cfg)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
