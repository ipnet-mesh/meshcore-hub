"""Handler for trace data events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.hash_utils import compute_trace_hash
from meshcore_hub.common.models import Node, TracePath

logger = logging.getLogger(__name__)


def handle_trace_data(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a trace data event.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Trace data payload
        db: Database manager
    """
    initiator_tag = payload.get("initiator_tag")
    if initiator_tag is None:
        logger.warning("Trace data missing initiator_tag")
        return

    now = datetime.now(timezone.utc)

    path_len = payload.get("path_len")
    flags = payload.get("flags")
    auth = payload.get("auth")
    path_hashes = payload.get("path_hashes")
    snr_values = payload.get("snr_values")
    hop_count = payload.get("hop_count")

    # Compute event hash for deduplication (initiator_tag is unique per trace)
    event_hash = compute_trace_hash(initiator_tag=initiator_tag)

    with db.session_scope() as session:
        # Check if trace with same hash already exists
        existing = session.execute(
            select(TracePath.id).where(TracePath.event_hash == event_hash)
        ).scalar_one_or_none()

        if existing:
            logger.debug(f"Duplicate trace skipped (tag={initiator_tag})")
            return

        # Find receiver node
        receiver_node = None
        if public_key:
            receiver_query = select(Node).where(Node.public_key == public_key)
            receiver_node = session.execute(receiver_query).scalar_one_or_none()

            if not receiver_node:
                receiver_node = Node(
                    public_key=public_key,
                    first_seen=now,
                    last_seen=now,
                )
                session.add(receiver_node)
                session.flush()
            else:
                receiver_node.last_seen = now

        # Create trace path record
        trace_path = TracePath(
            receiver_node_id=receiver_node.id if receiver_node else None,
            initiator_tag=initiator_tag,
            path_len=path_len,
            flags=flags,
            auth=auth,
            path_hashes=path_hashes,
            snr_values=snr_values,
            hop_count=hop_count,
            received_at=now,
            event_hash=event_hash,
        )
        session.add(trace_path)

    logger.info(f"Stored trace data: tag={initiator_tag}, hops={hop_count}")
