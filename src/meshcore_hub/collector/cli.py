"""CLI for the Collector component."""

import click

from meshcore_hub.common.logging import configure_logging


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
            database_url=effective_db_url,
            log_level=log_level,
            data_home=data_home or settings.data_home,
        )


def _run_collector_service(
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    database_url: str,
    log_level: str,
    data_home: str,
) -> None:
    """Run the collector service.

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
    click.echo(f"MQTT: {mqtt_host}:{mqtt_port} (prefix: {prefix})")
    click.echo(f"Database: {database_url}")

    # Load webhook configuration from settings
    from meshcore_hub.common.config import get_collector_settings
    from meshcore_hub.collector.webhook import (
        WebhookDispatcher,
        create_webhooks_from_settings,
    )

    settings = get_collector_settings()
    webhooks = create_webhooks_from_settings(settings)
    webhook_dispatcher = WebhookDispatcher(webhooks) if webhooks else None

    if webhook_dispatcher and webhook_dispatcher.webhooks:
        click.echo(f"Webhooks configured: {len(webhooks)}")
        for wh in webhooks:
            click.echo(f"  - {wh.name}: {wh.url}")
    else:
        click.echo("Webhooks: None configured")

    from meshcore_hub.collector.subscriber import run_collector

    run_collector(
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=prefix,
        database_url=database_url,
        webhook_dispatcher=webhook_dispatcher,
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
        database_url=ctx.obj["database_url"],
        log_level=ctx.obj["log_level"],
        data_home=ctx.obj["data_home"],
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
    - node_tags.json: Node tag definitions (keyed by public_key)
    - members.json: Network member definitions

    Files that don't exist are skipped. This command is idempotent -
    existing records are updated, new records are created.

    SEED_HOME defaults to {DATA_HOME}/collector but can be overridden
    with the --seed-home option or SEED_HOME environment variable.
    """
    from pathlib import Path

    configure_logging(level=ctx.obj["log_level"])

    seed_home = ctx.obj["seed_home"]
    click.echo(f"Seed home: {seed_home}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.tag_import import import_tags
    from meshcore_hub.collector.member_import import import_members

    # Initialize database
    db = DatabaseManager(ctx.obj["database_url"])
    db.create_tables()

    # Track what was imported
    imported_any = False

    # Import node tags if file exists
    node_tags_file = Path(seed_home) / "node_tags.json"
    if node_tags_file.exists():
        click.echo(f"\nImporting node tags from: {node_tags_file}")
        stats = import_tags(
            file_path=str(node_tags_file),
            db=db,
            create_nodes=not no_create_nodes,
        )
        click.echo(f"  Tags: {stats['created']} created, {stats['updated']} updated")
        if stats["nodes_created"]:
            click.echo(f"  Nodes created: {stats['nodes_created']}")
        if stats["errors"]:
            for error in stats["errors"]:
                click.echo(f"  Error: {error}", err=True)
        imported_any = True
    else:
        click.echo(f"\nNo node_tags.json found in {seed_home}")

    # Import members if file exists
    members_file = Path(seed_home) / "members.json"
    if members_file.exists():
        click.echo(f"\nImporting members from: {members_file}")
        stats = import_members(
            file_path=str(members_file),
            db=db,
        )
        click.echo(f"  Members: {stats['created']} created, {stats['updated']} updated")
        if stats["errors"]:
            for error in stats["errors"]:
                click.echo(f"  Error: {error}", err=True)
        imported_any = True
    else:
        click.echo(f"\nNo members.json found in {seed_home}")

    if not imported_any:
        click.echo("\nNo seed files found. Nothing to import.")
    else:
        click.echo("\nSeed import complete.")

    db.dispose()


@collector.command("import-tags")
@click.argument("file", type=click.Path(), required=False, default=None)
@click.option(
    "--no-create-nodes",
    is_flag=True,
    default=False,
    help="Skip tags for nodes that don't exist (default: create nodes)",
)
@click.pass_context
def import_tags_cmd(
    ctx: click.Context,
    file: str | None,
    no_create_nodes: bool,
) -> None:
    """Import node tags from a JSON file.

    Reads a JSON file containing tag definitions and upserts them
    into the database. Existing tags are updated, new tags are created.

    FILE is the path to the JSON file containing tags.
    If not provided, defaults to {SEED_HOME}/node_tags.json.

    Expected JSON format (keyed by public_key):
    \b
    {
      "0123456789abcdef...": {
        "friendly_name": "My Node",
        "location": {"value": "52.0,1.0", "type": "coordinate"},
        "altitude": {"value": "150", "type": "number"}
      }
    }

    Shorthand is also supported (string values with default type):
    \b
    {
      "0123456789abcdef...": {
        "friendly_name": "My Node",
        "role": "gateway"
      }
    }

    Supported types: string, number, boolean, coordinate
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
            click.echo("Specify a file path or create the default node_tags.json.")
        return

    click.echo(f"Importing tags from: {tags_file}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.tag_import import import_tags

    # Initialize database
    db = DatabaseManager(ctx.obj["database_url"])
    db.create_tables()

    # Import tags
    stats = import_tags(
        file_path=tags_file,
        db=db,
        create_nodes=not no_create_nodes,
    )

    # Report results
    click.echo("")
    click.echo("Import complete:")
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
    """Import network members from a JSON file.

    Reads a JSON file containing member definitions and upserts them
    into the database. Existing members (matched by name) are updated,
    new members are created.

    FILE is the path to the JSON file containing members.
    If not provided, defaults to {SEED_HOME}/members.json.

    Expected JSON format (list):
    \b
    [
      {
        "name": "John Doe",
        "callsign": "N0CALL",
        "role": "Network Operator",
        "description": "Example member"
      }
    ]

    Or with "members" key:
    \b
    {
      "members": [
        {"name": "John Doe", "callsign": "N0CALL", ...}
      ]
    }
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
            click.echo("Specify a file path or create the default members.json.")
        return

    click.echo(f"Importing members from: {members_file}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.member_import import import_members

    # Initialize database
    db = DatabaseManager(ctx.obj["database_url"])
    db.create_tables()

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
