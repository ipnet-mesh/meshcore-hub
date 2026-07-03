"""Raw packet capture handler.

Stores one ``RawPacket`` row per observer reception from the LetsMesh
``packets`` feed, independent of how the packet is later classified. The decode
is reused from the normalizer's per-hex decode cache (a second ``decode_payload``
call is a cache hit, not a re-decode), so capture adds only a single insert plus
the observer upsert to the ingest path.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from meshcore_hub.collector.letsmesh_normalizer import LetsMeshNormalizer
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node, RawPacket

logger = logging.getLogger(__name__)

# Wire route-type codes -> labels (mirrors LetsMeshNormalizer._ROUTE_TYPE_MAP).
_ROUTE_TYPE_MAP: dict[int, str] = {
    0: "transport_flood",
    1: "flood",
    2: "direct",
    3: "transport_direct",
}


def _extract_source_pubkey_prefix(
    decoded_packet: Optional[dict[str, Any]],
) -> Optional[str]:
    """Derive a 12-char sender prefix from the decoder sourceHash/senderPublicKey."""
    decoded = LetsMeshNormalizer._extract_letsmesh_decoder_payload(decoded_packet)
    if not decoded:
        return None
    for key in ("sourceHash", "senderPublicKey"):
        prefix = LetsMeshNormalizer._normalize_pubkey_prefix(decoded.get(key))
        if prefix:
            return prefix
    return None


def _path_hash_byte_width(hashes: list[str] | None) -> int | None:
    """Widest path-hash prefix width in bytes (each hash is hex: 2/4/6 chars)."""
    if not hashes:
        return None
    widths = [len(h) // 2 for h in hashes if isinstance(h, str) and h]
    return max(widths) if widths else None


def store_raw_packet(
    public_key: str,
    payload: dict[str, Any],
    decoded_packet: Optional[dict[str, Any]],
    event_type: str,
    db: DatabaseManager,
) -> None:
    """Capture a single raw packet from the LetsMesh ``packets`` feed.

    Args:
        public_key: Observer (receiver) node public key from the MQTT topic
        payload: Original LetsMesh upload payload (carries ``raw``, ``hash``, SNR)
        decoded_packet: Decoder output already produced during normalization
        event_type: How the collector classified the packet
        db: Database manager
    """
    now = datetime.now(timezone.utc)

    raw_value = payload.get("raw")
    raw_hex = raw_value.strip() if isinstance(raw_value, str) else None

    hash_value = payload.get("hash")
    packet_hash = hash_value if isinstance(hash_value, str) else None

    payload_type = LetsMeshNormalizer._extract_letsmesh_decoder_payload_type(
        decoded_packet
    )
    packet_type = LetsMeshNormalizer._parse_int(payload.get("packet_type"))
    if packet_type is None:
        packet_type = payload_type

    channel_idx = LetsMeshNormalizer._parse_int(payload.get("channel_idx"))
    if channel_idx is None:
        channel_hash = LetsMeshNormalizer._extract_letsmesh_decoder_channel_hash(
            decoded_packet
        )
        if channel_hash:
            channel_idx = LetsMeshNormalizer._parse_channel_hash_idx(channel_hash)

    source_pubkey_prefix = _extract_source_pubkey_prefix(decoded_packet)

    route_type: Optional[str] = None
    if isinstance(decoded_packet, dict):
        route_raw = LetsMeshNormalizer._parse_int(decoded_packet.get("routeType"))
        if route_raw in _ROUTE_TYPE_MAP:
            route_type = _ROUTE_TYPE_MAP[route_raw]

    path_len = LetsMeshNormalizer._parse_path_length(payload.get("path"))
    if path_len is None:
        path_len = LetsMeshNormalizer._extract_letsmesh_decoder_path_length(
            decoded_packet
        )

    path_hashes = LetsMeshNormalizer._normalize_hash_list(
        decoded_packet.get("path") if isinstance(decoded_packet, dict) else None
    )
    if not path_hashes and isinstance(decoded_packet, dict):
        inner = (decoded_packet.get("payload") or {}).get("decoded") or {}
        path_hashes = LetsMeshNormalizer._normalize_hash_list(inner.get("pathHashes"))
    path_hash_bytes = _path_hash_byte_width(path_hashes)

    snr = LetsMeshNormalizer._parse_float(payload.get("SNR"))
    if snr is None:
        snr = LetsMeshNormalizer._parse_float(payload.get("snr"))

    with db.session_scope() as session:
        observer_node = None
        if public_key:
            observer_node = session.execute(
                select(Node).where(Node.public_key == public_key)
            ).scalar_one_or_none()
            if not observer_node:
                observer_node = Node(
                    public_key=public_key,
                    first_seen=now,
                    last_seen=now,
                    is_observer=True,
                )
                session.add(observer_node)
                session.flush()
            else:
                observer_node.last_seen = now
                if not observer_node.is_observer:
                    observer_node.is_observer = True

        session.add(
            RawPacket(
                observer_node_id=observer_node.id if observer_node else None,
                packet_hash=packet_hash,
                raw_hex=raw_hex,
                packet_type=packet_type,
                payload_type=payload_type,
                event_type=event_type,
                channel_idx=channel_idx,
                source_pubkey_prefix=source_pubkey_prefix,
                route_type=route_type,
                path_len=path_len,
                path_hash_bytes=path_hash_bytes,
                snr=snr,
                decoded=decoded_packet,
                received_at=now,
            )
        )

    logger.debug("Captured raw packet: %s (%s)", packet_hash or "unknown", event_type)
