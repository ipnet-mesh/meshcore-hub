"""MQTT client utilities for MeshCore Hub."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger(__name__)


@dataclass
class MQTTConfig:
    """MQTT connection configuration."""

    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    prefix: str = "meshcore"
    client_id: Optional[str] = None
    keepalive: int = 60
    clean_session: bool = True
    tls: bool = False


class TopicBuilder:
    """Helper class for building MQTT topics."""

    def __init__(self, prefix: str = "meshcore"):
        """Initialize topic builder.

        Args:
            prefix: MQTT topic prefix
        """
        self.prefix = prefix

    def event_topic(self, public_key: str, event_name: str) -> str:
        """Build an event topic.

        Args:
            public_key: Node's public key
            event_name: Event name

        Returns:
            Full MQTT topic string
        """
        return f"{self.prefix}/{public_key}/event/{event_name}"

    def command_topic(self, public_key: str, command_name: str) -> str:
        """Build a command topic.

        Args:
            public_key: Node's public key (or '+' for wildcard)
            command_name: Command name

        Returns:
            Full MQTT topic string
        """
        return f"{self.prefix}/{public_key}/command/{command_name}"

    def all_events_topic(self) -> str:
        """Build a topic pattern to subscribe to all events.

        Returns:
            MQTT topic pattern with wildcards
        """
        return f"{self.prefix}/+/event/#"

    def all_commands_topic(self) -> str:
        """Build a topic pattern to subscribe to all commands.

        Returns:
            MQTT topic pattern with wildcards
        """
        return f"{self.prefix}/+/command/#"

    def parse_event_topic(self, topic: str) -> tuple[str, str] | None:
        """Parse an event topic to extract public key and event name.

        Args:
            topic: Full MQTT topic string

        Returns:
            Tuple of (public_key, event_name) or None if invalid
        """
        parts = topic.split("/")
        if len(parts) >= 4 and parts[0] == self.prefix and parts[2] == "event":
            public_key = parts[1]
            event_name = "/".join(parts[3:])
            return (public_key, event_name)
        return None

    def parse_command_topic(self, topic: str) -> tuple[str, str] | None:
        """Parse a command topic to extract public key and command name.

        Args:
            topic: Full MQTT topic string

        Returns:
            Tuple of (public_key, command_name) or None if invalid
        """
        parts = topic.split("/")
        if len(parts) >= 4 and parts[0] == self.prefix and parts[2] == "command":
            public_key = parts[1]
            command_name = "/".join(parts[3:])
            return (public_key, command_name)
        return None


MessageHandler = Callable[[str, str, dict[str, Any]], None]


class MQTTClient:
    """Wrapper for paho-mqtt client with helper methods."""

    def __init__(self, config: MQTTConfig):
        """Initialize MQTT client.

        Args:
            config: MQTT configuration
        """
        self.config = config
        self.topic_builder = TopicBuilder(config.prefix)
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,  # type: ignore[call-arg]
            client_id=config.client_id,
            clean_session=config.clean_session,
        )
        self._connected = False
        self._message_handlers: dict[str, list[MessageHandler]] = {}

        # Set up TLS if enabled
        if config.tls:
            self._client.tls_set()
            logger.debug("TLS/SSL enabled for MQTT connection")

        # Set up authentication if provided
        if config.username:
            self._client.username_pw_set(config.username, config.password)

        # Set up callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        """Handle connection callback."""
        if reason_code == 0:
            self._connected = True
            logger.info(
                f"Connected to MQTT broker at {self.config.host}:{self.config.port}"
            )
            # Resubscribe to topics on reconnect
            for topic in self._message_handlers.keys():
                self._client.subscribe(topic)
                logger.debug(f"Resubscribed to topic: {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {reason_code}")

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        """Handle disconnection callback."""
        self._connected = False
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming message callback."""
        topic = message.topic
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to decode message payload: {e}")
            return

        logger.debug(f"Received message on topic {topic}: {payload}")

        # Call registered handlers
        for pattern, handlers in self._message_handlers.items():
            if self._topic_matches(pattern, topic):
                for handler in handlers:
                    try:
                        handler(topic, pattern, payload)
                    except Exception as e:
                        logger.error(f"Error in message handler: {e}")

    def _topic_matches(self, pattern: str, topic: str) -> bool:
        """Check if a topic matches a subscription pattern.

        Args:
            pattern: MQTT subscription pattern (may contain + and #)
            topic: Actual topic string

        Returns:
            True if topic matches pattern
        """
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")

        for _i, (p, t) in enumerate(zip(pattern_parts, topic_parts)):
            if p == "#":
                return True
            if p != "+" and p != t:
                return False

        return len(pattern_parts) == len(topic_parts) or (
            len(pattern_parts) > 0 and pattern_parts[-1] == "#"
        )

    def connect(self) -> None:
        """Connect to the MQTT broker."""
        logger.info(
            f"Connecting to MQTT broker at {self.config.host}:{self.config.port}"
        )
        self._client.connect(
            self.config.host,
            self.config.port,
            self.config.keepalive,
        )

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        self._client.disconnect()

    def start(self) -> None:
        """Start the MQTT client loop (blocking)."""
        self._client.loop_forever()

    def start_background(self) -> None:
        """Start the MQTT client loop in background thread."""
        self._client.loop_start()

    def stop(self) -> None:
        """Stop the MQTT client loop."""
        self._client.loop_stop()

    def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        qos: int = 1,
    ) -> None:
        """Subscribe to a topic with a handler.

        Args:
            topic: MQTT topic pattern
            handler: Message handler function
            qos: Quality of service level
        """
        if topic not in self._message_handlers:
            self._message_handlers[topic] = []
            if self._connected:
                self._client.subscribe(topic, qos)
                logger.debug(f"Subscribed to topic: {topic}")

        self._message_handlers[topic].append(handler)

    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic.

        Args:
            topic: MQTT topic pattern
        """
        if topic in self._message_handlers:
            del self._message_handlers[topic]
            self._client.unsubscribe(topic)
            logger.debug(f"Unsubscribed from topic: {topic}")

    def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        """Publish a message to a topic.

        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON encoded)
            qos: Quality of service level
            retain: Whether to retain the message
        """
        message = json.dumps(payload)
        self._client.publish(topic, message, qos=qos, retain=retain)
        logger.debug(f"Published message to topic {topic}: {payload}")

    def publish_event(
        self,
        public_key: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        """Publish an event message.

        Args:
            public_key: Node's public key
            event_name: Event name
            payload: Event payload
        """
        topic = self.topic_builder.event_topic(public_key, event_name)
        self.publish(topic, payload)

    def publish_command(
        self,
        public_key: str,
        command_name: str,
        payload: dict[str, Any],
    ) -> None:
        """Publish a command message.

        Args:
            public_key: Target node's public key (or '+' for all)
            command_name: Command name
            payload: Command payload
        """
        topic = self.topic_builder.command_topic(public_key, command_name)
        self.publish(topic, payload)

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to broker."""
        return self._connected


def create_mqtt_client(
    host: str = "localhost",
    port: int = 1883,
    username: Optional[str] = None,
    password: Optional[str] = None,
    prefix: str = "meshcore",
    client_id: Optional[str] = None,
    tls: bool = False,
) -> MQTTClient:
    """Create and configure an MQTT client.

    Args:
        host: MQTT broker host
        port: MQTT broker port
        username: MQTT username (optional)
        password: MQTT password (optional)
        prefix: Topic prefix
        client_id: Client identifier (optional)
        tls: Enable TLS/SSL connection (optional)

    Returns:
        Configured MQTTClient instance
    """
    config = MQTTConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        prefix=prefix,
        client_id=client_id,
        tls=tls,
    )
    return MQTTClient(config)
