"""RECEIVER mode implementation for MeshCore Interface.

In RECEIVER mode, the interface:
1. Connects to a MeshCore device
2. Subscribes to all device events
3. Publishes events to MQTT broker
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
    EventType,
    create_device,
)

logger = logging.getLogger(__name__)


class Receiver:
    """RECEIVER mode implementation.

    Bridges MeshCore device events to MQTT broker.
    """

    def __init__(
        self,
        device: BaseMeshCoreDevice,
        mqtt_client: MQTTClient,
    ):
        """Initialize receiver.

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
        """Check if the receiver is healthy.

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

    def _initialize_device(self) -> None:
        """Initialize device after connection.

        Sets the hardware clock, sends a local advertisement, and starts message fetching.
        """
        # Set device time to current Unix timestamp
        current_time = int(time.time())
        if self.device.set_time(current_time):
            logger.info(f"Synchronized device clock to {current_time}")
        else:
            logger.warning("Failed to synchronize device clock")

        # Send a local (non-flood) advertisement to announce presence
        if self.device.send_advertisement(flood=False):
            logger.info("Sent local advertisement")
        else:
            logger.warning("Failed to send local advertisement")

        # Start automatic message fetching
        if self.device.start_message_fetching():
            logger.info("Started automatic message fetching")
        else:
            logger.warning("Failed to start automatic message fetching")

    def _handle_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Handle device event and publish to MQTT.

        Args:
            event_type: Event type
            payload: Event payload
        """
        if not self.device.public_key:
            logger.warning("Cannot publish event: device public key not available")
            return

        try:
            # Convert event type to MQTT topic name
            event_name = event_type.value

            # Publish to MQTT
            self.mqtt.publish_event(
                self.device.public_key,
                event_name,
                payload,
            )

            logger.debug(f"Published {event_name} event to MQTT")

        except Exception as e:
            logger.error(f"Failed to publish event to MQTT: {e}")

    def start(self) -> None:
        """Start the receiver."""
        logger.info("Starting RECEIVER mode")

        # Register event handlers for all event types
        for event_type in EventType:
            self.device.register_handler(event_type, self._handle_event)
            logger.debug(f"Registered handler for {event_type.value}")

        # Connect to MQTT broker
        try:
            self.mqtt.connect()
            self.mqtt.start_background()
            self._mqtt_connected = True
            logger.info("Connected to MQTT broker")
        except Exception as e:
            self._mqtt_connected = False
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

        # Connect to device
        if not self.device.connect():
            self._device_connected = False
            logger.error("Failed to connect to MeshCore device")
            self.mqtt.stop()
            self.mqtt.disconnect()
            self._mqtt_connected = False
            raise RuntimeError("Failed to connect to MeshCore device")

        self._device_connected = True
        logger.info(f"Connected to MeshCore device: {self.device.public_key}")

        # Initialize device: set time and send local advertisement
        self._initialize_device()

        self._running = True

        # Start health reporter for Docker health checks
        self._health_reporter = HealthReporter(
            component="interface",
            status_fn=self.get_health_status,
            interval=10.0,
        )
        self._health_reporter.start()

    def run(self) -> None:
        """Run the receiver event loop (blocking)."""
        if not self._running:
            self.start()

        logger.info("Receiver running. Press Ctrl+C to stop.")

        try:
            # Run device event loop
            self.device.run()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the receiver."""
        if not self._running:
            return

        logger.info("Stopping receiver")
        self._running = False
        self._shutdown_event.set()

        # Stop health reporter
        if self._health_reporter:
            self._health_reporter.stop()
            self._health_reporter = None

        # Stop device
        self.device.stop()
        self.device.disconnect()
        self._device_connected = False

        # Stop MQTT
        self.mqtt.stop()
        self.mqtt.disconnect()
        self._mqtt_connected = False

        logger.info("Receiver stopped")


def create_receiver(
    port: str = "/dev/ttyUSB0",
    baud: int = 115200,
    mock: bool = False,
    node_address: Optional[str] = None,
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    mqtt_username: Optional[str] = None,
    mqtt_password: Optional[str] = None,
    mqtt_prefix: str = "meshcore",
) -> Receiver:
    """Create a configured receiver instance.

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
        Configured Receiver instance
    """
    # Create device
    device = create_device(port=port, baud=baud, mock=mock, node_address=node_address)

    # Create MQTT client
    mqtt_config = MQTTConfig(
        host=mqtt_host,
        port=mqtt_port,
        username=mqtt_username,
        password=mqtt_password,
        prefix=mqtt_prefix,
        client_id=f"meshcore-receiver-{device.public_key[:8] if device.public_key else 'unknown'}",
    )
    mqtt_client = MQTTClient(mqtt_config)

    return Receiver(device, mqtt_client)


def run_receiver(
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
    """Run the receiver (blocking).

    This is the main entry point for running the receiver component.

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
    receiver = create_receiver(
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
        receiver.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    receiver.run()
