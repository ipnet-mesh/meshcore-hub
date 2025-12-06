"""Handler for trace data events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.hash_utils import compute_trace_hash
from meshcore_hub.common.models import Node, TracePath, add_event_receiver

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
        # Find or create receiver node first (needed for both new and duplicate events)
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

        # Check if trace with same hash already exists
        existing = session.execute(
            select(TracePath.id).where(TracePath.event_hash == event_hash)
        ).scalar_one_or_none()

        if existing:
            # Event already exists - just add this receiver to the junction table
            if receiver_node:
                added = add_event_receiver(
                    session=session,
                    event_type="trace",
                    event_hash=event_hash,
                    receiver_node_id=receiver_node.id,
                    snr=None,  # Trace events don't have a single SNR value
                    received_at=now,
                )
                if added:
                    logger.debug(
                        f"Added receiver {public_key[:12]}... to trace "
                        f"(tag={initiator_tag})"
                    )
            return

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

        # Add first receiver to junction table
        if receiver_node:
            add_event_receiver(
                session=session,
                event_type="trace",
                event_hash=event_hash,
                receiver_node_id=receiver_node.id,
                snr=None,
                received_at=now,
            )

        # Flush to check for duplicate constraint violation (race condition)
        try:
            session.flush()
        except IntegrityError:
            # Race condition: another request inserted the same event_hash
            session.rollback()
            logger.debug(
                f"Duplicate trace skipped (race condition, tag={initiator_tag})"
            )
            # Re-add receiver to existing event in a new transaction
            if receiver_node:
                add_event_receiver(
                    session=session,
                    event_type="trace",
                    event_hash=event_hash,
                    receiver_node_id=receiver_node.id,
                    snr=None,
                    received_at=now,
                )
            return

    logger.info(f"Stored trace data: tag={initiator_tag}, hops={hop_count}")
