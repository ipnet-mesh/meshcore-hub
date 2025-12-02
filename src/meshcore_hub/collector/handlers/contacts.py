"""Handler for contacts sync events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node

logger = logging.getLogger(__name__)


def handle_contacts(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a contacts sync event.

    Upserts all contacts in the contacts list.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Contacts payload
        db: Database manager
    """
    contacts = payload.get("contacts", [])
    if not contacts:
        logger.debug("Empty contacts list received")
        return

    now = datetime.now(timezone.utc)
    created_count = 0
    updated_count = 0

    with db.session_scope() as session:
        for contact in contacts:
            contact_key = contact.get("public_key")
            if not contact_key:
                continue

            name = contact.get("name")
            node_type = contact.get("node_type")

            # Find or create node
            node_query = select(Node).where(Node.public_key == contact_key)
            node = session.execute(node_query).scalar_one_or_none()

            if node:
                # Update existing node
                if name and not node.name:
                    node.name = name
                if node_type and not node.adv_type:
                    node.adv_type = node_type
                node.last_seen = now
                updated_count += 1
            else:
                # Create new node
                node = Node(
                    public_key=contact_key,
                    name=name,
                    adv_type=node_type,
                    first_seen=now,
                    last_seen=now,
                )
                session.add(node)
                created_count += 1

    logger.info(
        f"Processed contacts sync: {created_count} new, {updated_count} updated"
    )
