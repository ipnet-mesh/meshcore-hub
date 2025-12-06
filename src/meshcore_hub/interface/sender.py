"""SENDER mode implementation for MeshCore Interface.

In SENDER mode, the interface:
1. Connects to a MeshCore device
2. Subscribes to command topics on MQTT broker
3. Executes received commands on the device
"""

import logging
import signal
import threading
import time
from typing import Any, Optional

from meshcore_hub.common.health import HealthReporter
from meshcore_hub.common.mqtt import MQTTClient, MQTTConfig
from meshcore_hub.interface.device import (
    BaseMeshCoreDevice,
    create_device,
)

logger = logging.getLogger(__name__)


class Sender:
    """SENDER mode implementation.

    Bridges MQTT commands to MeshCore device.
    """

    def __init__(
        self,
        device: BaseMeshCoreDevice,
        mqtt_client: MQTTClient,
    ):
        """Initialize sender.

        Args:
            device: MeshCore device instance
            mqtt_client: MQTT client instance
        """
        self.device = device
        self.mqtt = mqtt_client
        self._running = False
        self._shutdown_event = threading.Event()
        self._device_connected = False
        self._mqtt_connected = False
        self._health_reporter: Optional[HealthReporter] = None

    @property
    def is_healthy(self) -> bool:
        """Check if the sender is healthy.

        Returns:
            True if device and MQTT are connected
        """
        return self._running and self._device_connected and self._mqtt_connected

    def get_health_status(self) -> dict[str, Any]:
        """Get detailed health status.

        Returns:
            Dictionary with health status details
        """
        return {
            "healthy": self.is_healthy,
            "running": self._running,
            "device_connected": self._device_connected,
            "mqtt_connected": self._mqtt_connected,
            "device_public_key": self.device.public_key,
        }

    def _handle_mqtt_message(
        self,
        topic: str,
        pattern: str,
        payload: dict[str, Any],
    ) -> None:
        """Handle incoming MQTT command message.

        Args:
            topic: MQTT topic
            pattern: Subscription pattern
            payload: Message payload
        """
        # Parse command from topic
        parsed = self.mqtt.topic_builder.parse_command_topic(topic)
        if not parsed:
            logger.warning(f"Could not parse command topic: {topic}")
            return

        target_key, command_name = parsed
        logger.info(f"Received command: {command_name} for {target_key[:12]}...")

        # Dispatch command
        try:
            if command_name == "send_msg":
                self._handle_send_msg(payload)
            elif command_name == "send_channel_msg":
                self._handle_send_channel_msg(payload)
            elif command_name == "send_advert":
                self._handle_send_advert(payload)
            elif command_name == "request_status":
                self._handle_request_status(payload)
            elif command_name == "request_telemetry":
                self._handle_request_telemetry(payload)
            else:
                logger.warning(f"Unknown command: {command_name}")

        except Exception as e:
            logger.error(f"Error handling command {command_name}: {e}")

    def _handle_send_msg(self, payload: dict[str, Any]) -> None:
        """Handle send_msg command.

        Args:
            payload: Command payload with destination, text, timestamp
        """
        destination = payload.get("destination")
        text = payload.get("text")
        timestamp = payload.get("timestamp")

        if not destination or not text:
            logger.error("send_msg: missing destination or text")
            return

        success = self.device.send_message(destination, text, timestamp)
        if success:
            logger.info(f"Message sent to {destination[:12]}...")
        else:
            logger.error(f"Failed to send message to {destination[:12]}...")

    def _handle_send_channel_msg(self, payload: dict[str, Any]) -> None:
        """Handle send_channel_msg command.

        Args:
            payload: Command payload with channel_idx, text, timestamp
        """
        channel_idx = payload.get("channel_idx")
        text = payload.get("text")
        timestamp = payload.get("timestamp")

        if channel_idx is None or not text:
            logger.error("send_channel_msg: missing channel_idx or text")
            return

        success = self.device.send_channel_message(channel_idx, text, timestamp)
        if success:
            logger.info(f"Channel message sent to channel {channel_idx}")
        else:
            logger.error(f"Failed to send message to channel {channel_idx}")

    def _handle_send_advert(self, payload: dict[str, Any]) -> None:
        """Handle send_advert command.

        Args:
            payload: Command payload with flood flag
        """
        flood = payload.get("flood", True)

        success = self.device.send_advertisement(flood)
        if success:
            logger.info(f"Advertisement sent (flood={flood})")
        else:
            logger.error("Failed to send advertisement")

    def _handle_request_status(self, payload: dict[str, Any]) -> None:
        """Handle request_status command.

        Args:
            payload: Command payload with optional target
        """
        target = payload.get("target_public_key")

        success = self.device.request_status(target)
        if success:
            logger.info(f"Status requested from {target or 'self'}")
        else:
            logger.error("Failed to request status")

    def _handle_request_telemetry(self, payload: dict[str, Any]) -> None:
        """Handle request_telemetry command.

        Args:
            payload: Command payload with target
        """
        target = payload.get("target_public_key")

        if not target:
            logger.error("request_telemetry: missing target_public_key")
            return

        success = self.device.request_telemetry(target)
        if success:
            logger.info(f"Telemetry requested from {target[:12]}...")
        else:
            logger.error("Failed to request telemetry")

    def start(self) -> None:
        """Start the sender."""
        logger.info("Starting SENDER mode")

        # Device should already be connected (from create_sender)
        # but handle case where start() is called directly
        if not self.device.is_connected:
            if not self.device.connect():
                self._device_connected = False
                logger.error("Failed to connect to MeshCore device")
                raise RuntimeError("Failed to connect to MeshCore device")
            logger.info(f"Connected to MeshCore device: {self.device.public_key}")

        self._device_connected = True

        # Connect to MQTT broker
        try:
            self.mqtt.connect()
            self.mqtt.start_background()
            self._mqtt_connected = True
            logger.info("Connected to MQTT broker")
        except Exception as e:
            self._mqtt_connected = False
            logger.error(f"Failed to connect to MQTT broker: {e}")
            self.device.disconnect()
            self._device_connected = False
            raise

        # Subscribe to command topics
        # Using wildcard to receive commands for any node
        command_topic = self.mqtt.topic_builder.all_commands_topic()
        self.mqtt.subscribe(command_topic, self._handle_mqtt_message)
        logger.info(f"Subscribed to command topic: {command_topic}")

        self._running = True

        # Start health reporter for Docker health checks
        self._health_reporter = HealthReporter(
            component="interface",
            status_fn=self.get_health_status,
            interval=10.0,
        )
        self._health_reporter.start()

    def run(self) -> None:
        """Run the sender event loop (blocking)."""
        if not self._running:
            self.start()

        logger.info("Sender running. Press Ctrl+C to stop.")

        try:
            while self._running and not self._shutdown_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the sender."""
        if not self._running:
            return

        logger.info("Stopping sender")
        self._running = False
        self._shutdown_event.set()

        # Stop health reporter
        if self._health_reporter:
            self._health_reporter.stop()
            self._health_reporter = None

        # Stop MQTT
        self.mqtt.stop()
        self.mqtt.disconnect()
        self._mqtt_connected = False

        # Stop device
        self.device.stop()
        self.device.disconnect()
        self._device_connected = False

        logger.info("Sender stopped")


def create_sender(
    port: str = "/dev/ttyUSB0",
    baud: int = 115200,
    mock: bool = False,
    node_address: Optional[str] = None,
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    mqtt_username: Optional[str] = None,
    mqtt_password: Optional[str] = None,
    mqtt_prefix: str = "meshcore",
) -> Sender:
    """Create a configured sender instance.

    Args:
        port: Serial port path
        baud: Baud rate
        mock: Use mock device
        node_address: Optional override for device public key/address
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix

    Returns:
        Configured Sender instance
    """
    # Create and connect device first to get public key
    device = create_device(port=port, baud=baud, mock=mock, node_address=node_address)

    if not device.connect():
        raise RuntimeError("Failed to connect to MeshCore device")

    logger.info(f"Connected to MeshCore device: {device.public_key}")

    # Create MQTT client with device's public key for unique client ID
    mqtt_config = MQTTConfig(
        host=mqtt_host,
        port=mqtt_port,
        username=mqtt_username,
        password=mqtt_password,
        prefix=mqtt_prefix,
        client_id=f"meshcore-sender-{device.public_key[:12] if device.public_key else 'unknown'}",
    )
    mqtt_client = MQTTClient(mqtt_config)

    return Sender(device, mqtt_client)


def run_sender(
    port: str = "/dev/ttyUSB0",
    baud: int = 115200,
    mock: bool = False,
    node_address: Optional[str] = None,
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    mqtt_username: Optional[str] = None,
    mqtt_password: Optional[str] = None,
    mqtt_prefix: str = "meshcore",
) -> None:
    """Run the sender (blocking).

    This is the main entry point for running the sender component.

    Args:
        port: Serial port path
        baud: Baud rate
        mock: Use mock device
        node_address: Optional override for device public key/address
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix
    """
    sender = create_sender(
        port=port,
        baud=baud,
        mock=mock,
        node_address=node_address,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=mqtt_prefix,
    )

    # Set up signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        sender.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    sender.run()
