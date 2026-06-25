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
from meshcore_hub.collector.observer_filter import ObserverFilter

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
        channel_refresh_interval_seconds: int = 300,
        raw_packet_capture_enabled: bool = False,
        raw_packet_retention_days: int = 7,
        observer_filter: Optional[ObserverFilter] = None,
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
            channel_refresh_interval_seconds: Seconds between channel key refresh
            raw_packet_capture_enabled: Capture every packets-feed packet to raw_packets
            raw_packet_retention_days: Days to retain raw packets
            observer_filter: Allow/deny filter for observer-sourced events
                (defaults to an inactive filter that accepts all observers)
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
        # Raw packet capture
        self._raw_packet_capture_enabled = raw_packet_capture_enabled
        self._raw_packet_retention_days = raw_packet_retention_days
        logger.info(
            "Raw packet capture %s (retention=%d days)",
            "enabled" if raw_packet_capture_enabled else "disabled",
            raw_packet_retention_days,
        )
        # Observer ingestion filter (allow/deny by observer public key)
        self._observer_filter = observer_filter or ObserverFilter()
        if self._observer_filter.active:
            logger.info(
                "Observer filter active: %d allow, %d deny",
                len(self._observer_filter.allowlist),
                len(self._observer_filter.denylist),
            )
        # Channel key refresh
        self._channel_refresh_interval_seconds = channel_refresh_interval_seconds
        self._channel_refresh_thread: Optional[threading.Thread] = None
        # Background spam re-scoring sweep
        self._spam_rescore_thread: Optional[threading.Thread] = None
        # Load initial channel keys from database
        self._include_test_channel = self._load_channel_keys_from_db()
        self._letsmesh_decoder = LetsMeshPacketDecoder(
            channel_keys=self._db_channel_keys,
        )

    @property
    def is_healthy(self) -> bool:
        """Check if the subscriber is healthy.

        Returns:
            True if MQTT and database are connected
        """
        return self._running and self._mqtt_connected and self._db_connected

    def _load_channel_keys_from_db(self) -> bool:
        """Load channel keys from the database (synchronous).

        Queries enabled channels, merges with built-in keys, and
        determines whether the test channel should be included.

        Returns:
            True if test channel should be included (DB row exists with enabled=True).
        """
        self._db_channel_keys: list[str] = []
        include_test = False
        try:
            from meshcore_hub.common.models.channel import Channel

            with self.db.session_scope() as session:
                channels = (
                    session.query(Channel)
                    .filter(Channel.enabled == True)  # noqa: E712
                    .all()
                )
                for ch in channels:
                    self._db_channel_keys.append(f"{ch.name}={ch.key_hex}")
                    if ch.name.lower() == "test":
                        include_test = True
            logger.info(
                "Loaded %d channel keys from database (include_test=%s)",
                len(self._db_channel_keys),
                include_test,
            )
        except Exception as e:
            logger.warning("Failed to load channel keys from database: %s", e)
            self._db_channel_keys = []
        return include_test

    def _refresh_channel_keys_from_db(self) -> None:
        """Refresh channel keys from the database and reload the decoder."""
        new_keys: list[str] = []
        include_test = False
        try:
            from meshcore_hub.common.models.channel import Channel

            with self.db.session_scope() as session:
                channels = (
                    session.query(Channel)
                    .filter(Channel.enabled == True)  # noqa: E712
                    .all()
                )
                for ch in channels:
                    new_keys.append(f"{ch.name}={ch.key_hex}")
                    if ch.name.lower() == "test":
                        include_test = True
            self._db_channel_keys = new_keys
            self._include_test_channel = include_test
            self._letsmesh_decoder.reload_keys(new_keys)
            logger.info(
                "Refreshed %d channel keys from database (include_test=%s)",
                len(new_keys),
                include_test,
            )
        except Exception as e:
            logger.error("Failed to refresh channel keys from database: %s", e)

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
        # Apply the observer allow/deny filter first, before any decode,
        # raw-packet capture, or handler dispatch. Blocked observers' packets
        # are dropped entirely and never touch the database. The cheap topic
        # split below runs only when the filter is active, so the default
        # (accept-all) path is unaffected.
        if self._observer_filter.active:
            parsed_topic = self.mqtt.topic_builder.parse_letsmesh_upload_topic(topic)
            if parsed_topic:
                observer_key, _feed = parsed_topic
                if not self._observer_filter.is_allowed(observer_key):
                    logger.debug(
                        "Dropping event from blocked observer %s...",
                        observer_key[:12],
                    )
                    return

        parsed: tuple[str, str, dict[str, Any]] | None
        parsed = self._normalize_letsmesh_event(topic, payload)

        if not parsed:
            logger.warning("Could not parse topic: %s", topic)
            return

        public_key, event_type, normalized_payload = parsed
        logger.debug("Received event: %s from %s...", event_type, public_key[:12])

        # Capture the raw packet (packets feed only) independent of, and before,
        # structured dispatch so the raw_packets table is complete. The boolean
        # short-circuit avoids the insert entirely when capture is disabled.
        if self._raw_packet_capture_enabled:
            self._maybe_capture_raw_packet(topic, public_key, event_type, payload)

        self._dispatch_event(public_key, event_type, normalized_payload)

    def _maybe_capture_raw_packet(
        self,
        topic: str,
        public_key: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Persist a raw_packets row for a packets-feed reception.

        Reuses the decode the normalizer already performed (the decoder caches
        per raw hex, so this ``decode_payload`` call is a cache hit). Capture
        failures are logged and never block event dispatch.
        """
        try:
            parsed_topic = self.mqtt.topic_builder.parse_letsmesh_upload_topic(topic)
            if not parsed_topic:
                return
            _, feed_type = parsed_topic
            if feed_type != "packets":
                return

            from meshcore_hub.collector.handlers.raw_packet import store_raw_packet

            decoded_packet = self._letsmesh_decoder.decode_payload(payload)
            store_raw_packet(public_key, payload, decoded_packet, event_type, self.db)
        except Exception as e:
            logger.error("Error capturing raw packet: %s", e)

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
                                cleanup_orphaned_node_relations,
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
                                            raw_packet_retention_days=(
                                                self._raw_packet_retention_days
                                            ),
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

                                        orphan_counts = (
                                            await cleanup_orphaned_node_relations(
                                                session,
                                                dry_run=False,
                                            )
                                        )
                                        if any(orphan_counts.values()):
                                            logger.info(
                                                "Orphan cleanup completed: %s",
                                                orphan_counts,
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

    def _start_channel_refresh_scheduler(self) -> None:
        """Start background thread for periodic channel key refresh."""
        interval = self._channel_refresh_interval_seconds
        if interval <= 0:
            logger.info("Channel key refresh is disabled (interval=0)")
            return

        logger.info("Starting channel refresh scheduler (interval=%ds)", interval)

        def run_refresh_loop() -> None:
            """Periodically refresh channel keys from database."""
            while self._running:
                for _ in range(interval):
                    if not self._running:
                        break
                    time.sleep(1)
                if self._running:
                    try:
                        self._refresh_channel_keys_from_db()
                    except Exception as e:
                        logger.error("Channel refresh error: %s", e, exc_info=True)

        self._channel_refresh_thread = threading.Thread(
            target=run_refresh_loop, daemon=True, name="channel-refresh"
        )
        self._channel_refresh_thread.start()

    def _stop_channel_refresh_scheduler(self) -> None:
        """Stop the channel refresh scheduler thread."""
        if self._channel_refresh_thread and self._channel_refresh_thread.is_alive():
            self._channel_refresh_thread.join(timeout=5.0)
            if self._channel_refresh_thread.is_alive():
                logger.warning("Channel refresh thread did not stop cleanly")

    def _start_spam_rescore_scheduler(self) -> None:
        """Start background thread that re-scores recent messages with hindsight.

        Disabled (not scheduled at all) when spam detection is off or the
        interval is 0. Follows the same loop template as the channel-refresh
        scheduler and uses synchronous sessions.
        """
        from meshcore_hub.collector.spam import get_spam_config

        cfg = get_spam_config()
        if not cfg.enabled or cfg.rescore_interval_seconds <= 0:
            logger.info(
                "Spam re-scoring sweep disabled (enabled=%s, interval=%ds)",
                cfg.enabled,
                cfg.rescore_interval_seconds,
            )
            return

        interval = cfg.rescore_interval_seconds
        logger.info("Starting spam re-scoring sweep (interval=%ds)", interval)

        def run_rescore_loop() -> None:
            """Periodically re-score recent messages with symmetric-window counts."""
            from meshcore_hub.collector.spam import get_spam_config, rescore_recent

            while self._running:
                for _ in range(interval):
                    if not self._running:
                        break
                    time.sleep(1)
                if self._running:
                    try:
                        sweep_cfg = get_spam_config()
                        with self.db.session_scope() as session:
                            updated = rescore_recent(session, sweep_cfg)
                        if updated:
                            logger.info(
                                "Spam re-scoring sweep updated %d rows", updated
                            )
                    except Exception as e:
                        logger.error("Spam re-scoring error: %s", e, exc_info=True)

        self._spam_rescore_thread = threading.Thread(
            target=run_rescore_loop, daemon=True, name="spam-rescore"
        )
        self._spam_rescore_thread.start()

    def _stop_spam_rescore_scheduler(self) -> None:
        """Stop the spam re-scoring sweep thread."""
        if self._spam_rescore_thread and self._spam_rescore_thread.is_alive():
            self._spam_rescore_thread.join(timeout=5.0)
            if self._spam_rescore_thread.is_alive():
                logger.warning("Spam re-scoring thread did not stop cleanly")

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

        # Connect to MQTT broker with retry
        max_retries = 10
        retry_delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                self.mqtt.connect()
                self.mqtt.start_background()
                self._mqtt_connected = True
                logger.info("Connected to MQTT broker")
                break
            except Exception as e:
                self._mqtt_connected = False
                if attempt < max_retries:
                    logger.warning(
                        "MQTT connection attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt,
                        max_retries,
                        e,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30.0)
                else:
                    logger.error(
                        "Failed to connect to MQTT broker after %d attempts: %s",
                        max_retries,
                        e,
                    )
                    raise

        # Subscribe to LetsMesh upload topics
        letsmesh_topics = [
            f"{self.mqtt.topic_builder.prefix}/+/+/packets",
            f"{self.mqtt.topic_builder.prefix}/+/+/status",
            f"{self.mqtt.topic_builder.prefix}/+/+/internal",
        ]
        for letsmesh_topic in letsmesh_topics:
            self.mqtt.subscribe(letsmesh_topic, self._handle_mqtt_message)
            logger.info(f"Subscribed to LetsMesh upload topic: {letsmesh_topic}")

        self._running = True

        # Start webhook processor if configured
        self._start_webhook_processor()

        # Start cleanup scheduler if configured
        self._start_cleanup_scheduler()

        # Start channel key refresh scheduler
        self._start_channel_refresh_scheduler()

        # Start background spam re-scoring sweep (no-op when disabled)
        self._start_spam_rescore_scheduler()

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

        # Stop channel refresh scheduler
        self._stop_channel_refresh_scheduler()

        # Stop spam re-scoring sweep
        self._stop_spam_rescore_scheduler()

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
    mqtt_transport: str = "websockets",
    mqtt_ws_path: str = "/",
    database_url: str = "sqlite:///./meshcore.db",
    webhook_dispatcher: Optional["WebhookDispatcher"] = None,
    cleanup_enabled: bool = False,
    cleanup_retention_days: int = 30,
    cleanup_interval_hours: int = 24,
    node_cleanup_enabled: bool = False,
    node_cleanup_days: int = 90,
    channel_refresh_interval_seconds: int = 300,
    raw_packet_capture_enabled: bool = False,
    raw_packet_retention_days: int = 7,
    observer_filter: Optional[ObserverFilter] = None,
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
        channel_refresh_interval_seconds: Seconds between channel key refresh

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
        channel_refresh_interval_seconds=channel_refresh_interval_seconds,
        raw_packet_capture_enabled=raw_packet_capture_enabled,
        raw_packet_retention_days=raw_packet_retention_days,
        observer_filter=observer_filter,
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
    mqtt_transport: str = "websockets",
    mqtt_ws_path: str = "/",
    database_url: str = "sqlite:///./meshcore.db",
    webhook_dispatcher: Optional["WebhookDispatcher"] = None,
    cleanup_enabled: bool = False,
    cleanup_retention_days: int = 30,
    cleanup_interval_hours: int = 24,
    node_cleanup_enabled: bool = False,
    node_cleanup_days: int = 90,
    channel_refresh_interval_seconds: int = 300,
    raw_packet_capture_enabled: bool = False,
    raw_packet_retention_days: int = 7,
    observer_filter: Optional[ObserverFilter] = None,
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
        channel_refresh_interval_seconds: Seconds between channel key refresh
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
        channel_refresh_interval_seconds=channel_refresh_interval_seconds,
        raw_packet_capture_enabled=raw_packet_capture_enabled,
        raw_packet_retention_days=raw_packet_retention_days,
        observer_filter=observer_filter,
    )

    # Set up signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        subscriber.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    subscriber.run()
