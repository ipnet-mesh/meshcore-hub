"""Event hash utilities for deduplication.

This module provides functions to compute deterministic hashes for events,
allowing deduplication when multiple receiver nodes report the same event.
"""

import hashlib
from datetime import datetime
from typing import Optional


def compute_message_hash(
    text: str,
    pubkey_prefix: Optional[str] = None,
    channel_idx: Optional[int] = None,
    sender_timestamp: Optional[datetime] = None,
    txt_type: Optional[int] = None,
) -> str:
    """Compute a deterministic hash for a message.

    The hash is computed from fields that uniquely identify a message's content
    and sender, excluding receiver-specific data.

    Args:
        text: Message content
        pubkey_prefix: Sender's public key prefix (12 chars)
        channel_idx: Channel index for channel messages
        sender_timestamp: Sender's timestamp
        txt_type: Message type indicator

    Returns:
        32-character hex hash string
    """
    # Build a canonical string from the relevant fields
    parts = [
        text or "",
        pubkey_prefix or "",
        str(channel_idx) if channel_idx is not None else "",
        sender_timestamp.isoformat() if sender_timestamp else "",
        str(txt_type) if txt_type is not None else "",
    ]
    canonical = "|".join(parts)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def compute_advertisement_hash(
    public_key: str,
    name: Optional[str] = None,
    adv_type: Optional[str] = None,
    flags: Optional[int] = None,
    received_at: Optional[datetime] = None,
    bucket_minutes: int = 5,
) -> str:
    """Compute a deterministic hash for an advertisement.

    Advertisements are bucketed by time since the same node may advertise
    periodically and we want to deduplicate within a time window.

    Args:
        public_key: Advertised node's public key
        name: Advertised name
        adv_type: Node type
        flags: Capability flags
        received_at: When received (used for time bucketing)
        bucket_minutes: Time bucket size in minutes (default 5)

    Returns:
        32-character hex hash string
    """
    # Bucket the time to allow deduplication within a window
    time_bucket = ""
    if received_at:
        # Round down to nearest bucket
        bucket_seconds = bucket_minutes * 60
        epoch = int(received_at.timestamp())
        bucket_epoch = (epoch // bucket_seconds) * bucket_seconds
        time_bucket = str(bucket_epoch)

    parts = [
        public_key,
        name or "",
        adv_type or "",
        str(flags) if flags is not None else "",
        time_bucket,
    ]
    canonical = "|".join(parts)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def compute_trace_hash(initiator_tag: int) -> str:
    """Compute a deterministic hash for a trace path.

    Trace paths have a unique initiator_tag that serves as the identifier.

    Args:
        initiator_tag: Unique trace identifier

    Returns:
        32-character hex hash string
    """
    return hashlib.md5(str(initiator_tag).encode("utf-8")).hexdigest()


def compute_telemetry_hash(
    node_public_key: str,
    parsed_data: Optional[dict] = None,
    received_at: Optional[datetime] = None,
    bucket_minutes: int = 5,
) -> str:
    """Compute a deterministic hash for a telemetry record.

    Telemetry is bucketed by time since nodes report periodically.

    Args:
        node_public_key: Reporting node's public key
        parsed_data: Decoded sensor readings
        received_at: When received (used for time bucketing)
        bucket_minutes: Time bucket size in minutes (default 5)

    Returns:
        32-character hex hash string
    """
    # Bucket the time
    time_bucket = ""
    if received_at:
        bucket_seconds = bucket_minutes * 60
        epoch = int(received_at.timestamp())
        bucket_epoch = (epoch // bucket_seconds) * bucket_seconds
        time_bucket = str(bucket_epoch)

    # Serialize parsed_data deterministically
    data_str = ""
    if parsed_data:
        # Sort keys for deterministic serialization
        sorted_items = sorted(parsed_data.items())
        data_str = str(sorted_items)

    parts = [
        node_public_key,
        data_str,
        time_bucket,
    ]
    canonical = "|".join(parts)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()
