"""Handler for advertisement events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.hash_utils import compute_advertisement_hash
from meshcore_hub.common.models import Advertisement, Node, add_event_receiver

logger = logging.getLogger(__name__)


def handle_advertisement(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle an advertisement event.

    1. Upserts the node in the nodes table
    2. Creates an advertisement record
    3. Updates node last_seen timestamp

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Advertisement payload
        db: Database manager
    """
    adv_public_key = payload.get("public_key")
    if not adv_public_key:
        logger.warning("Advertisement missing public_key")
        return

    name = payload.get("name")
    adv_type = payload.get("adv_type")
    flags = payload.get("flags")
    now = datetime.now(timezone.utc)

    # Compute event hash for deduplication (30-second time bucket)
    event_hash = compute_advertisement_hash(
        public_key=adv_public_key,
        name=name,
        adv_type=adv_type,
        flags=flags,
        received_at=now,
    )

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

        # Check if advertisement with same hash already exists
        existing = session.execute(
            select(Advertisement.id).where(Advertisement.event_hash == event_hash)
        ).scalar_one_or_none()

        if existing:
            # Still update advertised node's last_seen even for duplicate advertisements
            node_query = select(Node).where(Node.public_key == adv_public_key)
            node = session.execute(node_query).scalar_one_or_none()
            if node:
                node.last_seen = now

            # Add this receiver to the junction table
            if receiver_node:
                added = add_event_receiver(
                    session=session,
                    event_type="advertisement",
                    event_hash=event_hash,
                    receiver_node_id=receiver_node.id,
                    snr=None,  # Advertisements don't have SNR
                    received_at=now,
                )
                if added:
                    logger.debug(
                        f"Added receiver {public_key[:12]}... to advertisement "
                        f"(hash={event_hash[:8]}...)"
                    )
            return

        # Find or create advertised node
        node_query = select(Node).where(Node.public_key == adv_public_key)
        node = session.execute(node_query).scalar_one_or_none()

        if node:
            # Update existing node
            if name:
                node.name = name
            if adv_type:
                node.adv_type = adv_type
            if flags is not None:
                node.flags = flags
            node.last_seen = now
        else:
            # Create new node
            node = Node(
                public_key=adv_public_key,
                name=name,
                adv_type=adv_type,
                flags=flags,
                first_seen=now,
                last_seen=now,
            )
            session.add(node)
            session.flush()

        # Create advertisement record
        advertisement = Advertisement(
            receiver_node_id=receiver_node.id if receiver_node else None,
            node_id=node.id,
            public_key=adv_public_key,
            name=name,
            adv_type=adv_type,
            flags=flags,
            received_at=now,
            event_hash=event_hash,
        )
        session.add(advertisement)

        # Add first receiver to junction table
        if receiver_node:
            add_event_receiver(
                session=session,
                event_type="advertisement",
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
                f"Duplicate advertisement skipped (race condition, "
                f"hash={event_hash[:8]}...)"
            )
            # Re-add receiver to existing event in a new transaction
            if receiver_node:
                add_event_receiver(
                    session=session,
                    event_type="advertisement",
                    event_hash=event_hash,
                    receiver_node_id=receiver_node.id,
                    snr=None,
                    received_at=now,
                )
            return

    logger.info(
        f"Stored advertisement from {name or adv_public_key[:12]!r} "
        f"(type={adv_type})"
    )
