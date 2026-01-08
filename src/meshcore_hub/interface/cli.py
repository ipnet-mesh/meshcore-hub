"""CLI for the Interface component."""

import click

from meshcore_hub.common.logging import configure_logging


@click.group()
def interface() -> None:
    """Interface component for MeshCore device communication.

    Runs in RECEIVER or SENDER mode to bridge between
    MeshCore devices and MQTT broker.
    """
    pass


@interface.command("run")
@click.option(
    "--mode",
    type=click.Choice(["RECEIVER", "SENDER"], case_sensitive=False),
    required=True,
    envvar="INTERFACE_MODE",
    help="Interface mode: RECEIVER or SENDER",
)
@click.option(
    "--port",
    type=str,
    default="/dev/ttyUSB0",
    envvar="SERIAL_PORT",
    help="Serial port path",
)
@click.option(
    "--baud",
    type=int,
    default=115200,
    envvar="SERIAL_BAUD",
    help="Serial baud rate",
)
@click.option(
    "--mock",
    is_flag=True,
    default=False,
    envvar="MOCK_DEVICE",
    help="Use mock device for testing",
)
@click.option(
    "--node-address",
    type=str,
    default=None,
    envvar="NODE_ADDRESS",
    help="Override for device public key/address (hex string)",
)
@click.option(
    "--device-name",
    type=str,
    default=None,
    envvar="MESHCORE_DEVICE_NAME",
    help="Device/node name (optional)",
)
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
    "--contact-cleanup/--no-contact-cleanup",
    default=True,
    envvar="CONTACT_CLEANUP_ENABLED",
    help="Enable/disable automatic removal of stale contacts (RECEIVER mode only)",
)
@click.option(
    "--contact-cleanup-days",
    type=int,
    default=7,
    envvar="CONTACT_CLEANUP_DAYS",
    help="Remove contacts not advertised for this many days (RECEIVER mode only)",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="INFO",
    envvar="LOG_LEVEL",
    help="Log level",
)
def run(
    mode: str,
    port: str,
    baud: int,
    mock: bool,
    node_address: str | None,
    device_name: str | None,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    mqtt_tls: bool,
    contact_cleanup: bool,
    contact_cleanup_days: int,
    log_level: str,
) -> None:
    """Run the interface component.

    The interface bridges MeshCore devices to an MQTT broker.

    In RECEIVER mode:
    - Connects to a MeshCore device
    - Subscribes to device events
    - Publishes events to MQTT

    In SENDER mode:
    - Connects to a MeshCore device
    - Subscribes to MQTT command topics
    - Executes commands on the device
    """
    configure_logging(level=log_level)

    click.echo(f"Starting interface in {mode} mode")
    click.echo(f"Serial: {port} @ {baud} baud")
    click.echo(f"MQTT: {mqtt_host}:{mqtt_port} (prefix: {prefix})")
    click.echo(f"Mock device: {mock}")
    if node_address:
        click.echo(f"Node address: {node_address}")

    mode_upper = mode.upper()

    if mode_upper == "RECEIVER":
        from meshcore_hub.interface.receiver import run_receiver

        run_receiver(
            port=port,
            baud=baud,
            mock=mock,
            node_address=node_address,
            device_name=device_name,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_username=mqtt_username,
            mqtt_password=mqtt_password,
            mqtt_prefix=prefix,
            mqtt_tls=mqtt_tls,
            contact_cleanup_enabled=contact_cleanup,
            contact_cleanup_days=contact_cleanup_days,
        )
    elif mode_upper == "SENDER":
        from meshcore_hub.interface.sender import run_sender

        run_sender(
            port=port,
            baud=baud,
            mock=mock,
            node_address=node_address,
            device_name=device_name,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_username=mqtt_username,
            mqtt_password=mqtt_password,
            mqtt_prefix=prefix,
            mqtt_tls=mqtt_tls,
        )
    else:
        click.echo(f"Unknown mode: {mode}", err=True)
        raise click.Abort()


