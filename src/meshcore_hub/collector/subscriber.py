"""MQTT Subscriber for collecting MeshCore events.

The subscriber:
1. Connects to MQTT broker
2. Subscribes to all event topics
3. Routes events to appropriate handlers
4. Persists data to database
5. Dispatches events to configured webhooks
6. Performs scheduled data cleanup if enabled
"""

import asyncio
import logging
import signal
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TYPE_CHECKING

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.health import HealthReporter
from meshcore_hub.common.mqtt import MQTTClient, MQTTConfig
from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder
from meshcore_hub.collector.letsmesh_normalizer import LetsMeshNormalizer

if TYPE_CHECKING:
    from meshcore_hub.collector.webhook import WebhookDispatcher

logger = logging.getLogger(__name__)


# Handler type: receives (public_key, event_type, payload, db_manager)
EventHandler = Callable[[str, str, dict[str, Any], DatabaseManager], None]


class Subscriber(LetsMeshNormalizer):
    """MQTT Subscriber for collecting and storing MeshCore events."""

    def __init__(
        self,
        mqtt_client: MQTTClient,
        db_manager: DatabaseManager,
        webhook_dispatcher: Optional["WebhookDispatcher"] = None,
        cleanup_enabled: bool = False,
        cleanup_retention_days: int = 30,
        cleanup_interval_hours: int = 24,
        node_cleanup_enabled: bool = False,
        node_cleanup_days: int = 90,
        letsmesh_decoder_channel_keys: list[str] | None = None,
    ):
        """Initialize subscriber.

        Args:
            mqtt_client: MQTT client instance
            db_manager: Database manager instance
            webhook_dispatcher: Optional webhook dispatcher for event forwarding
            cleanup_enabled: Enable automatic event data cleanup
            cleanup_retention_days: Number of days to retain event data
            cleanup_interval_hours: Hours between cleanup runs
            node_cleanup_enabled: Enable automatic cleanup of inactive nodes
            node_cleanup_days: Remove nodes not seen for this many days
            letsmesh_decoder_channel_keys: Optional channel keys for decrypting group text
        """
        self.mqtt = mqtt_client
        self.db = db_manager
        self._webhook_dispatcher = webhook_dispatcher
        self._running = False
        self._shutdown_event = threading.Event()
        self._handlers: dict[str, EventHandler] = {}
        self._mqtt_connected = False
        self._db_connected = False
        self._health_reporter: Optional[HealthReporter] = None
        # Webhook processing
        self._webhook_queue: list[tuple[str, dict[str, Any], str]] = []
        self._webhook_lock = threading.Lock()
        self._webhook_thread: Optional[threading.Thread] = None
        # Data cleanup
        self._cleanup_enabled = cleanup_enabled
        self._cleanup_retention_days = cleanup_retention_days
        self._cleanup_interval_hours = cleanup_interval_hours
        self._node_cleanup_enabled = node_cleanup_enabled
        self._node_cleanup_days = node_cleanup_days
        self._cleanup_thread: Optional[threading.Thread] = None
        self._last_cleanup: Optional[datetime] = None
        self._letsmesh_decoder = LetsMeshPacketDecoder(
            channel_keys=letsmesh_decoder_channel_keys,
        )

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
        parsed: tuple[str, str, dict[str, Any]] | None
        parsed = self._normalize_letsmesh_event(topic, payload)

        if not parsed:
            logger.warning("Could not parse topic: %s", topic)
            return

        public_key, event_type, normalized_payload = parsed
        logger.debug("Received event: %s from %s...", event_type, public_key[:12])
        self._dispatch_event(public_key, event_type, normalized_payload)

    def _dispatch_event(
        self,
        public_key: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Route a normalized event to the appropriate handler."""

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

        # Queue event for webhook dispatch
        if self._webhook_dispatcher and self._webhook_dispatcher.webhooks:
            self._queue_webhook_event(event_type, payload, public_key)

    def _queue_webhook_event(
        self, event_type: str, payload: dict[str, Any], public_key: str
    ) -> None:
        """Queue an event for webhook dispatch.

        Args:
            event_type: Event type name
            payload: Event payload
            public_key: Source node public key
        """
        with self._webhook_lock:
            self._webhook_queue.append((event_type, payload, public_key))

    def _start_webhook_processor(self) -> None:
        """Start background thread for webhook processing."""
        if not self._webhook_dispatcher or not self._webhook_dispatcher.webhooks:
            return

        # Capture dispatcher in local variable for closure (avoids Optional issues)
        dispatcher = self._webhook_dispatcher

        def run_webhook_loop() -> None:
            """Run async webhook dispatch in background thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                loop.run_until_complete(dispatcher.start())
                logger.info("Webhook processor started")

                while self._running:
                    # Get queued events
                    events_to_process: list[tuple[str, dict[str, Any], str]] = []
                    with self._webhook_lock:
                        if self._webhook_queue:
                            events_to_process = self._webhook_queue.copy()
                            self._webhook_queue.clear()

                    # Process events
                    for event_type, payload, public_key in events_to_process:
                        try:
                            loop.run_until_complete(
                                dispatcher.dispatch(event_type, payload, public_key)
                            )
                        except Exception as e:
                            logger.error(f"Webhook dispatch error: {e}")

                    # Small sleep to prevent busy-waiting
                    time.sleep(0.01)

            finally:
                loop.run_until_complete(dispatcher.stop())
                loop.close()
                logger.info("Webhook processor stopped")

        self._webhook_thread = threading.Thread(
            target=run_webhook_loop, daemon=True, name="webhook-processor"
        )
        self._webhook_thread.start()

    def _stop_webhook_processor(self) -> None:
        """Stop the webhook processor thread."""
        if self._webhook_thread and self._webhook_thread.is_alive():
            # Thread will exit when self._running becomes False
            self._webhook_thread.join(timeout=5.0)
            if self._webhook_thread.is_alive():
                logger.warning("Webhook processor thread did not stop cleanly")

    def _start_cleanup_scheduler(self) -> None:
        """Start background thread for periodic data cleanup."""
        if not self._cleanup_enabled and not self._node_cleanup_enabled:
            logger.info("Data cleanup and node cleanup are both disabled")
            return

        logger.info(
            "Starting cleanup scheduler (interval_hours=%d)",
            self._cleanup_interval_hours,
        )
        if self._cleanup_enabled:
            logger.info(
                "  Event data cleanup: ENABLED (retention_days=%d)",
                self._cleanup_retention_days,
            )
        else:
            logger.info("  Event data cleanup: DISABLED")

        if self._node_cleanup_enabled:
            logger.info(
                "  Node cleanup: ENABLED (inactivity_days=%d)", self._node_cleanup_days
            )
        else:
            logger.info("  Node cleanup: DISABLED")

        def run_cleanup_loop() -> None:
            """Run async cleanup tasks in background thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                while self._running:
                    # Check if cleanup is due
                    now = datetime.now(timezone.utc)
                    should_run = False

                    if self._last_cleanup is None:
                        # First run
                        should_run = True
                    else:
                        # Check if interval has passed
                        hours_since_last = (
                            now - self._last_cleanup
                        ).total_seconds() / 3600
                        should_run = hours_since_last >= self._cleanup_interval_hours

                    if should_run:
                        try:
                            logger.info("Starting scheduled cleanup")
                            from meshcore_hub.collector.cleanup import (
                                cleanup_old_data,
                                cleanup_inactive_nodes,
                            )

                            # Get async session and run cleanup
                            async def run_cleanup() -> None:
                                async with self.db.async_session() as session:
                                    # Run event data cleanup if enabled
                                    if self._cleanup_enabled:
                                        stats = await cleanup_old_data(
                                            session,
                                            self._cleanup_retention_days,
                                            dry_run=False,
                                        )
                                        logger.info(
                                            "Event cleanup completed: %s", stats
                                        )

                                    # Run node cleanup if enabled
                                    if self._node_cleanup_enabled:
                                        nodes_deleted = await cleanup_inactive_nodes(
                                            session,
                                            self._node_cleanup_days,
                                            dry_run=False,
                                        )
                                        logger.info(
                                            "Node cleanup completed: %d nodes deleted",
                                            nodes_deleted,
                                        )

                            loop.run_until_complete(run_cleanup())
                            self._last_cleanup = now

                        except Exception as e:
                            logger.error(f"Cleanup error: {e}", exc_info=True)

                    # Sleep for 1 hour before next check
                    for _ in range(3600):
                        if not self._running:
                            break
                        time.sleep(1)

            finally:
                loop.close()
                logger.info("Cleanup scheduler stopped")

        self._cleanup_thread = threading.Thread(
            target=run_cleanup_loop, daemon=True, name="cleanup-scheduler"
        )
        self._cleanup_thread.start()

    def _stop_cleanup_scheduler(self) -> None:
        """Stop the cleanup scheduler thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            # Thread will exit when self._running becomes False
            self._cleanup_thread.join(timeout=5.0)
            if self._cleanup_thread.is_alive():
                logger.warning("Cleanup scheduler thread did not stop cleanly")

    def start(self) -> None:
        """Start the subscriber."""
        logger.info("Starting collector subscriber")

        # Verify database connection (schema managed by Alembic migrations)
        try:
            # Test connection by getting a session
            session = self.db.get_session()
            session.close()
            self._db_connected = True
            logger.info("Database connection verified")
        except Exception as e:
            self._db_connected = False
            logger.error(f"Failed to connect to database: {e}")
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

        # Subscribe to LetsMesh upload topics
        letsmesh_topics = [
            f"{self.mqtt.topic_builder.prefix}/+/packets",
            f"{self.mqtt.topic_builder.prefix}/+/status",
            f"{self.mqtt.topic_builder.prefix}/+/internal",
        ]
        for letsmesh_topic in letsmesh_topics:
            self.mqtt.subscribe(letsmesh_topic, self._handle_mqtt_message)
            logger.info(f"Subscribed to LetsMesh upload topic: {letsmesh_topic}")

        self._running = True

        # Start webhook processor if configured
        self._start_webhook_processor()

        # Start cleanup scheduler if configured
        self._start_cleanup_scheduler()

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

        # Stop cleanup scheduler
        self._stop_cleanup_scheduler()

        # Stop webhook processor
        self._stop_webhook_processor()

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
    mqtt_tls: bool = False,
    mqtt_transport: str = "tcp",
    mqtt_ws_path: str = "/mqtt",
    database_url: str = "sqlite:///./meshcore.db",
    webhook_dispatcher: Optional["WebhookDispatcher"] = None,
    cleanup_enabled: bool = False,
    cleanup_retention_days: int = 30,
    cleanup_interval_hours: int = 24,
    node_cleanup_enabled: bool = False,
    node_cleanup_days: int = 90,
    letsmesh_decoder_channel_keys: list[str] | None = None,
) -> Subscriber:
    """Create a configured subscriber instance.

    Args:
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix
        mqtt_tls: Enable TLS/SSL for MQTT connection
        mqtt_transport: MQTT transport protocol (tcp or websockets)
        mqtt_ws_path: WebSocket path (used when transport=websockets)
        database_url: Database connection URL
        webhook_dispatcher: Optional webhook dispatcher for event forwarding
        cleanup_enabled: Enable automatic event data cleanup
        cleanup_retention_days: Number of days to retain event data
        cleanup_interval_hours: Hours between cleanup runs
        node_cleanup_enabled: Enable automatic cleanup of inactive nodes
        node_cleanup_days: Remove nodes not seen for this many days
        letsmesh_decoder_channel_keys: Optional channel keys for decrypting group text

    Returns:
        Configured Subscriber instance
    """
    # Create MQTT client with unique client ID to allow multiple collectors
    unique_id = uuid.uuid4().hex[:8]
    mqtt_config = MQTTConfig(
        host=mqtt_host,
        port=mqtt_port,
        username=mqtt_username,
        password=mqtt_password,
        prefix=mqtt_prefix,
        client_id=f"meshcore-collector-{unique_id}",
        tls=mqtt_tls,
        transport=mqtt_transport,
        ws_path=mqtt_ws_path,
    )
    mqtt_client = MQTTClient(mqtt_config)

    # Create database manager
    db_manager = DatabaseManager(database_url)

    # Create subscriber
    subscriber = Subscriber(
        mqtt_client,
        db_manager,
        webhook_dispatcher,
        cleanup_enabled=cleanup_enabled,
        cleanup_retention_days=cleanup_retention_days,
        cleanup_interval_hours=cleanup_interval_hours,
        node_cleanup_enabled=node_cleanup_enabled,
        node_cleanup_days=node_cleanup_days,
        letsmesh_decoder_channel_keys=letsmesh_decoder_channel_keys,
    )

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
    mqtt_tls: bool = False,
    mqtt_transport: str = "tcp",
    mqtt_ws_path: str = "/mqtt",
    database_url: str = "sqlite:///./meshcore.db",
    webhook_dispatcher: Optional["WebhookDispatcher"] = None,
    cleanup_enabled: bool = False,
    cleanup_retention_days: int = 30,
    cleanup_interval_hours: int = 24,
    node_cleanup_enabled: bool = False,
    node_cleanup_days: int = 90,
    letsmesh_decoder_channel_keys: list[str] | None = None,
) -> None:
    """Run the collector (blocking).

    Args:
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_username: MQTT username
        mqtt_password: MQTT password
        mqtt_prefix: MQTT topic prefix
        mqtt_tls: Enable TLS/SSL for MQTT connection
        mqtt_transport: MQTT transport protocol (tcp or websockets)
        mqtt_ws_path: WebSocket path (used when transport=websockets)
        database_url: Database connection URL
        webhook_dispatcher: Optional webhook dispatcher for event forwarding
        cleanup_enabled: Enable automatic event data cleanup
        cleanup_retention_days: Number of days to retain event data
        cleanup_interval_hours: Hours between cleanup runs
        node_cleanup_enabled: Enable automatic cleanup of inactive nodes
        node_cleanup_days: Remove nodes not seen for this many days
        letsmesh_decoder_channel_keys: Optional channel keys for decrypting group text
    """
    subscriber = create_subscriber(
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_prefix=mqtt_prefix,
        mqtt_tls=mqtt_tls,
        mqtt_transport=mqtt_transport,
        mqtt_ws_path=mqtt_ws_path,
        database_url=database_url,
        webhook_dispatcher=webhook_dispatcher,
        cleanup_enabled=cleanup_enabled,
        cleanup_retention_days=cleanup_retention_days,
        cleanup_interval_hours=cleanup_interval_hours,
        node_cleanup_enabled=node_cleanup_enabled,
        node_cleanup_days=node_cleanup_days,
        letsmesh_decoder_channel_keys=letsmesh_decoder_channel_keys,
    )

    # Set up signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        subscriber.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    subscriber.run()
