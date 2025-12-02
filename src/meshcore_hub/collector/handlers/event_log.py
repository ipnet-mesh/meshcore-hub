"""Generic event log handler for informational events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import EventLog, Node

logger = logging.getLogger(__name__)


def handle_event_log(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle an event by logging it to the events_log table.

    This is used for informational events that don't need
    specific processing but should be recorded.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Event payload
        db: Database manager
    """
    now = datetime.now(timezone.utc)

    with db.session_scope() as session:
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

        # Create event log record
        event_log = EventLog(
            receiver_node_id=receiver_node.id if receiver_node else None,
            event_type=event_type,
            payload=payload,
            received_at=now,
        )
        session.add(event_log)

    logger.debug(f"Logged event: {event_type}")