@interface.command("receiver")
@click.option(
    "--port",
    type=str,
    default="/dev/ttyUSB0",
    envvar="SERIAL_PORT",
    help="Serial port path",
)
@click.option(
    "--baud",
    type=int,
    default=115200,
    envvar="SERIAL_BAUD",
    help="Serial baud rate",
)
@click.option(
    "--mock",
    is_flag=True,
    default=False,
    envvar="MOCK_DEVICE",
    help="Use mock device for testing",
)
@click.option(
    "--node-address",
    type=str,
    default=None,
    envvar="NODE_ADDRESS",
    help="Override for device public key/address (hex string)",
)
@click.option(
    "--device-name",
    type=str,
    default=None,
    envvar="MESHCORE_DEVICE_NAME",
    help="Device/node name (optional)",
)
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
    "--contact-cleanup/--no-contact-cleanup",
    default=True,
    envvar="CONTACT_CLEANUP_ENABLED",
    help="Enable/disable automatic removal of stale contacts",
)
@click.option(
    "--contact-cleanup-days",
    type=int,
    default=7,
    envvar="CONTACT_CLEANUP_DAYS",
    help="Remove contacts not advertised for this many days",
)
def receiver(
    port: str,
    baud: int,
    mock: bool,
    node_address: str | None,
    device_name: str | None,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    mqtt_tls: bool,
    contact_cleanup: bool,
    contact_cleanup_days: int,
) -> None:
    """Run interface in RECEIVER mode.

    Shortcut for: meshcore-hub interface run --mode RECEIVER
    """
    from meshcore_hub.interface.receiver import run_receiver

    click.echo("Starting interface in RECEIVER mode")
    click.echo(f"Serial: {port} @ {baud} baud")
    click.echo(f"MQTT: {mqtt_host}:{mqtt_port} (prefix: {prefix})")
    click.echo(f"Mock device: {mock}")
    if node_address:
        click.echo(f"Node address: {node_address}")

    run_receiver(
        port=port,
        baud=baud,
        mock=mock,
        node_address=node_address,
        device_name=device_name,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=prefix,
        mqtt_tls=mqtt_tls,
        contact_cleanup_enabled=contact_cleanup,
        contact_cleanup_days=contact_cleanup_days,
    )


@interface.command("sender")
@click.option(
    "--port",
    type=str,
    default="/dev/ttyUSB0",
    envvar="SERIAL_PORT",
    help="Serial port path",
)
@click.option(
    "--baud",
    type=int,
    default=115200,
    envvar="SERIAL_BAUD",
    help="Serial baud rate",
)
@click.option(
    "--mock",
    is_flag=True,
    default=False,
    envvar="MOCK_DEVICE",
    help="Use mock device for testing",
)
@click.option(
    "--node-address",
    type=str,
    default=None,
    envvar="NODE_ADDRESS",
    help="Override for device public key/address (hex string)",
)
@click.option(
    "--device-name",
    type=str,
    default=None,
    envvar="MESHCORE_DEVICE_NAME",
    help="Device/node name (optional)",
)
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
def sender(
    port: str,
    baud: int,
    mock: bool,
    node_address: str | None,
    device_name: str | None,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    prefix: str,
    mqtt_tls: bool,
) -> None:
    """Run interface in SENDER mode.

    Shortcut for: meshcore-hub interface run --mode SENDER
    """
    from meshcore_hub.interface.sender import run_sender

    click.echo("Starting interface in SENDER mode")
    click.echo(f"Serial: {port} @ {baud} baud")
    click.echo(f"MQTT: {mqtt_host}:{mqtt_port} (prefix: {prefix})")
    click.echo(f"Mock device: {mock}")
    if node_address:
        click.echo(f"Node address: {node_address}")

    run_sender(
        port=port,
        baud=baud,
        mock=mock,
        node_address=node_address,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=prefix,
        mqtt_tls=mqtt_tls,
    )
