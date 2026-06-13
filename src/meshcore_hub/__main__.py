"""MeshCore Hub CLI entry point."""

import sys

import click
from dotenv import load_dotenv

from meshcore_hub import __version__
from meshcore_hub.common.config import LogLevel
from meshcore_hub.common.health import check_health
from meshcore_hub.common.logging import configure_logging

# Load .env file early so Click's envvar parameter picks up values
load_dotenv()


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
from meshcore_hub.collector.cli import collector
from meshcore_hub.api.cli import api
from meshcore_hub.web.cli import web

cli.add_command(collector)
cli.add_command(api)
cli.add_command(web)


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


@db.command("migrate-to-postgres")
@click.option(
    "--source",
    type=str,
    default=None,
    help="Source SQLite URL (default: sqlite:///{DATA_HOME}/collector/meshcore.db)",
)
@click.option(
    "--target",
    type=str,
    default=None,
    help="Target Postgres URL (default: the configured DATABASE_* connection)",
)
@click.option("--batch-size", type=int, default=2000, help="Rows per insert batch")
@click.option(
    "--truncate",
    is_flag=True,
    default=False,
    help="Delete existing rows from target tables before loading",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Report source/target row counts without writing",
)
@click.option(
    "--no-replication-role",
    is_flag=True,
    default=False,
    help="Don't disable FK triggers via session_replication_role (managed Postgres)",
)
def db_migrate_to_postgres(
    source: str | None,
    target: str | None,
    batch_size: int,
    truncate: bool,
    dry_run: bool,
    no_replication_role: bool,
) -> None:
    """Copy data from an existing SQLite database into PostgreSQL.

    Run 'db upgrade' against the target first to create the schema. This command
    only moves data and never modifies the source.
    """
    from pathlib import Path

    from meshcore_hub.common.config import CollectorSettings
    from meshcore_hub.common.db_migrate import migrate_sqlite_to_postgres

    settings = CollectorSettings()
    source_url = (
        source or f"sqlite:///{Path(settings.data_home) / 'collector' / 'meshcore.db'}"
    )
    target_url = target or settings.effective_database_url
    target_schema = settings.effective_database_schema

    click.echo(f"Source: {source_url}")
    click.echo(f"Target: {target_url} (schema: {target_schema})")
    if dry_run:
        click.echo("Mode: dry-run (no writes)")

    try:
        result = migrate_sqlite_to_postgres(
            source_url,
            target_url,
            target_schema=target_schema,
            batch_size=batch_size,
            truncate=truncate,
            dry_run=dry_run,
            disable_replication_role=no_replication_role,
        )
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("")
    if dry_run:
        # Preview only: the target is expected to be empty, so no OK/MISMATCH judgement.
        click.echo("table (source rows -> current target rows)")
        for t in result.tables:
            click.echo(f"  {t.name:28} {t.source_rows:>8} -> {t.target_rows:>8}")
        click.echo("")
        click.echo("Dry run complete.")
        return

    click.echo("table (source -> target)")
    for t in result.tables:
        status = "OK" if t.ok else "MISMATCH"
        click.echo(f"  {t.name:28} {t.source_rows:>8} -> {t.target_rows:>8}  {status}")
    if not result.ok:
        raise click.ClickException("Row-count mismatch between source and target")
    click.echo("")
    click.echo("Migration complete.")


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


@db.command("stamp")
@click.option(
    "--revision",
    type=str,
    default="head",
    help="Target revision to stamp (default: head)",
)
@click.option(
    "--database-url",
    type=str,
    default=None,
    envvar="DATABASE_URL",
    help="Database connection URL",
)
def db_stamp(revision: str, database_url: str | None) -> None:
    """Stamp database with revision without running migrations.

    Use this to mark an existing database as up-to-date when the schema
    was created before Alembic migrations were introduced.
    """
    import os
    from alembic import command
    from alembic.config import Config

    click.echo(f"Stamping database with revision: {revision}")

    alembic_cfg = Config("alembic.ini")
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    command.stamp(alembic_cfg, revision)
    click.echo("Database stamped successfully.")


# Health check commands for Docker HEALTHCHECK
@cli.group()
def health() -> None:
    """Health check commands for component monitoring.

    These commands are used by Docker HEALTHCHECK to monitor
    container health. Each running component writes its health
    status to a file, and these commands verify that status.
    """
    pass


@health.command("collector")
@click.option(
    "--timeout",
    type=int,
    default=60,
    help="Maximum age of health status in seconds",
)
def health_collector(timeout: int) -> None:
    """Check collector component health status.

    Returns exit code 0 if healthy, 1 if not.
    """
    is_healthy, message = check_health("collector", stale_threshold=timeout)

    if is_healthy:
        click.echo(f"Collector health: {message}")
        sys.exit(0)
    else:
        click.echo(f"Collector unhealthy: {message}", err=True)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
