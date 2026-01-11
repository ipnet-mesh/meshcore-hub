"""CLI for the Collector component."""

from typing import TYPE_CHECKING

import click

from meshcore_hub.common.logging import configure_logging

if TYPE_CHECKING:
    from meshcore_hub.common.database import DatabaseManager


@click.group(invoke_without_command=True)
@click.pass_context
@click.option(
    "--mqtt-host",
    type=str,
    default="localhost",
    envvar="MQTT_HOST",
    help="MQTT broker host",
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
    "--prefix",
    type=str,
    default="meshcore",
    envvar="MQTT_PREFIX",
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
    "--data-home",
    type=str,
    default=None,
    envvar="DATA_HOME",
    help="Base data directory (default: ./data)",
)
@click.option(
    "--seed-home",
    type=str,
    default=None,
    envvar="SEED_HOME",
    help="Directory containing seed data files (default: {data_home}/collector)",
)
@click.option(
    "--database-url",
    type=str,
    default=None,
    envvar="DATABASE_URL",
    help="Database connection URL (default: sqlite:///{data_home}/collector/meshcore.db)",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="INFO",
    envvar="LOG_LEVEL",
    help="Log level",
)
def collector(
    ctx: click.Context,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    mqtt_tls: bool,
    data_home: str | None,
    seed_home: str | None,
    database_url: str | None,
    log_level: str,
) -> None:
    """Collector component for storing MeshCore events.

    The collector subscribes to MQTT broker and stores
    MeshCore events in the database for later retrieval.

    Events stored include:
    - Node advertisements
    - Contact and channel messages
    - Trace path data
    - Telemetry responses
    - Informational events (battery, status, etc.)

    When invoked without a subcommand, runs the collector service.
    """
    from meshcore_hub.common.config import get_collector_settings

    # Get settings to compute effective values
    settings = get_collector_settings()

    # Build settings overrides
    overrides = {}
    if data_home:
        overrides["data_home"] = data_home
    if seed_home:
        overrides["seed_home"] = seed_home

    if overrides:
        settings = settings.model_copy(update=overrides)

    # Use effective database URL if not explicitly provided
    effective_db_url = database_url if database_url else settings.effective_database_url

    ctx.ensure_object(dict)
    ctx.obj["mqtt_host"] = mqtt_host
    ctx.obj["mqtt_port"] = mqtt_port
    ctx.obj["mqtt_username"] = mqtt_username
    ctx.obj["mqtt_password"] = mqtt_password
    ctx.obj["prefix"] = prefix
    ctx.obj["mqtt_tls"] = mqtt_tls
    ctx.obj["data_home"] = data_home or settings.data_home
    ctx.obj["seed_home"] = settings.effective_seed_home
    ctx.obj["database_url"] = effective_db_url
    ctx.obj["log_level"] = log_level
    ctx.obj["settings"] = settings

    # If no subcommand, run the collector service
    if ctx.invoked_subcommand is None:
        _run_collector_service(
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_username=mqtt_username,
            mqtt_password=mqtt_password,
            prefix=prefix,
            mqtt_tls=mqtt_tls,
            database_url=effective_db_url,
            log_level=log_level,
            data_home=data_home or settings.data_home,
            seed_home=settings.effective_seed_home,
        )


