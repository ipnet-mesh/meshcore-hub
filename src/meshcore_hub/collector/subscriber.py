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

if TYPE_CHECKING:
    from meshcore_hub.collector.webhook import WebhookDispatcher

logger = logging.getLogger(__name__)


# Handler type: receives (public_key, event_type, payload, db_manager)
EventHandler = Callable[[str, str, dict[str, Any], DatabaseManager], None]


class Subscriber:
    """MQTT Subscriber for collecting and storing MeshCore events."""

    INGEST_MODE_NATIVE = "native"
    INGEST_MODE_LETSMESH_UPLOAD = "letsmesh_upload"

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
        ingest_mode: str = INGEST_MODE_NATIVE,
        letsmesh_decoder_enabled: bool = True,
        letsmesh_decoder_command: str = "meshcore-decoder",
        letsmesh_decoder_channel_keys: list[str] | None = None,
        letsmesh_decoder_timeout_seconds: float = 2.0,
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
            ingest_mode: Ingest mode ('native' or 'letsmesh_upload')
            letsmesh_decoder_enabled: Enable external LetsMesh packet decoder
            letsmesh_decoder_command: Decoder CLI command
            letsmesh_decoder_channel_keys: Optional channel keys for decrypting group text
            letsmesh_decoder_timeout_seconds: Decoder CLI timeout
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
        self._ingest_mode = ingest_mode.lower()
        if self._ingest_mode not in {
            self.INGEST_MODE_NATIVE,
            self.INGEST_MODE_LETSMESH_UPLOAD,
        }:
            raise ValueError(f"Unsupported collector ingest mode: {ingest_mode}")
        self._letsmesh_decoder = LetsMeshPacketDecoder(
            enabled=letsmesh_decoder_enabled,
            command=letsmesh_decoder_command,
            channel_keys=letsmesh_decoder_channel_keys,
            timeout_seconds=letsmesh_decoder_timeout_seconds,
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
        if self._ingest_mode == self.INGEST_MODE_LETSMESH_UPLOAD:
            parsed = self._normalize_letsmesh_event(topic, payload)
        else:
            parsed_event = self.mqtt.topic_builder.parse_event_topic(topic)
            parsed = (
                (parsed_event[0], parsed_event[1], payload) if parsed_event else None
            )

        if not parsed:
            logger.warning(
                "Could not parse topic for ingest mode %s: %s",
                self._ingest_mode,
                topic,
            )
            return

        public_key, event_type, normalized_payload = parsed
        logger.debug("Received event: %s from %s...", event_type, public_key[:12])
        self._dispatch_event(public_key, event_type, normalized_payload)

    def _normalize_letsmesh_event(
        self,
        topic: str,
        payload: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]] | None:
        """Normalize LetsMesh upload topics to collector event handlers."""
        parsed = self.mqtt.topic_builder.parse_letsmesh_upload_topic(topic)
        if not parsed:
            return None

        observer_public_key, feed_type = parsed

        if feed_type == "status":
            normalized_status = self._build_letsmesh_status_advertisement_payload(
                payload,
                observer_public_key=observer_public_key,
            )
            if normalized_status:
                return observer_public_key, "advertisement", normalized_status
            return observer_public_key, "letsmesh_status", dict(payload)

        if feed_type == "packets":
            decoded_packet = self._letsmesh_decoder.decode_payload(payload)

            normalized_message = self._build_letsmesh_message_payload(
                payload,
                decoded_packet=decoded_packet,
            )
            if normalized_message:
                event_type, message_payload = normalized_message
                return observer_public_key, event_type, message_payload

            normalized_advertisement = self._build_letsmesh_advertisement_payload(
                payload,
                decoded_packet=decoded_packet,
            )
            if normalized_advertisement:
                return observer_public_key, "advertisement", normalized_advertisement

            normalized_packet_payload = dict(payload)
            if decoded_packet:
                normalized_packet_payload["decoded_packet"] = decoded_packet
                decoded_payload_type = self._extract_letsmesh_decoder_payload_type(
                    decoded_packet
                )
                if decoded_payload_type is not None:
                    normalized_packet_payload["decoded_payload_type"] = (
                        decoded_payload_type
                    )
            return observer_public_key, "letsmesh_packet", normalized_packet_payload

        if feed_type == "internal":
            return observer_public_key, "letsmesh_internal", payload

        return None

    def _build_letsmesh_message_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        """Build a message payload from LetsMesh packet data when possible."""
        packet_type = self._resolve_letsmesh_packet_type(payload, decoded_packet)
        if packet_type == 5:
            event_type = "channel_msg_recv"
        elif packet_type in {1, 2, 7}:
            event_type = "contact_msg_recv"
        else:
            return None

        normalized_payload = dict(payload)
        packet_hash = payload.get("hash")
        packet_hash_text = packet_hash if isinstance(packet_hash, str) else None
        if decoded_packet is None:
            decoded_packet = self._letsmesh_decoder.decode_payload(payload)

        # In LetsMesh compatibility mode, only show messages that decrypt.
        text = self._extract_letsmesh_decoder_text(decoded_packet)
        if not text:
            logger.debug(
                "Skipping LetsMesh packet %s (type=%s): no decryptable text payload",
                packet_hash_text or "unknown",
                packet_type,
            )
            return None

        txt_type = self._parse_int(payload.get("txt_type"))
        if txt_type is None:
            txt_type = self._extract_letsmesh_decoder_txt_type(decoded_packet)
        normalized_payload["txt_type"] = (
            txt_type if txt_type is not None else packet_type
        )
        normalized_payload["signature"] = payload.get("signature") or packet_hash
        path_len = self._parse_path_length(payload.get("path"))
        if path_len is None:
            path_len = self._extract_letsmesh_decoder_path_length(decoded_packet)
        normalized_payload["path_len"] = path_len

        sender_timestamp = self._parse_sender_timestamp(payload)
        if sender_timestamp is None:
            sender_timestamp = self._extract_letsmesh_decoder_sender_timestamp(
                decoded_packet
            )
        if sender_timestamp is not None:
            normalized_payload["sender_timestamp"] = sender_timestamp

        snr = self._parse_float(payload.get("SNR"))
        if snr is None:
            snr = self._parse_float(payload.get("snr"))
        if snr is not None:
            normalized_payload["SNR"] = snr

        decoded_sender = self._extract_letsmesh_decoder_sender(
            decoded_packet,
            packet_type=packet_type,
        )
        sender_name = self._normalize_sender_name(decoded_sender)
        if sender_name:
            normalized_payload["sender_name"] = sender_name

        if decoded_sender and not normalized_payload.get("pubkey_prefix"):
            normalized_prefix = self._normalize_pubkey_prefix(decoded_sender)
            if normalized_prefix:
                normalized_payload["pubkey_prefix"] = normalized_prefix

        if not normalized_payload.get("pubkey_prefix"):
            fallback_sender = self._extract_letsmesh_sender_from_payload(payload)
            if fallback_sender:
                normalized_payload["pubkey_prefix"] = fallback_sender

        sender_prefix = self._normalize_pubkey_prefix(
            normalized_payload.get("pubkey_prefix")
        )
        if sender_prefix:
            normalized_payload["pubkey_prefix"] = sender_prefix
        else:
            normalized_payload.pop("pubkey_prefix", None)

        channel_idx = self._parse_int(payload.get("channel_idx"))
        channel_hash = self._extract_letsmesh_decoder_channel_hash(decoded_packet)
        if channel_idx is None and channel_hash:
            channel_idx = self._parse_channel_hash_idx(channel_hash)
        if channel_idx is not None:
            normalized_payload["channel_idx"] = channel_idx

        if event_type == "channel_msg_recv":
            channel_name = self._letsmesh_decoder.channel_name_from_decoded(
                decoded_packet
            )
            channel_label = self._format_channel_label(
                channel_name=channel_name,
                channel_hash=channel_hash,
                channel_idx=channel_idx,
            )
            if channel_label:
                normalized_payload["channel_name"] = channel_label
            normalized_payload["text"] = self._prefix_sender_name(
                text,
                normalized_payload.get("sender_name"),
            )
        else:
            normalized_payload["text"] = self._prefix_sender_name(
                text,
                normalized_payload.get("sender_name"),
            )

        return event_type, normalized_payload

    def _build_letsmesh_advertisement_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Map decoded LetsMesh packet payloads to advertisement events."""
        if decoded_packet is None:
            decoded_packet = self._letsmesh_decoder.decode_payload(payload)
        if not isinstance(decoded_packet, dict):
            return None

        decoded_payload_type = self._extract_letsmesh_decoder_payload_type(
            decoded_packet
        )
        # Primary packet forms that carry node identity/role/location metadata.
        if decoded_payload_type not in {4, 11}:
            return None

        decoded_payload = self._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded_payload:
            return None

        public_key = self._normalize_full_public_key(
            decoded_payload.get("publicKey")
            or payload.get("public_key")
            or payload.get("origin_id")
        )
        if not public_key:
            return None

        normalized_payload: dict[str, Any] = {
            "public_key": public_key,
        }

        app_data = decoded_payload.get("appData")
        if isinstance(app_data, dict):
            name = app_data.get("name")
            if isinstance(name, str) and name.strip():
                normalized_payload["name"] = name.strip()

            flags = self._parse_int(app_data.get("flags"))
            if flags is not None:
                normalized_payload["flags"] = flags

            device_role = app_data.get("deviceRole")
            role_name = self._normalize_letsmesh_node_type(device_role)
            if role_name:
                normalized_payload["adv_type"] = role_name

            location = app_data.get("location")
            if isinstance(location, dict):
                lat = self._parse_float(location.get("latitude"))
                lon = self._parse_float(location.get("longitude"))
                if lat is not None:
                    normalized_payload["lat"] = lat
                if lon is not None:
                    normalized_payload["lon"] = lon

        if "name" not in normalized_payload:
            status_name = payload.get("origin") or payload.get("name")
            if isinstance(status_name, str) and status_name.strip():
                normalized_payload["name"] = status_name.strip()

        if "flags" not in normalized_payload:
            raw_flags = self._parse_int(decoded_payload.get("rawFlags"))
            if raw_flags is not None:
                normalized_payload["flags"] = raw_flags

        if "adv_type" not in normalized_payload:
            node_type = self._normalize_letsmesh_node_type(
                decoded_payload.get("nodeType")
            )
            node_type_name = self._normalize_letsmesh_node_type(
                decoded_payload.get("nodeTypeName")
            )
            normalized_adv_type = (
                node_type
                or node_type_name
                or self._normalize_letsmesh_adv_type(normalized_payload)
            )
            if normalized_adv_type:
                normalized_payload["adv_type"] = normalized_adv_type

        return normalized_payload

    def _build_letsmesh_status_advertisement_payload(
        self,
        payload: dict[str, Any],
        observer_public_key: str,
    ) -> dict[str, Any] | None:
        """Normalize LetsMesh status feed payloads into advertisement events."""
        status_public_key = self._normalize_full_public_key(
            payload.get("origin_id") or payload.get("public_key") or observer_public_key
        )
        if not status_public_key:
            return None

        normalized_payload: dict[str, Any] = {"public_key": status_public_key}

        status_name = payload.get("origin") or payload.get("name")
        if isinstance(status_name, str) and status_name.strip():
            normalized_payload["name"] = status_name.strip()

        normalized_adv_type = self._normalize_letsmesh_adv_type(payload)
        if normalized_adv_type:
            normalized_payload["adv_type"] = normalized_adv_type

        # Only trust explicit status payload flags. stats.debug_flags are observer/debug
        # counters and cause false capability flags + inflated dedup churn.
        explicit_flags = self._parse_int(payload.get("flags"))
        if explicit_flags is not None:
            normalized_payload["flags"] = explicit_flags

        lat = self._parse_float(payload.get("lat"))
        lon = self._parse_float(payload.get("lon"))
        if lat is None:
            lat = self._parse_float(payload.get("adv_lat"))
        if lon is None:
            lon = self._parse_float(payload.get("adv_lon"))
        location = payload.get("location")
        if isinstance(location, dict):
            if lat is None:
                lat = self._parse_float(location.get("latitude"))
            if lon is None:
                lon = self._parse_float(location.get("longitude"))
        if lat is not None:
            normalized_payload["lat"] = lat
        if lon is not None:
            normalized_payload["lon"] = lon

        # Ignore status heartbeat/counter frames that have no node identity metadata.
        if not any(
            key in normalized_payload
            for key in ("name", "adv_type", "flags", "lat", "lon")
        ):
            return None
        return normalized_payload

    @classmethod
    def _extract_letsmesh_text(
        cls,
        payload: dict[str, Any],
        depth: int = 3,
    ) -> str | None:
        """Extract text from possible LetsMesh packet payload fields."""
        if depth < 0:
            return None

        for key in ("text", "message", "msg", "body", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for nested in payload.values():
            if not isinstance(nested, dict):
                continue
            text = cls._extract_letsmesh_text(nested, depth=depth - 1)
            if text:
                return text

        return None

    @classmethod
    def _extract_letsmesh_decoder_text(
        cls,
        decoded_packet: dict[str, Any] | None,
    ) -> str | None:
        """Extract human-readable text from decoder JSON output."""
        if not isinstance(decoded_packet, dict):
            return None
        payload = decoded_packet.get("payload")
        if not isinstance(payload, dict):
            return None
        return cls._extract_letsmesh_text(payload)

    @classmethod
    def _extract_letsmesh_decoder_sender_timestamp(
        cls,
        decoded_packet: dict[str, Any] | None,
    ) -> int | None:
        """Extract sender timestamp from decoder JSON output."""
        if not isinstance(decoded_packet, dict):
            return None
        payload = decoded_packet.get("payload")
        if not isinstance(payload, dict):
            return None
        decoded = payload.get("decoded")
        if not isinstance(decoded, dict):
            return None
        decrypted = decoded.get("decrypted")
        if not isinstance(decrypted, dict):
            return None
        return cls._parse_int(decrypted.get("timestamp"))

    @classmethod
    def _extract_letsmesh_decoder_sender(
        cls,
        decoded_packet: dict[str, Any] | None,
        packet_type: int | None = None,
    ) -> str | None:
        """Extract sender identifier from decoder JSON output."""
        if not isinstance(decoded_packet, dict):
            return None
        payload = decoded_packet.get("payload")
        if not isinstance(payload, dict):
            return None
        decoded = payload.get("decoded")
        if not isinstance(decoded, dict):
            return None
        decrypted = decoded.get("decrypted")
        if not isinstance(decrypted, dict):
            return None
        sender = decrypted.get("sender")
        if isinstance(sender, str) and sender.strip():
            return sender.strip()

        source_hash = decoded.get("sourceHash")
        if isinstance(source_hash, str) and source_hash.strip():
            return source_hash.strip()
        return None

    @staticmethod
    def _extract_letsmesh_decoder_payload(
        decoded_packet: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Extract decoded packet payload object."""
        if not isinstance(decoded_packet, dict):
            return None
        payload = decoded_packet.get("payload")
        if not isinstance(payload, dict):
            return None
        decoded = payload.get("decoded")
        return decoded if isinstance(decoded, dict) else None

    @classmethod
    def _extract_letsmesh_decoder_payload_type(
        cls,
        decoded_packet: dict[str, Any] | None,
    ) -> int | None:
        """Extract payload type from decoder output."""
        if not isinstance(decoded_packet, dict):
            return None
        payload_type = cls._parse_int(decoded_packet.get("payloadType"))
        if payload_type is not None:
            return payload_type
        decoded = cls._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded:
            return None
        return cls._parse_int(decoded.get("type"))

    @classmethod
    def _resolve_letsmesh_packet_type(
        cls,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> int | None:
        """Resolve packet type from source payload with decoder fallback."""
        packet_type = cls._parse_int(payload.get("packet_type"))
        if packet_type is not None:
            return packet_type
        return cls._extract_letsmesh_decoder_payload_type(decoded_packet)

    @staticmethod
    def _extract_letsmesh_sender_from_payload(payload: dict[str, Any]) -> str | None:
        """Extract sender-like identifiers from LetsMesh upload payload fields."""
        for key in (
            "pubkey_prefix",
            "sourceHash",
            "source_hash",
            "source",
            "sender",
            "from",
            "src",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @classmethod
    def _extract_letsmesh_decoder_txt_type(
        cls,
        decoded_packet: dict[str, Any] | None,
    ) -> int | None:
        """Extract txt_type equivalent from decoder output."""
        if not isinstance(decoded_packet, dict):
            return None
        return cls._parse_int(decoded_packet.get("payloadType"))

    @classmethod
    def _extract_letsmesh_decoder_path_length(
        cls,
        decoded_packet: dict[str, Any] | None,
    ) -> int | None:
        """Extract path length from decoder output."""
        if not isinstance(decoded_packet, dict):
            return None
        return cls._parse_int(decoded_packet.get("pathLength"))

    @classmethod
    def _extract_letsmesh_decoder_channel_hash(
        cls,
        decoded_packet: dict[str, Any] | None,
    ) -> str | None:
        """Extract channel hash (1-byte hex) from decoder output."""
        if not isinstance(decoded_packet, dict):
            return None
        payload = decoded_packet.get("payload")
        if not isinstance(payload, dict):
            return None
        decoded = payload.get("decoded")
        if not isinstance(decoded, dict):
            return None
        channel_hash = decoded.get("channelHash")
        if not isinstance(channel_hash, str):
            return None
        normalized = channel_hash.strip().upper()
        if len(normalized) != 2:
            return None
        if any(ch not in "0123456789ABCDEF" for ch in normalized):
            return None
        return normalized

    @staticmethod
    def _normalize_full_public_key(value: Any) -> str | None:
        """Normalize full node public key (64 hex chars)."""
        if not isinstance(value, str):
            return None
        normalized = value.strip().removeprefix("0x").removeprefix("0X").upper()
        if len(normalized) != 64:
            return None
        if any(ch not in "0123456789ABCDEF" for ch in normalized):
            return None
        return normalized

    @staticmethod
    def _normalize_pubkey_prefix(value: Any) -> str | None:
        """Normalize sender key/prefix to 12 uppercase hex characters."""
        if not isinstance(value, str):
            return None
        normalized = value.strip().removeprefix("0x").removeprefix("0X").upper()
        if not normalized:
            return None
        if any(ch not in "0123456789ABCDEF" for ch in normalized):
            return None
        if len(normalized) < 8:
            return None
        return normalized[:12]

    @staticmethod
    def _parse_channel_hash_idx(channel_hash: str) -> int | None:
        """Convert 1-byte channel hash hex string into a stable numeric index."""
        normalized = channel_hash.strip().upper()
        if len(normalized) != 2:
            return None
        if any(ch not in "0123456789ABCDEF" for ch in normalized):
            return None
        return int(normalized, 16)

    @staticmethod
    def _format_channel_label(
        channel_name: str | None,
        channel_hash: str | None,
        channel_idx: int | None,
    ) -> str | None:
        """Format a display label for channel messages."""
        if channel_name and channel_name.strip():
            cleaned = channel_name.strip()
            if cleaned.lower() == "public":
                return "Public"
            return cleaned if cleaned.startswith("#") else f"#{cleaned}"
        if channel_idx is not None:
            return f"Ch {channel_idx}"
        if channel_hash:
            return f"Ch {channel_hash.upper()}"
        return None

    @staticmethod
    def _prefix_channel_label(text: str, channel_label: str | None) -> str:
        """Prefix channel label to message text for LetsMesh channel feeds."""
        if not channel_label:
            return text
        prefix = f"[{channel_label}] "
        if text.startswith(prefix):
            return text
        return f"{prefix}{text}"

    @classmethod
    def _normalize_sender_name(cls, value: Any) -> str | None:
        """Normalize human sender names from decoder output."""
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if cls._normalize_pubkey_prefix(normalized):
            return None
        return normalized

    @staticmethod
    def _prefix_sender_name(text: str, sender_name: Any) -> str:
        """Prefix sender name when available and not already present."""
        if not isinstance(sender_name, str):
            return text
        sender = sender_name.strip()
        if not sender:
            return text
        lower_text = text.lstrip().lower()
        prefix = f"{sender}:"
        if lower_text.startswith(prefix.lower()):
            return text
        return f"{sender}: {text}"

    @staticmethod
    def _normalize_letsmesh_adv_type(payload: dict[str, Any]) -> str | None:
        """Map LetsMesh status fields to canonical node types."""
        candidates: list[str] = []
        for key in ("adv_type", "type", "node_type", "role", "mode", "status"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip().lower())

        for key in ("origin", "name", "model"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip().lower())

        if not candidates:
            return None

        normalized = " ".join(candidates)
        if any(token in normalized for token in ("room server", "roomserver", "room")):
            return "room"
        if any(token in normalized for token in ("repeater", "relay")):
            return "repeater"
        if any(token in normalized for token in ("companion", "observer")):
            return "companion"
        if "chat" in normalized:
            return "chat"

        # Preserve existing canonical values when they are already set.
        for candidate in candidates:
            if candidate in {"chat", "repeater", "room", "companion"}:
                return candidate

        return None

    @classmethod
    def _normalize_letsmesh_node_type(cls, value: Any) -> str | None:
        """Normalize LetsMesh node-type values to canonical adv_type values."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            numeric = int(value)
            if numeric == 0:
                return None
            if numeric == 1:
                return "chat"
            if numeric == 2:
                return "repeater"
            if numeric == 3:
                return "room"
            if numeric == 4:
                return "companion"
            return None

        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            return cls._normalize_letsmesh_adv_type({"type": normalized})

        return None

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        """Parse int-like values safely."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_float(value: Any) -> float | None:
        """Parse float-like values safely."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @classmethod
    def _parse_path_length(cls, value: Any) -> int | None:
        """Parse path length from list or packed hex string."""
        if value is None:
            return None
        if isinstance(value, list):
            return len(value)
        if isinstance(value, str):
            path = value.strip()
            if not path:
                return None
            return len(path) // 2 if len(path) % 2 == 0 else len(path)
        return cls._parse_int(value)

    @staticmethod
    def _parse_sender_timestamp(payload: dict[str, Any]) -> int | None:
        """Parse sender timestamp from known LetsMesh fields."""
        sender_ts = payload.get("sender_timestamp")
        if isinstance(sender_ts, (int, float)):
            return int(sender_ts)
        if isinstance(sender_ts, str):
            try:
                return int(float(sender_ts))
            except ValueError:
                return None

        return None

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

        # Subscribe to topics based on ingest mode
        if self._ingest_mode == self.INGEST_MODE_LETSMESH_UPLOAD:
            letsmesh_topics = [
                f"{self.mqtt.topic_builder.prefix}/+/packets",
                f"{self.mqtt.topic_builder.prefix}/+/status",
                f"{self.mqtt.topic_builder.prefix}/+/internal",
            ]
            for letsmesh_topic in letsmesh_topics:
                self.mqtt.subscribe(letsmesh_topic, self._handle_mqtt_message)
                logger.info(f"Subscribed to LetsMesh upload topic: {letsmesh_topic}")
        else:
            event_topic = self.mqtt.topic_builder.all_events_topic()
            self.mqtt.subscribe(event_topic, self._handle_mqtt_message)
            logger.info(f"Subscribed to event topic: {event_topic}")

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
    ingest_mode: str = "native",
    database_url: str = "sqlite:///./meshcore.db",
    webhook_dispatcher: Optional["WebhookDispatcher"] = None,
    cleanup_enabled: bool = False,
    cleanup_retention_days: int = 30,
    cleanup_interval_hours: int = 24,
    node_cleanup_enabled: bool = False,
    node_cleanup_days: int = 90,
    letsmesh_decoder_enabled: bool = True,
    letsmesh_decoder_command: str = "meshcore-decoder",
    letsmesh_decoder_channel_keys: list[str] | None = None,
    letsmesh_decoder_timeout_seconds: float = 2.0,
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
        ingest_mode: Ingest mode ('native' or 'letsmesh_upload')
        database_url: Database connection URL
        webhook_dispatcher: Optional webhook dispatcher for event forwarding
        cleanup_enabled: Enable automatic event data cleanup
        cleanup_retention_days: Number of days to retain event data
        cleanup_interval_hours: Hours between cleanup runs
        node_cleanup_enabled: Enable automatic cleanup of inactive nodes
        node_cleanup_days: Remove nodes not seen for this many days
        letsmesh_decoder_enabled: Enable external LetsMesh packet decoder
        letsmesh_decoder_command: Decoder CLI command
        letsmesh_decoder_channel_keys: Optional channel keys for decrypting group text
        letsmesh_decoder_timeout_seconds: Decoder CLI timeout

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
        ingest_mode=ingest_mode,
        letsmesh_decoder_enabled=letsmesh_decoder_enabled,
        letsmesh_decoder_command=letsmesh_decoder_command,
        letsmesh_decoder_channel_keys=letsmesh_decoder_channel_keys,
        letsmesh_decoder_timeout_seconds=letsmesh_decoder_timeout_seconds,
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
    ingest_mode: str = "native",
    database_url: str = "sqlite:///./meshcore.db",
    webhook_dispatcher: Optional["WebhookDispatcher"] = None,
    cleanup_enabled: bool = False,
    cleanup_retention_days: int = 30,
    cleanup_interval_hours: int = 24,
    node_cleanup_enabled: bool = False,
    node_cleanup_days: int = 90,
    letsmesh_decoder_enabled: bool = True,
    letsmesh_decoder_command: str = "meshcore-decoder",
    letsmesh_decoder_channel_keys: list[str] | None = None,
    letsmesh_decoder_timeout_seconds: float = 2.0,
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
        ingest_mode: Ingest mode ('native' or 'letsmesh_upload')
        database_url: Database connection URL
        webhook_dispatcher: Optional webhook dispatcher for event forwarding
        cleanup_enabled: Enable automatic event data cleanup
        cleanup_retention_days: Number of days to retain event data
        cleanup_interval_hours: Hours between cleanup runs
        node_cleanup_enabled: Enable automatic cleanup of inactive nodes
        node_cleanup_days: Remove nodes not seen for this many days
        letsmesh_decoder_enabled: Enable external LetsMesh packet decoder
        letsmesh_decoder_command: Decoder CLI command
        letsmesh_decoder_channel_keys: Optional channel keys for decrypting group text
        letsmesh_decoder_timeout_seconds: Decoder CLI timeout
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
        ingest_mode=ingest_mode,
        database_url=database_url,
        webhook_dispatcher=webhook_dispatcher,
        cleanup_enabled=cleanup_enabled,
        cleanup_retention_days=cleanup_retention_days,
        cleanup_interval_hours=cleanup_interval_hours,
        node_cleanup_enabled=node_cleanup_enabled,
        node_cleanup_days=node_cleanup_days,
        letsmesh_decoder_enabled=letsmesh_decoder_enabled,
        letsmesh_decoder_command=letsmesh_decoder_command,
        letsmesh_decoder_channel_keys=letsmesh_decoder_channel_keys,
        letsmesh_decoder_timeout_seconds=letsmesh_decoder_timeout_seconds,
    )

    # Set up signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        subscriber.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    subscriber.run()
