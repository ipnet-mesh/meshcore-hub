"""MQTT Subscriber for collecting MeshCore events.

The subscriber:
1. Connects to MQTT broker
2. Subscribes to all event topics
3. Routes events to appropriate handlers
4. Persists data to database
"""

import logging
import signal
import threading
import time
from typing import Any, Callable, Optional

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.health import HealthReporter
from meshcore_hub.common.mqtt import MQTTClient, MQTTConfig

logger = logging.getLogger(__name__)


# Handler type: receives (public_key, event_type, payload, db_manager)
EventHandler = Callable[[str, str, dict[str, Any], DatabaseManager], None]


class Subscriber:
    """MQTT Subscriber for collecting and storing MeshCore events."""

    def __init__(
        self,
        mqtt_client: MQTTClient,
        db_manager: DatabaseManager,
    ):
        """Initialize subscriber.

        Args:
            mqtt_client: MQTT client instance
            db_manager: Database manager instance
        """
        self.mqtt = mqtt_client
        self.db = db_manager
        self._running = False
        self._shutdown_event = threading.Event()
        self._handlers: dict[str, EventHandler] = {}
        self._mqtt_connected = False
        self._db_connected = False
        self._health_reporter: Optional[HealthReporter] = None

    @property
    def is_healthy(self) -> bool:
        """Check if the subscriber is healthy.

        Returns:
            True if MQTT and database are connected
        """
        return self._running and self._mqtt_connected and self._db_connected

    def get_health_status(self) -> dict[str, Any]:
        """Get detailed health status.

        Returns:
            Dictionary with health status details
        """
        return {
            "healthy": self.is_healthy,
            "running": self._running,
            "mqtt_connected": self._mqtt_connected,
            "database_connected": self._db_connected,
        }

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type.

        Args:
            event_type: Event type name (e.g., 'advertisement')
            handler: Handler function
        """
        self._handlers[event_type] = handler
        logger.debug(f"Registered handler for {event_type}")

    def _handle_mqtt_message(
        self,
        topic: str,
        pattern: str,
        payload: dict[str, Any],
    ) -> None:
        """Handle incoming MQTT event message.

        Args:
            topic: MQTT topic
            pattern: Subscription pattern
            payload: Message payload
        """
        # Parse event from topic
        parsed = self.mqtt.topic_builder.parse_event_topic(topic)
        if not parsed:
            logger.warning(f"Could not parse event topic: {topic}")
            return

        public_key, event_type = parsed
        logger.debug(f"Received event: {event_type} from {public_key[:12]}...")

        # Find and call handler
        handler = self._handlers.get(event_type)
        if handler:
            try:
                handler(public_key, event_type, payload, self.db)
            except Exception as e:
                logger.error(f"Error handling {event_type}: {e}")
        else:
            # Use generic event log handler if no specific handler
            from meshcore_hub.collector.handlers.event_log import handle_event_log

            try:
                handle_event_log(public_key, event_type, payload, self.db)
            except Exception as e:
                logger.error(f"Error logging event {event_type}: {e}")

    def start(self) -> None:
        """Start the subscriber."""
        logger.info("Starting collector subscriber")

        # Create database tables if needed
        try:
            self.db.create_tables()
            self._db_connected = True
            logger.info("Database initialized")
        except Exception as e:
            self._db_connected = False
            logger.error(f"Failed to initialize database: {e}")
            raise

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

        # Subscribe to all event topics
        event_topic = self.mqtt.topic_builder.all_events_topic()
        self.mqtt.subscribe(event_topic, self._handle_mqtt_message)
        logger.info(f"Subscribed to event topic: {event_topic}")

        self._running = True

        # Start health reporter for Docker health checks
        self._health_reporter = HealthReporter(
            component="collector",
            status_fn=self.get_health_status,
            interval=10.0,
        )
        self._health_reporter.start()

    def run(self) -> None:
        """Run the subscriber event loop (blocking)."""
        if not self._running:
            self.start()

        logger.info("Collector running. Press Ctrl+C to stop.")

        try:
            while self._running and not self._shutdown_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the subscriber."""
        if not self._running:
            return

        logger.info("Stopping collector subscriber")
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

        logger.info("Collector subscriber stopped")


def create_subscriber(
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    mqtt_username: Optional[str] = None,
    mqtt_password: Optional[str] = None,
    mqtt_prefix: str = "meshcore",
    database_url: str = "sqlite:///./meshcore.db",
) -> Subscriber:
    """Create a configured subscriber instance.

    Args:
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix
        database_url: Database connection URL

    Returns:
        Configured Subscriber instance
    """
    # Create MQTT client
    mqtt_config = MQTTConfig(
        host=mqtt_host,
        port=mqtt_port,
        username=mqtt_username,
        password=mqtt_password,
        prefix=mqtt_prefix,
        client_id="meshcore-collector",
    )
    mqtt_client = MQTTClient(mqtt_config)

    # Create database manager
    db_manager = DatabaseManager(database_url)

    # Create subscriber
    subscriber = Subscriber(mqtt_client, db_manager)

    # Register handlers
    from meshcore_hub.collector.handlers import register_all_handlers

    register_all_handlers(subscriber)

    return subscriber


def run_collector(
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    mqtt_username: Optional[str] = None,
    mqtt_password: Optional[str] = None,
    mqtt_prefix: str = "meshcore",
    database_url: str = "sqlite:///./meshcore.db",
) -> None:
    """Run the collector (blocking).

    Args:
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix
        database_url: Database connection URL
    """
    subscriber = create_subscriber(
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=mqtt_prefix,
        database_url=database_url,
    )

    # Set up signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        subscriber.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    subscriber.run()