def _run_collector_service(
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    mqtt_tls: bool,
    database_url: str,
    log_level: str,
    data_home: str,
    seed_home: str,
) -> None:
    """Run the collector service.

    Note: Seed data import should be done using the 'meshcore-hub collector seed'
    command or the dedicated seed container before starting the collector service.

    Webhooks can be configured via environment variables:
    - WEBHOOK_ADVERTISEMENT_URL: Webhook for advertisement events
    - WEBHOOK_MESSAGE_URL: Webhook for all message events
    - WEBHOOK_CHANNEL_MESSAGE_URL: Override for channel messages
    - WEBHOOK_DIRECT_MESSAGE_URL: Override for direct messages
    """
    from pathlib import Path

    configure_logging(level=log_level)

    # Ensure data directory exists
    collector_data_dir = Path(data_home) / "collector"
    collector_data_dir.mkdir(parents=True, exist_ok=True)

    click.echo("Starting MeshCore Collector")
    click.echo(f"Data home: {data_home}")
    click.echo(f"Seed home: {seed_home}")
    click.echo(f"MQTT: {mqtt_host}:{mqtt_port} (prefix: {prefix})")
    click.echo(f"Database: {database_url}")

    # Load webhook configuration from settings
    from meshcore_hub.collector.webhook import (
        WebhookDispatcher,
        create_webhooks_from_settings,
    )
    from meshcore_hub.common.config import get_collector_settings

    settings = get_collector_settings()
    webhooks = create_webhooks_from_settings(settings)
    webhook_dispatcher = WebhookDispatcher(webhooks) if webhooks else None

    click.echo("")
    if webhook_dispatcher and webhook_dispatcher.webhooks:
        click.echo(f"Webhooks configured: {len(webhooks)}")
        for wh in webhooks:
            click.echo(f"  - {wh.name}: {wh.url}")
    else:
        click.echo("Webhooks: None configured")

    from meshcore_hub.collector.subscriber import run_collector

    # Show cleanup configuration
    click.echo("")
    click.echo("Cleanup configuration:")
    if settings.data_retention_enabled:
        click.echo(
            f"  Event data: Enabled (retention: {settings.data_retention_days} days)"
        )
    else:
        click.echo("  Event data: Disabled")

    if settings.node_cleanup_enabled:
        click.echo(
            f"  Inactive nodes: Enabled (inactivity: {settings.node_cleanup_days} days)"
        )
    else:
        click.echo("  Inactive nodes: Disabled")

    if settings.data_retention_enabled or settings.node_cleanup_enabled:
        click.echo(f"  Interval: {settings.data_retention_interval_hours} hours")

    click.echo("")
    click.echo("Starting MQTT subscriber...")
    run_collector(
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=prefix,
        mqtt_tls=mqtt_tls,
        database_url=database_url,
        webhook_dispatcher=webhook_dispatcher,
        cleanup_enabled=settings.data_retention_enabled,
        cleanup_retention_days=settings.data_retention_days,
        cleanup_interval_hours=settings.data_retention_interval_hours,
        node_cleanup_enabled=settings.node_cleanup_enabled,
        node_cleanup_days=settings.node_cleanup_days,
    )


@collector.command("run")
@click.pass_context
def run_cmd(ctx: click.Context) -> None:
    """Run the collector service.

    This is the default behavior when no subcommand is specified.
    """
    _run_collector_service(
        mqtt_host=ctx.obj["mqtt_host"],
        mqtt_port=ctx.obj["mqtt_port"],
        mqtt_username=ctx.obj["mqtt_username"],
        mqtt_password=ctx.obj["mqtt_password"],
        prefix=ctx.obj["prefix"],
        mqtt_tls=ctx.obj["mqtt_tls"],
        database_url=ctx.obj["database_url"],
        log_level=ctx.obj["log_level"],
        data_home=ctx.obj["data_home"],
        seed_home=ctx.obj["seed_home"],
    )


