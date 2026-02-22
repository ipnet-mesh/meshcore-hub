"""LetsMesh packet decoder integration.

Provides an optional bridge to the external `meshcore-decoder` CLI so the
collector can turn LetsMesh upload `raw` packet hex into decoded message data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shlex
import shutil
import string
import subprocess
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class LetsMeshPacketDecoder:
    """Decode LetsMesh packet payloads with `meshcore-decoder` CLI."""

    class ChannelKey(NamedTuple):
        """Channel key metadata for decryption and channel labeling."""

        label: str | None
        key_hex: str
        channel_hash: str

    # Built-in keys required by your deployment.
    # - Public channel
    # - #test channel
    BUILTIN_CHANNEL_KEYS: tuple[tuple[str, str], ...] = (
        ("Public", "8B3387E9C5CDEA6AC9E5EDBAA115CD72"),
        ("test", "9CD8FCF22A47333B591D96A2B848B73F"),
    )

    def __init__(
        self,
        enabled: bool = True,
        command: str = "meshcore-decoder",
        channel_keys: list[str] | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._enabled = enabled
        self._command_tokens = shlex.split(command.strip()) if command.strip() else []
        self._channel_key_infos = self._normalize_channel_keys(channel_keys or [])
        self._channel_keys = [info.key_hex for info in self._channel_key_infos]
        self._channel_names_by_hash = {
            info.channel_hash: info.label
            for info in self._channel_key_infos
            if info.label
        }
        self._decode_cache: dict[str, dict[str, Any] | None] = {}
        self._decode_cache_maxsize = 2048
        self._timeout_seconds = timeout_seconds
        self._checked_command = False
        self._command_available = False
        self._warned_unavailable = False

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
        cached = self._decode_cache.get(clean_hex)
        if clean_hex in self._decode_cache:
            return cached

        decoded = self._decode_raw(clean_hex)
        self._decode_cache[clean_hex] = decoded
        if len(self._decode_cache) > self._decode_cache_maxsize:
            # Drop oldest cached payload (insertion-order dict).
            self._decode_cache.pop(next(iter(self._decode_cache)))
        return decoded

    def _decode_raw(self, raw_hex: str) -> dict[str, Any] | None:
        """Decode raw packet hex with decoder CLI (cached per packet hex)."""
        if not self._enabled:
            return None
        if not self._is_command_available():
            return None

        command = [*self._command_tokens, "decode", raw_hex, "--json"]
        if self._channel_keys:
            command.append("--key")
            command.extend(self._channel_keys)

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.debug(
                "LetsMesh decoder timed out after %.2fs",
                self._timeout_seconds,
            )
            return None
        except OSError as exc:
            logger.debug("LetsMesh decoder failed to execute: %s", exc)
            return None

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            logger.debug(
                "LetsMesh decoder exited with code %s%s",
                result.returncode,
                f": {stderr}" if stderr else "",
            )
            return None

        output = result.stdout.strip()
        if not output:
            return None

        try:
            decoded = json.loads(output)
        except json.JSONDecodeError:
            logger.debug("LetsMesh decoder returned non-JSON output")
            return None

        return decoded if isinstance(decoded, dict) else None

    def _is_command_available(self) -> bool:
        """Check decoder command availability once."""
        if self._checked_command:
            return self._command_available

        self._checked_command = True
        if not self._command_tokens:
            self._command_available = False
        else:
            command = self._command_tokens[0]
            if "/" in command:
                self._command_available = shutil.which(command) is not None
            else:
                self._command_available = shutil.which(command) is not None

        if not self._command_available and not self._warned_unavailable:
            self._warned_unavailable = True
            command_text = " ".join(self._command_tokens) or "<empty>"
            logger.warning(
                "LetsMesh decoder command not found (%s). "
                "Messages will remain encrypted placeholders until decoder is installed.",
                command_text,
            )

        return self._command_available
