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
    mqtt_transport: str,
    mqtt_ws_path: str,
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
    ctx.obj["mqtt_transport"] = mqtt_transport
    ctx.obj["mqtt_ws_path"] = mqtt_ws_path
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
            mqtt_transport=mqtt_transport,
            mqtt_ws_path=mqtt_ws_path,
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
    mqtt_transport: str,
    mqtt_ws_path: str,
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
    click.echo(f"MQTT transport: {mqtt_transport} (ws_path: {mqtt_ws_path})")
    click.echo(f"Database: {database_url}")

    # Load webhook configuration from settings
    from meshcore_hub.collector.webhook import (
        WebhookDispatcher,
        create_webhooks_from_settings,
    )
    from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder
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
    builtin_keys = len(LetsMeshPacketDecoder.BUILTIN_CHANNEL_KEYS)
    click.echo(f"Packet decoder: {builtin_keys} built-in keys, loading from database")

    click.echo("")
    click.echo("Starting MQTT subscriber...")
    run_collector(
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=prefix,
        mqtt_tls=mqtt_tls,
        mqtt_transport=mqtt_transport,
        mqtt_ws_path=mqtt_ws_path,
        database_url=database_url,
        webhook_dispatcher=webhook_dispatcher,
        cleanup_enabled=settings.data_retention_enabled,
        cleanup_retention_days=settings.data_retention_days,
        cleanup_interval_hours=settings.data_retention_interval_hours,
        node_cleanup_enabled=settings.node_cleanup_enabled,
        node_cleanup_days=settings.node_cleanup_days,
        channel_refresh_interval_seconds=settings.channel_refresh_interval_seconds,
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
        mqtt_transport=ctx.obj["mqtt_transport"],
        mqtt_ws_path=ctx.obj["mqtt_ws_path"],
        database_url=ctx.obj["database_url"],
        log_level=ctx.obj["log_level"],
        data_home=ctx.obj["data_home"],
        seed_home=ctx.obj["seed_home"],
    )


@collector.group("channel")
@click.pass_context
def channel_group(ctx: click.Context) -> None:
    """Manage decryption channels in the database."""
    pass


@channel_group.command("list")
@click.pass_context
def channel_list_cmd(ctx: click.Context) -> None:
    """List all channels in the database."""
    configure_logging(level=ctx.obj["log_level"])

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.common.models.channel import Channel

    db = DatabaseManager(ctx.obj["database_url"])
    with db.session_scope() as session:
        channels = session.query(Channel).order_by(Channel.name).all()
        if not channels:
            click.echo("No channels found.")
        else:
            click.echo(
                f"{'Name':<20} {'Key':<16} {'Hash':<6} {'Visibility':<12} {'Enabled'}"
            )
            click.echo("-" * 70)
            for ch in channels:
                click.echo(
                    f"{ch.name:<20} {ch.masked_key:<16} {ch.channel_hash:<6} "
                    f"{ch.visibility:<12} {'Yes' if ch.enabled else 'No'}"
                )
    db.dispose()


@channel_group.command("add")
@click.option("--name", required=True, help="Channel display name")
@click.option(
    "--key", "key_hex", required=True, help="Channel key as hex (32 or 64 chars)"
)
@click.option(
    "--visibility",
    type=click.Choice(["public", "member", "operator", "admin"]),
    default="public",
    help="Channel visibility level (default: public)",
)
@click.pass_context
def channel_add_cmd(
    ctx: click.Context,
    name: str,
    key_hex: str,
    visibility: str,
) -> None:
    """Add a new channel to the database."""
    configure_logging(level=ctx.obj["log_level"])

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.common.models.channel import Channel

    db = DatabaseManager(ctx.obj["database_url"])
    with db.session_scope() as session:
        existing = session.query(Channel).filter(Channel.name == name).first()
        if existing:
            click.echo(f"Error: Channel '{name}' already exists.", err=True)
            db.dispose()
            return

        channel = Channel(
            name=name,
            key_hex=key_hex.upper(),
            channel_hash=Channel.compute_channel_hash(key_hex.upper()),
            visibility=visibility,
            enabled=True,
        )
        session.add(channel)
        click.echo(f"Channel '{name}' added (hash={channel.channel_hash})")
    db.dispose()


