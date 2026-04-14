"""LetsMesh upload topic normalization helpers for collector subscriber."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder

logger = logging.getLogger(__name__)


class LetsMeshNormalizer:
    """Normalize LetsMesh upload topics/payloads into collector event payloads."""

    # Attributes are provided by Subscriber at runtime.
    mqtt: Any
    _letsmesh_decoder: LetsMeshPacketDecoder
    _include_test_channel: bool

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
            # Keep status feed telemetry as informational event logs only.
            # This preserves parity with native mode where advertisements are
            # sourced from advertisement event traffic, not observer status frames.
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

            normalized_structured_event = self._build_letsmesh_structured_event_payload(
                payload,
                decoded_packet=decoded_packet,
            )
            if normalized_structured_event:
                event_type, structured_payload = normalized_structured_event
                return observer_public_key, event_type, structured_payload

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

        # Filter test channel messages when not explicitly included.
        if packet_type == 5 and not self._include_test_channel:
            channel_hash = self._extract_letsmesh_decoder_channel_hash(decoded_packet)
            if (
                channel_hash
                and channel_hash.upper() == LetsMeshPacketDecoder.TEST_CHANNEL_HASH
            ):
                logger.debug(
                    "Skipping LetsMesh packet %s (type=%s): test channel excluded",
                    packet_hash_text or "unknown",
                    packet_type,
                )
                return None

        # In LetsMesh compatibility mode, only show messages that decrypt.
        text = self._extract_letsmesh_decoder_text(decoded_packet)
        if not text:
            channel_hash = self._extract_letsmesh_decoder_channel_hash(decoded_packet)
            logger.debug(
                "Skipping LetsMesh packet %s (type=%s): no decryptable text payload "
                "(channel_hash=%s, decoded_keys=%s)",
                packet_hash_text or "unknown",
                packet_type,
                channel_hash or "N/A",
                (
                    list(decoded_packet.keys())
                    if isinstance(decoded_packet, dict)
                    else "N/A"
                ),
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

    def _build_letsmesh_structured_event_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        """Map LetsMesh packet payloads to native collector event types."""
        packet_type = self._resolve_letsmesh_packet_type(payload, decoded_packet)
        if packet_type is None:
            return None

        if packet_type == 9:
            trace_payload = self._build_letsmesh_trace_payload(payload, decoded_packet)
            if trace_payload:
                return "trace_data", trace_payload
            return None

        if packet_type == 11:
            contact_payload = self._build_letsmesh_contact_payload(
                payload,
                decoded_packet,
            )
            if contact_payload:
                return "contact", contact_payload
            status_payload = self._build_letsmesh_status_payload(
                payload, decoded_packet
            )
            if status_payload:
                return "status_response", status_payload
            return None

        if packet_type == 8:
            path_payload = self._build_letsmesh_path_updated_payload(
                payload,
                decoded_packet,
            )
            if path_payload:
                return "path_updated", path_payload
            return None

        if packet_type == 1:
            return self._build_letsmesh_response_payload(payload, decoded_packet)

        return None

    def _build_letsmesh_trace_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Build native `trace_data` payload from LetsMesh trace packets."""
        decoded_payload = self._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded_payload:
            return None

        trace_tag = (
            decoded_payload.get("traceTag")
            or payload.get("traceTag")
            or payload.get("trace_tag")
        )
        initiator_tag = self._parse_hex_or_int(trace_tag)
        if initiator_tag is None:
            return None

        path_hashes = self._normalize_hash_list(decoded_payload.get("pathHashes"))
        snr_values = self._normalize_float_list(decoded_payload.get("snrValues"))
        path_len = self._parse_path_length(payload.get("path"))
        if path_len is None:
            path_len = self._parse_int(decoded_payload.get("pathLength"))
        if path_len is None and path_hashes:
            path_len = len(path_hashes)

        hop_count: int | None = None
        if path_hashes:
            hop_count = len(path_hashes)
        elif snr_values:
            hop_count = len(snr_values)
        elif path_len is not None:
            hop_count = path_len

        normalized_payload: dict[str, Any] = {
            "initiator_tag": initiator_tag,
        }
        flags = self._parse_int(decoded_payload.get("flags"))
        auth = self._parse_int(decoded_payload.get("authCode"))
        if auth is None:
            auth = self._parse_int(decoded_payload.get("auth"))
        if path_len is not None:
            normalized_payload["path_len"] = path_len
        if flags is not None:
            normalized_payload["flags"] = flags
        if auth is not None:
            normalized_payload["auth"] = auth
        if path_hashes:
            normalized_payload["path_hashes"] = path_hashes
        if snr_values:
            normalized_payload["snr_values"] = snr_values
        if hop_count is not None:
            normalized_payload["hop_count"] = hop_count

        return normalized_payload

    def _build_letsmesh_contact_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Build native `contact` payload from LetsMesh control discovery responses."""
        decoded_payload = self._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded_payload:
            return None

        sub_type = self._parse_int(decoded_payload.get("subType"))
        # 0x90 (144): Node discover response with identity metadata.
        if sub_type is not None and sub_type != 144:
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

        node_type_raw = self._parse_int(decoded_payload.get("nodeType"))
        node_type = self._normalize_letsmesh_node_type(
            decoded_payload.get("nodeType") or decoded_payload.get("nodeTypeName")
        )
        if node_type_raw in {0, 1, 2, 3}:
            normalized_payload["type"] = node_type_raw
        elif node_type:
            normalized_payload["node_type"] = node_type

        flags = self._parse_int(decoded_payload.get("rawFlags"))
        if flags is not None:
            normalized_payload["flags"] = flags

        display_name = payload.get("origin") or payload.get("name")
        if isinstance(display_name, str) and display_name.strip():
            normalized_payload["adv_name"] = display_name.strip()

        return normalized_payload

    def _build_letsmesh_status_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Build informational `status_response` payload from control packets."""
        decoded_payload = self._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded_payload:
            return None

        status_payload: dict[str, Any] = {}
        node_public_key = self._normalize_full_public_key(
            decoded_payload.get("publicKey")
            or payload.get("public_key")
            or payload.get("origin_id")
        )
        if node_public_key:
            status_payload["node_public_key"] = node_public_key

        sub_type = self._parse_int(decoded_payload.get("subType"))
        if sub_type is not None:
            status_payload["status"] = f"control_subtype_{sub_type}"
            status_payload["control_subtype"] = sub_type

        tag = self._parse_int(decoded_payload.get("tag"))
        if tag is not None:
            status_payload["tag"] = tag

        snr = self._parse_float(decoded_payload.get("snr"))
        if snr is not None:
            status_payload["snr"] = snr

        if "status" not in status_payload and "node_public_key" not in status_payload:
            return None
        return status_payload

    def _build_letsmesh_path_updated_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Build informational `path_updated` payload from LetsMesh path packets."""
        decoded_payload = self._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded_payload:
            return None

        path_hashes = self._normalize_hash_list(decoded_payload.get("pathHashes"))
        hop_count = None
        if path_hashes:
            hop_count = len(path_hashes)
        else:
            hop_count = self._parse_int(decoded_payload.get("pathLength"))

        if hop_count is None:
            return None

        normalized_payload: dict[str, Any] = {
            "hop_count": hop_count,
        }
        if path_hashes:
            normalized_payload["path_hashes"] = path_hashes

        extra_type = self._parse_int(decoded_payload.get("extraType"))
        if extra_type is not None:
            normalized_payload["extra_type"] = extra_type

        extra_data = decoded_payload.get("extraData")
        if isinstance(extra_data, str) and extra_data.strip():
            clean_extra_data = extra_data.strip().upper()
            normalized_payload["extra_data"] = clean_extra_data
            extracted_public_key = self._extract_public_key_from_hex(clean_extra_data)
            if extracted_public_key:
                normalized_payload["node_public_key"] = extracted_public_key

        node_public_key = self._normalize_full_public_key(
            payload.get("public_key") or payload.get("origin_id")
        )
        if node_public_key and "node_public_key" not in normalized_payload:
            normalized_payload["node_public_key"] = node_public_key

        return normalized_payload

    def _build_letsmesh_response_payload(
        self,
        payload: dict[str, Any],
        decoded_packet: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        """Build native events from decrypted response payloads when possible."""
        decoded_payload = self._extract_letsmesh_decoder_payload(decoded_packet)
        if not decoded_payload:
            return None

        decrypted = decoded_payload.get("decrypted")
        if not isinstance(decrypted, dict):
            return None

        content_data = self._extract_response_content_data(decrypted.get("content"))
        if not content_data:
            return None

        node_public_key = self._normalize_full_public_key(
            content_data.get("node_public_key")
            or content_data.get("public_key")
            or content_data.get("nodePublicKey")
            or payload.get("public_key")
            or payload.get("origin_id")
        )

        battery_voltage = self._parse_float(
            content_data.get("battery_voltage") or content_data.get("batteryVoltage")
        )
        battery_percentage = self._parse_int(
            content_data.get("battery_percentage")
            or content_data.get("batteryPercentage")
        )
        if battery_voltage is not None and battery_percentage is not None:
            return "battery", {
                "battery_voltage": battery_voltage,
                "battery_percentage": battery_percentage,
            }

        telemetry_data = content_data.get("parsed_data")
        if not isinstance(telemetry_data, dict):
            telemetry_data = content_data.get("parsedData")
        if not isinstance(telemetry_data, dict):
            telemetry_data = {
                key: value
                for key, value in content_data.items()
                if key
                not in {
                    "node_public_key",
                    "public_key",
                    "nodePublicKey",
                    "lpp_data",
                    "lppData",
                }
            }
            if not telemetry_data:
                telemetry_data = None

        if node_public_key and telemetry_data:
            telemetry_payload: dict[str, Any] = {
                "node_public_key": node_public_key,
                "parsed_data": telemetry_data,
            }
            lpp_data = content_data.get("lpp_data") or content_data.get("lppData")
            if isinstance(lpp_data, str) and lpp_data.strip():
                telemetry_payload["lpp_data"] = lpp_data.strip()
            return "telemetry_response", telemetry_payload

        if node_public_key:
            hop_count = self._parse_int(content_data.get("hop_count"))
            if hop_count is None:
                hop_count = self._parse_int(content_data.get("hopCount"))
            if hop_count is not None:
                return "path_updated", {
                    "node_public_key": node_public_key,
                    "hop_count": hop_count,
                }

        status = content_data.get("status")
        if isinstance(status, str) and status.strip():
            status_payload: dict[str, Any] = {
                "status": status.strip(),
            }
            if node_public_key:
                status_payload["node_public_key"] = node_public_key
            uptime = self._parse_int(content_data.get("uptime"))
            message_count = self._parse_int(content_data.get("message_count"))
            if message_count is None:
                message_count = self._parse_int(content_data.get("messageCount"))
            if uptime is not None:
                status_payload["uptime"] = uptime
            if message_count is not None:
                status_payload["message_count"] = message_count
            return "status_response", status_payload

        return None

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
        if decoded_payload_type != 4:
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

    @staticmethod
    def _extract_response_content_data(value: Any) -> dict[str, Any] | None:
        """Parse response `content` payload into a dictionary when possible."""
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return None

        text = value.strip()
        if not text:
            return None

        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None

        return None

    @staticmethod
    def _normalize_hash_list(value: Any) -> list[str] | None:
        """Normalize a list of variable-length hex hash strings.

        Accepts even-length hex strings of 2 or more characters.
        Each string is uppercased and validated as hexadecimal.
        Odd-length strings, empty strings, and non-hex strings are skipped.
        """
        if not isinstance(value, list):
            return None

        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            token = item.strip().upper()
            if len(token) < 2 or len(token) % 2 != 0:
                continue
            if any(ch not in "0123456789ABCDEF" for ch in token):
                continue
            normalized.append(token)
        return normalized or None

    @staticmethod
    def _normalize_float_list(value: Any) -> list[float] | None:
        """Normalize a list of numeric values as floats."""
        if not isinstance(value, list):
            return None

        normalized: list[float] = []
        for item in value:
            if isinstance(item, (int, float)):
                normalized.append(float(item))
        return normalized or None

    @staticmethod
    def _extract_public_key_from_hex(value: str) -> str | None:
        """Extract the first 64-char hex segment from a payload string."""
        match = re.search(r"([0-9A-Fa-f]{64})", value)
        if not match:
            return None
        return match.group(1).upper()

    @classmethod
    def _parse_hex_or_int(cls, value: Any) -> int | None:
        """Parse integers represented as decimal or hexadecimal strings."""
        parsed = cls._parse_int(value)
        if parsed is not None:
            return parsed
        if not isinstance(value, str):
            return None
        token = value.strip().removeprefix("0x").removeprefix("0X")
        if not token:
            return None
        if any(ch not in "0123456789ABCDEFabcdef" for ch in token):
            return None
        try:
            return int(token, 16)
        except ValueError:
            return None

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
            return channel_name.strip()
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