@collector.command("seed")
@click.option(
    "--no-create-nodes",
    is_flag=True,
    default=False,
    help="Skip tags for nodes that don't exist (default: create nodes)",
)
@click.pass_context
def seed_cmd(
    ctx: click.Context,
    no_create_nodes: bool,
) -> None:
    """Import seed data from SEED_HOME directory.

    Looks for the following files in SEED_HOME:
    - node_tags.yaml: Node tag definitions (keyed by public_key)
    - members.yaml: Network member definitions

    Files that don't exist are skipped. This command is idempotent -
    existing records are updated, new records are created.

    SEED_HOME defaults to ./seed but can be overridden
    with the --seed-home option or SEED_HOME environment variable.
    """
    configure_logging(level=ctx.obj["log_level"])

    seed_home = ctx.obj["seed_home"]
    click.echo(f"Seed home: {seed_home}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager

    # Initialize database (schema managed by Alembic migrations)
    db = DatabaseManager(ctx.obj["database_url"])

    # Run seed import
    imported_any = _run_seed_import(
        seed_home=seed_home,
        db=db,
        create_nodes=not no_create_nodes,
        verbose=True,
    )

    if not imported_any:
        click.echo("\nNo seed files found. Nothing to import.")
    else:
        click.echo("\nSeed import complete.")

    db.dispose()


def _run_seed_import(
    seed_home: str,
    db: "DatabaseManager",
    create_nodes: bool = True,
    verbose: bool = False,
) -> bool:
    """Run seed import from SEED_HOME directory.

    Args:
        seed_home: Path to seed home directory
        db: Database manager instance
        create_nodes: If True, create nodes that don't exist
        verbose: If True, output progress messages

    Returns:
        True if any files were imported, False otherwise
    """
    from pathlib import Path

    from meshcore_hub.collector.member_import import import_members
    from meshcore_hub.collector.tag_import import import_tags

    imported_any = False

    # Import node tags if file exists
    node_tags_file = Path(seed_home) / "node_tags.yaml"
    if node_tags_file.exists():
        if verbose:
            click.echo(f"\nImporting node tags from: {node_tags_file}")
        stats = import_tags(
            file_path=str(node_tags_file),
            db=db,
            create_nodes=create_nodes,
            clear_existing=True,
        )
        if verbose:
            if stats["deleted"]:
                click.echo(f"  Deleted {stats['deleted']} existing tags")
            click.echo(
                f"  Tags: {stats['created']} created, {stats['updated']} updated"
            )
            if stats["nodes_created"]:
                click.echo(f"  Nodes created: {stats['nodes_created']}")
            if stats["errors"]:
                for error in stats["errors"]:
                    click.echo(f"  Error: {error}", err=True)
        imported_any = True
    elif verbose:
        click.echo(f"\nNo node_tags.yaml found in {seed_home}")

    # Import members if file exists
    members_file = Path(seed_home) / "members.yaml"
    if members_file.exists():
        if verbose:
            click.echo(f"\nImporting members from: {members_file}")
        stats = import_members(
            file_path=str(members_file),
            db=db,
        )
        if verbose:
            click.echo(
                f"  Members: {stats['created']} created, {stats['updated']} updated"
            )
            if stats["errors"]:
                for error in stats["errors"]:
                    click.echo(f"  Error: {error}", err=True)
        imported_any = True
    elif verbose:
        click.echo(f"\nNo members.yaml found in {seed_home}")

    return imported_any


@collector.command("import-tags")
@click.argument("file", type=click.Path(), required=False, default=None)
@click.option(
    "--no-create-nodes",
    is_flag=True,
    default=False,
    help="Skip tags for nodes that don't exist (default: create nodes)",
)
@click.option(
    "--clear-existing",
    is_flag=True,
    default=False,
    help="Delete all existing tags before importing",
)
@click.pass_context
def import_tags_cmd(
    ctx: click.Context,
    file: str | None,
    no_create_nodes: bool,
    clear_existing: bool,
) -> None:
    """Import node tags from a YAML file.

    Reads a YAML file containing tag definitions and upserts them
    into the database. By default, existing tags are updated and new tags are created.
    Use --clear-existing to delete all tags before importing.

    FILE is the path to the YAML file containing tags.
    If not provided, defaults to {SEED_HOME}/node_tags.yaml.

    Expected YAML format (keyed by public_key):

    \b
    0123456789abcdef...:
      friendly_name: My Node
      altitude:
        value: "150"
        type: number
      active:
        value: "true"
        type: boolean

    Shorthand is also supported (string values with default type):

    \b
    0123456789abcdef...:
      friendly_name: My Node
      role: gateway

    Supported types: string, number, boolean
    """
    from pathlib import Path

    configure_logging(level=ctx.obj["log_level"])

    # Use node_tags_file from settings if not provided
    settings = ctx.obj["settings"]
    tags_file = file if file else settings.node_tags_file

    # Check if file exists
    if not Path(tags_file).exists():
        click.echo(f"Tags file not found: {tags_file}")
        if not file:
            click.echo("Specify a file path or create the default node_tags.yaml.")
        return

    click.echo(f"Importing tags from: {tags_file}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.tag_import import import_tags

    # Initialize database (schema managed by Alembic migrations)
    db = DatabaseManager(ctx.obj["database_url"])

    # Import tags
    stats = import_tags(
        file_path=tags_file,
        db=db,
        create_nodes=not no_create_nodes,
        clear_existing=clear_existing,
    )

    # Report results
    click.echo("")
    click.echo("Import complete:")
    if stats["deleted"]:
        click.echo(f"  Tags deleted: {stats['deleted']}")
    click.echo(f"  Total tags in file: {stats['total']}")
    click.echo(f"  Tags created: {stats['created']}")
    click.echo(f"  Tags updated: {stats['updated']}")
    click.echo(f"  Tags skipped: {stats['skipped']}")
    click.echo(f"  Nodes created: {stats['nodes_created']}")

    if stats["errors"]:
        click.echo("")
        click.echo("Errors:")
        for error in stats["errors"]:
            click.echo(f"  - {error}", err=True)

    db.dispose()


@collector.command("import-members")
@click.argument("file", type=click.Path(), required=False, default=None)
@click.pass_context
def import_members_cmd(
    ctx: click.Context,
    file: str | None,
) -> None:
    """Import network members from a YAML file.

    Reads a YAML file containing member definitions and upserts them
    into the database. Existing members (matched by name) are updated,
    new members are created.

    FILE is the path to the YAML file containing members.
    If not provided, defaults to {SEED_HOME}/members.yaml.

    Expected YAML format (list):

    \b
    - name: John Doe
      callsign: N0CALL
      role: Network Operator
      description: Example member

    Or with "members" key:

    \b
    members:
      - name: John Doe
        callsign: N0CALL
    """
    from pathlib import Path

    configure_logging(level=ctx.obj["log_level"])

    # Use members_file from settings if not provided
    settings = ctx.obj["settings"]
    members_file = file if file else settings.members_file

    # Check if file exists
    if not Path(members_file).exists():
        click.echo(f"Members file not found: {members_file}")
        if not file:
            click.echo("Specify a file path or create the default members.yaml.")
        return

    click.echo(f"Importing members from: {members_file}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.member_import import import_members

    # Initialize database (schema managed by Alembic migrations)
    db = DatabaseManager(ctx.obj["database_url"])

    # Import members
    stats = import_members(
        file_path=members_file,
        db=db,
    )

    # Report results
    click.echo("")
    click.echo("Import complete:")
    click.echo(f"  Total members in file: {stats['total']}")
    click.echo(f"  Members created: {stats['created']}")
    click.echo(f"  Members updated: {stats['updated']}")

    if stats["errors"]:
        click.echo("")
        click.echo("Errors:")
        for error in stats["errors"]:
            click.echo(f"  - {error}", err=True)

    db.dispose()


@collector.command("cleanup")
@click.option(
    "--retention-days",
    type=int,
    default=30,
    envvar="DATA_RETENTION_DAYS",
    help="Number of days to retain data (default: 30)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be deleted without deleting",
)
@click.pass_context
def cleanup_cmd(
    ctx: click.Context,
    retention_days: int,
    dry_run: bool,
) -> None:
    """Manually run data cleanup to delete old events.

    Deletes event data older than the retention period:
    - Advertisements
    - Messages (channel and direct)
    - Telemetry
    - Trace paths
    - Event logs

    Node records are never deleted - only event data.

    Use --dry-run to preview what would be deleted without
    actually deleting anything.
    """
    import asyncio

    configure_logging(level=ctx.obj["log_level"])

    click.echo(f"Database: {ctx.obj['database_url']}")
    click.echo(f"Retention: {retention_days} days")
    click.echo(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    click.echo("")

    if dry_run:
        click.echo("Running in dry-run mode - no data will be deleted.")
    else:
        click.echo("WARNING: This will permanently delete old event data!")
        if not click.confirm("Continue?"):
            click.echo("Aborted.")
            return

    click.echo("")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.cleanup import cleanup_old_data

    # Initialize database
    db = DatabaseManager(ctx.obj["database_url"])

    # Run cleanup
    async def run_cleanup() -> None:
        async with db.async_session() as session:
            stats = await cleanup_old_data(
                session,
                retention_days,
                dry_run=dry_run,
            )

            click.echo("")
            click.echo("Cleanup results:")
            click.echo(f"  Advertisements: {stats.advertisements_deleted}")
            click.echo(f"  Messages: {stats.messages_deleted}")
            click.echo(f"  Telemetry: {stats.telemetry_deleted}")
            click.echo(f"  Trace paths: {stats.trace_paths_deleted}")
            click.echo(f"  Event logs: {stats.event_logs_deleted}")
            click.echo(f"  Total: {stats.total_deleted}")

            if dry_run:
                click.echo("")
                click.echo("(Dry run - no data was actually deleted)")

    asyncio.run(run_cleanup())
    db.dispose()
    click.echo("")
    click.echo("Cleanup complete." if not dry_run else "Dry run complete.")


@collector.command("truncate")
@click.option(
    "--members",
    is_flag=True,
    default=False,
    help="Truncate members table",
)
@click.option(
    "--nodes",
    is_flag=True,
    default=False,
    help="Truncate nodes table (also clears tags, advertisements, messages, telemetry, trace paths)",
)
@click.option(
    "--messages",
    is_flag=True,
    default=False,
    help="Truncate messages table",
)
@click.option(
    "--advertisements",
    is_flag=True,
    default=False,
    help="Truncate advertisements table",
)
@click.option(
    "--telemetry",
    is_flag=True,
    default=False,
    help="Truncate telemetry table",
)
@click.option(
    "--trace-paths",
    is_flag=True,
    default=False,
    help="Truncate trace_paths table",
)
@click.option(
    "--event-logs",
    is_flag=True,
    default=False,
    help="Truncate event_logs table",
)
@click.option(
    "--all",
    "truncate_all",
    is_flag=True,
    default=False,
    help="Truncate ALL tables (use with caution!)",
)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt",
)
@click.pass_context
def truncate_cmd(
    ctx: click.Context,
    members: bool,
    nodes: bool,
    messages: bool,
    advertisements: bool,
    telemetry: bool,
    trace_paths: bool,
    event_logs: bool,
    truncate_all: bool,
    yes: bool,
) -> None:
    """Truncate (clear) data tables.

    WARNING: This permanently deletes data! Use with caution.

    Examples:
      # Clear members table
      meshcore-hub collector truncate --members

      # Clear messages and advertisements
      meshcore-hub collector truncate --messages --advertisements

      # Clear everything (requires confirmation)
      meshcore-hub collector truncate --all

    Note: Clearing nodes also clears all related data (tags, advertisements,
    messages, telemetry, trace paths) due to foreign key constraints.
    """
    configure_logging(level=ctx.obj["log_level"])

    # Determine what to truncate
    if truncate_all:
        tables_to_clear = {
            "members": True,
            "nodes": True,
            "messages": True,
            "advertisements": True,
            "telemetry": True,
            "trace_paths": True,
            "event_logs": True,
        }
    else:
        tables_to_clear = {
            "members": members,
            "nodes": nodes,
            "messages": messages,
            "advertisements": advertisements,
            "telemetry": telemetry,
            "trace_paths": trace_paths,
            "event_logs": event_logs,
        }

    # Check if any tables selected
    if not any(tables_to_clear.values()):
        click.echo("No tables specified. Use --help to see available options.")
        return

    # Show what will be cleared
    click.echo("Database: " + ctx.obj["database_url"])
    click.echo("")
    click.echo("The following tables will be PERMANENTLY CLEARED:")
    for table, should_clear in tables_to_clear.items():
        if should_clear:
            click.echo(f"  - {table}")

    if tables_to_clear.get("nodes"):
        click.echo("")
        click.echo(
            "WARNING: Clearing nodes will also clear all related data due to foreign keys:"
        )
        click.echo("  - node_tags")
        click.echo("  - advertisements")
        click.echo("  - messages")
        click.echo("  - telemetry")
        click.echo("  - trace_paths")

    click.echo("")

    # Confirm
    if not yes:
        if not click.confirm(
            "Are you sure you want to permanently delete this data?", default=False
        ):
            click.echo("Aborted.")
            return

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.common.models import (
        Advertisement,
        EventLog,
        Member,
        Message,
        Node,
        NodeTag,
        Telemetry,
        TracePath,
    )
    from sqlalchemy import delete
    from sqlalchemy.engine import CursorResult

    db = DatabaseManager(ctx.obj["database_url"])

    with db.session_scope() as session:
        # Truncate in correct order to respect foreign keys
        cleared: list[str] = []

        # Clear members (no dependencies)
        if tables_to_clear.get("members"):
            result: CursorResult = session.execute(delete(Member))  # type: ignore
            cleared.append(f"members: {result.rowcount} rows")

        # Clear event-specific tables first (they depend on nodes)
        if tables_to_clear.get("messages"):
            result = session.execute(delete(Message))  # type: ignore
            cleared.append(f"messages: {result.rowcount} rows")

        if tables_to_clear.get("advertisements"):
            result = session.execute(delete(Advertisement))  # type: ignore
            cleared.append(f"advertisements: {result.rowcount} rows")

        if tables_to_clear.get("telemetry"):
            result = session.execute(delete(Telemetry))  # type: ignore
            cleared.append(f"telemetry: {result.rowcount} rows")

        if tables_to_clear.get("trace_paths"):
            result = session.execute(delete(TracePath))  # type: ignore
            cleared.append(f"trace_paths: {result.rowcount} rows")

        if tables_to_clear.get("event_logs"):
            result = session.execute(delete(EventLog))  # type: ignore
            cleared.append(f"event_logs: {result.rowcount} rows")

        # Clear nodes last (this will cascade delete tags and any remaining events)
        if tables_to_clear.get("nodes"):
            # Delete tags first (they depend on nodes)
            tag_result: CursorResult = session.execute(delete(NodeTag))  # type: ignore
            cleared.append(f"node_tags: {tag_result.rowcount} rows (cascade)")

            # Delete nodes (will cascade to remaining related tables)
            node_result: CursorResult = session.execute(delete(Node))  # type: ignore
            cleared.append(f"nodes: {node_result.rowcount} rows")

    db.dispose()

    click.echo("")
    click.echo("Truncate complete. Cleared:")
    for item in cleared:
        click.echo(f"  - {item}")
    click.echo("")