@channel_group.command("remove")
@click.option("--name", required=True, help="Channel name to remove")
@click.pass_context
def channel_remove_cmd(ctx: click.Context, name: str) -> None:
    """Remove a channel from the database."""
    configure_logging(level=ctx.obj["log_level"])

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.common.models.channel import Channel

    db = DatabaseManager(ctx.obj["database_url"])
    with db.session_scope() as session:
        channel = session.query(Channel).filter(Channel.name == name).first()
        if not channel:
            click.echo(f"Error: Channel '{name}' not found.", err=True)
            db.dispose()
            return
        session.delete(channel)
        click.echo(f"Channel '{name}' removed.")
    db.dispose()


@channel_group.command("enable")
@click.option("--name", required=True, help="Channel name to enable")
@click.pass_context
def channel_enable_cmd(ctx: click.Context, name: str) -> None:
    """Enable a channel."""
    configure_logging(level=ctx.obj["log_level"])

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.common.models.channel import Channel

    db = DatabaseManager(ctx.obj["database_url"])
    with db.session_scope() as session:
        channel = session.query(Channel).filter(Channel.name == name).first()
        if not channel:
            click.echo(f"Error: Channel '{name}' not found.", err=True)
            db.dispose()
            return
        channel.enabled = True
        click.echo(f"Channel '{name}' enabled.")
    db.dispose()


@channel_group.command("disable")
@click.option("--name", required=True, help="Channel name to disable")
@click.pass_context
def channel_disable_cmd(ctx: click.Context, name: str) -> None:
    """Disable a channel."""
    configure_logging(level=ctx.obj["log_level"])

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.common.models.channel import Channel

    db = DatabaseManager(ctx.obj["database_url"])
    with db.session_scope() as session:
        channel = session.query(Channel).filter(Channel.name == name).first()
        if not channel:
            click.echo(f"Error: Channel '{name}' not found.", err=True)
            db.dispose()
            return
        channel.enabled = False
        click.echo(f"Channel '{name}' disabled.")
    db.dispose()


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

    # Import channels if file exists
    channels_file = Path(seed_home) / "channels.yaml"
    if channels_file.exists():
        if verbose:
            click.echo(f"\nImporting channels from: {channels_file}")
        channel_stats = _import_channels(
            file_path=str(channels_file),
            db=db,
            verbose=verbose,
        )
        if verbose:
            click.echo(
                f"  Channels: {channel_stats['created']} created, "
                f"{channel_stats['updated']} updated"
            )
            if channel_stats["errors"]:
                for error in channel_stats["errors"]:  # type: ignore[union-attr]
                    click.echo(f"  Error: {error}", err=True)
        imported_any = True
    elif verbose:
        click.echo(f"\nNo channels.yaml found in {seed_home}")

    return imported_any


