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
    "--database-url",
    type=str,
    default="sqlite:///./meshcore.db",
    envvar="DATABASE_URL",
    help="Database connection URL",
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
    database_url: str,
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
    ctx.ensure_object(dict)
    ctx.obj["mqtt_host"] = mqtt_host
    ctx.obj["mqtt_port"] = mqtt_port
    ctx.obj["mqtt_username"] = mqtt_username
    ctx.obj["mqtt_password"] = mqtt_password
    ctx.obj["prefix"] = prefix
    ctx.obj["database_url"] = database_url
    ctx.obj["log_level"] = log_level

    # If no subcommand, run the collector service
    if ctx.invoked_subcommand is None:
        _run_collector_service(
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_username=mqtt_username,
            mqtt_password=mqtt_password,
            prefix=prefix,
            database_url=database_url,
            log_level=log_level,
        )


def _run_collector_service(
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    database_url: str,
    log_level: str,
) -> None:
    """Run the collector service.

    Webhooks can be configured via environment variables:
    - WEBHOOK_ADVERTISEMENT_URL: Webhook for advertisement events
    - WEBHOOK_MESSAGE_URL: Webhook for all message events
    - WEBHOOK_CHANNEL_MESSAGE_URL: Override for channel messages
    - WEBHOOK_DIRECT_MESSAGE_URL: Override for direct messages
    """
    configure_logging(level=log_level)

    click.echo("Starting MeshCore Collector")
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
    )


@collector.command("import-tags")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--no-create-nodes",
    is_flag=True,
    default=False,
    help="Skip tags for nodes that don't exist (default: create nodes)",
)
@click.pass_context
def import_tags_cmd(
    ctx: click.Context,
    file: str,
    no_create_nodes: bool,
) -> None:
    """Import node tags from a JSON file.

    Reads a JSON file containing tag definitions and upserts them
    into the database. Existing tags are updated, new tags are created.

    FILE is the path to the JSON file containing tags.

    Expected JSON format:
    \b
    {
      "tags": [
        {
          "public_key": "64-char-hex-string",
          "key": "tag-name",
          "value": "tag-value",
          "value_type": "string"
        }
      ]
    }

    Supported value_type: string, number, boolean, coordinate
    """
    configure_logging(level=ctx.obj["log_level"])

    click.echo(f"Importing tags from: {file}")
    click.echo(f"Database: {ctx.obj['database_url']}")

    from meshcore_hub.common.database import DatabaseManager
    from meshcore_hub.collector.tag_import import import_tags

    # Initialize database
    db = DatabaseManager(ctx.obj["database_url"])
    db.create_tables()

    # Import tags
    stats = import_tags(
        file_path=file,
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
