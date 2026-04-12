"""LetsMesh packet decoder integration.

Provides native Python packet decoding via the ``meshcoredecoder`` library
so the collector can turn LetsMesh upload ``raw`` packet hex into decoded
message data.
"""

from __future__ import annotations

import hashlib
import logging
import string
from typing import Any, NamedTuple

from meshcoredecoder import MeshCoreDecoder
from meshcoredecoder.crypto import MeshCoreKeyStore
from meshcoredecoder.types import DecryptionOptions

logger = logging.getLogger(__name__)


class LetsMeshPacketDecoder:
    """Decode LetsMesh packet payloads with the native Python meshcore-decoder."""

    class ChannelKey(NamedTuple):
        """Channel key metadata for decryption and channel labeling."""

        label: str | None
        key_hex: str
        channel_hash: str

    BUILTIN_CHANNEL_KEYS: tuple[tuple[str, str], ...] = (
        ("Public", "8B3387E9C5CDEA6AC9E5EDBAA115CD72"),
        ("test", "9CD8FCF22A47333B591D96A2B848B73F"),
    )

    def __init__(
        self,
        channel_keys: list[str] | None = None,
    ) -> None:
        self._channel_key_infos = self._normalize_channel_keys(channel_keys or [])
        self._channel_keys = [info.key_hex for info in self._channel_key_infos]
        self._channel_names_by_hash = {
            info.channel_hash: info.label
            for info in self._channel_key_infos
            if info.label
        }
        self._decode_cache: dict[str, dict[str, Any] | None] = {}
        self._decode_cache_maxsize = 2048
        self._key_store = self._build_key_store()

    def _build_key_store(self) -> MeshCoreKeyStore:
        """Build a MeshCoreKeyStore from configured channel keys."""
        key_store = MeshCoreKeyStore()
        if self._channel_keys:
            key_store.add_channel_secrets(self._channel_keys)
        return key_store

    @classmethod
    def _normalize_channel_keys(cls, values: list[str]) -> list[ChannelKey]:
        """Normalize key list (labels + key + channel hash, deduplicated)."""
        normalized: list[LetsMeshPacketDecoder.ChannelKey] = []
        seen_keys: set[str] = set()

        for label, key in cls.BUILTIN_CHANNEL_KEYS:
            entry = cls._normalize_channel_entry(f"{label}={key}")
            if not entry:
                continue
            if entry.key_hex in seen_keys:
                continue
            normalized.append(entry)
            seen_keys.add(entry.key_hex)

        for value in values:
            entry = cls._normalize_channel_entry(value)
            if not entry:
                continue
            if entry.key_hex in seen_keys:
                continue
            normalized.append(entry)
            seen_keys.add(entry.key_hex)

        return normalized

    @classmethod
    def _normalize_channel_entry(cls, value: str | None) -> ChannelKey | None:
        """Normalize one key entry (`label=hex`, `label:hex`, or `hex`)."""
        if value is None:
            return None

        candidate = value.strip()
        if not candidate:
            return None

        label: str | None = None
        key_candidate = candidate
        for separator in ("=", ":"):
            if separator not in candidate:
                continue
            left, right = candidate.split(separator, 1)
            right = right.strip()
            right = right.removeprefix("0x").removeprefix("0X").strip()
            if right and cls._is_hex(right):
                label = left.strip().lstrip("#")
                key_candidate = right
                break

        key_candidate = key_candidate.strip()
        key_candidate = key_candidate.removeprefix("0x").removeprefix("0X").strip()
        if not key_candidate or not cls._is_hex(key_candidate):
            return None

        key_hex = key_candidate.upper()
        channel_hash = cls._compute_channel_hash(key_hex)
        normalized_label = label.strip() if label and label.strip() else None
        return cls.ChannelKey(
            label=normalized_label,
            key_hex=key_hex,
            channel_hash=channel_hash,
        )

    @staticmethod
    def _is_hex(value: str) -> bool:
        """Return True if string contains only hex digits."""
        return bool(value) and all(char in string.hexdigits for char in value)

    @staticmethod
    def _compute_channel_hash(key_hex: str) -> str:
        """Compute channel hash (first byte of SHA-256 of channel key)."""
        return hashlib.sha256(bytes.fromhex(key_hex)).digest()[:1].hex().upper()

    def channel_name_from_decoded(
        self,
        decoded_packet: dict[str, Any] | None,
    ) -> str | None:
        """Resolve channel label from decoded payload channel hash."""
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

        return self._channel_names_by_hash.get(channel_hash.upper())

    def channel_labels_by_index(self) -> dict[int, str]:
        """Return channel labels keyed by numeric channel index (0-255)."""
        labels: dict[int, str] = {}
        for info in self._channel_key_infos:
            if not info.label:
                continue

            label = info.label.strip()
            if not label:
                continue

            if label.lower() == "public":
                normalized_label = "Public"
            else:
                normalized_label = label if label.startswith("#") else f"#{label}"

            channel_idx = int(info.channel_hash, 16)
            labels.setdefault(channel_idx, normalized_label)

        return labels

    def decode_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Decode packet payload `raw` hex and return decoded JSON if available."""
        raw_hex = payload.get("raw")
        if not isinstance(raw_hex, str):
            return None
        clean_hex = raw_hex.strip()
        if not clean_hex:
            return None
        if not self._is_hex(clean_hex):
            logger.debug("LetsMesh decoder skipped non-hex raw payload")
            return None
        cached = self._decode_cache.get(clean_hex)
        if clean_hex in self._decode_cache:
            return cached

        decoded = self._decode_raw(clean_hex)
        self._decode_cache[clean_hex] = decoded
        if len(self._decode_cache) > self._decode_cache_maxsize:
            self._decode_cache.pop(next(iter(self._decode_cache)))
        return decoded

    def _decode_raw(self, raw_hex: str) -> dict[str, Any] | None:
        """Decode raw packet hex with native Python decoder (cached per packet hex)."""
        try:
            options = DecryptionOptions(
                key_store=self._key_store,
                attempt_decryption=True,
            )
            result = MeshCoreDecoder.decode(raw_hex, options)
        except Exception as exc:
            logger.debug("LetsMesh decoder failed: %s", exc)
            return None

        if not result.is_valid:
            errors = getattr(result, "errors", None)
            if errors:
                logger.debug("LetsMesh decoder errors: %s", errors)
            return None

        raw_payload_obj = None
        try:
            raw_payload_obj = result.payload.get("decoded")
        except (AttributeError, TypeError):
            pass

        decoded_dict = result.to_dict()

        if raw_payload_obj is not None:
            self._enrich_payload_decoded(decoded_dict, raw_payload_obj)

        self._flatten_control_parsed(decoded_dict)

        return decoded_dict if isinstance(decoded_dict, dict) else None

    _PAYLOAD_ATTR_MAP: tuple[tuple[str, str], ...] = (
        ("channel_hash", "channelHash"),
        ("cipher_mac", "cipherMac"),
        ("ciphertext", "ciphertext"),
        ("ciphertext_length", "ciphertextLength"),
        ("decrypted", "decrypted"),
        ("destination_hash", "destinationHash"),
        ("source_hash", "sourceHash"),
        ("sender_public_key", "senderPublicKey"),
        ("path_length", "pathLength"),
        ("path_hashes", "pathHashes"),
        ("extra_type", "extraType"),
        ("extra_data", "extraData"),
        ("checksum", "checksum"),
    )

    @classmethod
    def _enrich_payload_decoded(
        cls,
        decoded_dict: dict[str, Any],
        payload_obj: Any,
    ) -> None:
        """Enrich payload.decoded dict with fields the library's to_dict() omits.

        Several payload classes (GroupTextPayload, TextMessagePayload, etc.)
        inherit BasePayload.to_dict() which only returns type/version/isValid.
        This method reads the actual object attributes and merges them in so
        the normalizer can find decrypted text, channel hashes, etc.
        """
        payload_section = decoded_dict.get("payload")
        if not isinstance(payload_section, dict):
            return
        decoded_section = payload_section.get("decoded")
        if not isinstance(decoded_section, dict):
            return
        for attr_name, dict_key in cls._PAYLOAD_ATTR_MAP:
            value = getattr(payload_obj, attr_name, None)
            if value is None:
                continue
            decoded_section.setdefault(dict_key, value)

    @staticmethod
    def _flatten_control_parsed(decoded_dict: dict[str, Any]) -> None:
        """Flatten Control payload parsed sub-fields into decoded dict.

        The Python library nests sub-type-specific fields (publicKey, subType,
        nodeType, etc.) under ``payload.decoded.parsed`` while the TS CLI
        returns them flat at ``payload.decoded.*``.  The normalizer expects
        the flat layout.
        """
        payload = decoded_dict.get("payload")
        if not isinstance(payload, dict):
            return
        decoded = payload.get("decoded")
        if not isinstance(decoded, dict):
            return
        parsed = decoded.get("parsed")
        if not isinstance(parsed, dict):
            return
        for key, value in parsed.items():
            decoded.setdefault(key, value)