def _import_channels(
    file_path: str,
    db: "DatabaseManager",
    verbose: bool = False,
) -> dict[str, int | list[str]]:
    """Import channels from a YAML file.

    Supports two formats:
    - Shorthand: name: HEX (value is string, treated as key_hex)
    - Expanded: name: { key: HEX, enabled: true } (value is dict)

    Visibility is always 'public' for seeded channels.

    Returns:
        Dict with 'created', 'updated', and 'errors' counts.
    """
    import yaml

    from meshcore_hub.common.models.channel import Channel

    created: int = 0
    updated: int = 0
    errors: list[str] = []

    with open(file_path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        return {"created": created, "updated": updated, "errors": errors}

    with db.session_scope() as session:
        for name, value in data.items():
            try:
                if isinstance(value, str):
                    key_hex = value.strip().upper()
                    enabled = True
                elif isinstance(value, dict):
                    key_hex = value.get("key", "").strip().upper()
                    enabled = value.get("enabled", True)
                else:
                    errors.append(f"Invalid format for channel '{name}'")
                    continue

                if not key_hex:
                    errors.append(f"Empty key for channel '{name}'")
                    continue

                existing = session.query(Channel).filter(Channel.name == name).first()
                if existing:
                    existing.key_hex = key_hex
                    existing.channel_hash = Channel.compute_channel_hash(key_hex)
                    existing.enabled = enabled
                    updated += 1
                else:
                    channel = Channel(
                        name=name,
                        key_hex=key_hex,
                        channel_hash=Channel.compute_channel_hash(key_hex),
                        visibility="public",
                        enabled=enabled,
                    )
                    session.add(channel)
                    created += 1
            except Exception as e:
                errors.append(f"Channel '{name}': {e}")

    return {"created": created, "updated": updated, "errors": errors}


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


@collector.command("cleanup")
@click.option(
    "--retention-days",
    type=int,
    default=30,
    envvar="DATA_RETENTION_DAYS",
    help="Number of days to retain data (default: 30)",
)
@click.option(
    "--node-cleanup",
    is_flag=True,
    default=False,
    help="Also delete inactive nodes and orphaned relations",
)
@click.option(
    "--node-cleanup-days",
    type=int,
    default=30,
    help="Delete nodes not seen for this many days (default: 30)",
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
    node_cleanup: bool,
    node_cleanup_days: int,
    dry_run: bool,
) -> None:
    """Manually run data cleanup to delete old events.

    Deletes event data older than the retention period:
    - Advertisements
    - Messages (channel and direct)
    - Telemetry
    - Trace paths
    - Event logs

    Use --node-cleanup to also delete inactive nodes (not seen for
    --node-cleanup-days) and any orphaned rows in user_profile_nodes,
    event_observers, and node_tags that reference deleted nodes.

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
    from meshcore_hub.collector.cleanup import (
        cleanup_old_data,
        cleanup_inactive_nodes,
        cleanup_orphaned_node_relations,
    )

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

            if node_cleanup:
                click.echo("")
                nodes_deleted = await cleanup_inactive_nodes(
                    session,
                    node_cleanup_days,
                    dry_run=dry_run,
                )
                mode = "would be" if dry_run else "were"
                click.echo(
                    f"  Inactive nodes {mode} deleted: {nodes_deleted}"
                    f" (older than {node_cleanup_days} days)"
                )

                orphan_counts = await cleanup_orphaned_node_relations(
                    session,
                    dry_run=dry_run,
                )
                if any(orphan_counts.values()):
                    click.echo("  Orphaned relations:")
                    for table_name, count in orphan_counts.items():
                        if count > 0:
                            click.echo(f"    {table_name}: {count}")

            if dry_run:
                click.echo("")
                click.echo("(Dry run - no data was actually deleted)")

    asyncio.run(run_cleanup())
    db.dispose()
    click.echo("")
    click.echo("Cleanup complete." if not dry_run else "Dry run complete.")


@collector.command("truncate")
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
            "nodes": True,
            "messages": True,
            "advertisements": True,
            "telemetry": True,
            "trace_paths": True,
            "event_logs": True,
        }
    else:
        tables_to_clear = {
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
        click.echo("  - user_profile_nodes")
        click.echo("  - event_observers")
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
        Message,
        Node,
        NodeTag,
        Telemetry,
        TracePath,
    )
    from sqlalchemy import delete

    db = DatabaseManager(ctx.obj["database_url"])

    with db.session_scope() as session:
        cleared: list[str] = []

        if tables_to_clear.get("messages"):
            result = session.execute(delete(Message))
            cleared.append(f"messages: {result.rowcount} rows")  # type: ignore[attr-defined]

        if tables_to_clear.get("advertisements"):
            result = session.execute(delete(Advertisement))
            cleared.append(f"advertisements: {result.rowcount} rows")  # type: ignore[attr-defined]

        if tables_to_clear.get("telemetry"):
            result = session.execute(delete(Telemetry))
            cleared.append(f"telemetry: {result.rowcount} rows")  # type: ignore[attr-defined]

        if tables_to_clear.get("trace_paths"):
            result = session.execute(delete(TracePath))
            cleared.append(f"trace_paths: {result.rowcount} rows")  # type: ignore[attr-defined]

        if tables_to_clear.get("event_logs"):
            result = session.execute(delete(EventLog))
            cleared.append(f"event_logs: {result.rowcount} rows")  # type: ignore[attr-defined]

        if tables_to_clear.get("nodes"):
            tag_result = session.execute(delete(NodeTag))
            cleared.append(f"node_tags: {tag_result.rowcount} rows (cascade)")  # type: ignore[attr-defined]

            node_result = session.execute(delete(Node))
            cleared.append(f"nodes: {node_result.rowcount} rows")  # type: ignore[attr-defined]

    db.dispose()

    click.echo("")
    click.echo("Truncate complete. Cleared:")
    for item in cleared:
        click.echo(f"  - {item}")
    click.echo("")
