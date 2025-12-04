"""Handler for contact sync events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node

logger = logging.getLogger(__name__)

# Map numeric node type to string representation
NODE_TYPE_MAP = {
    0: "none",
    1: "chat",
    2: "repeater",
    3: "room",
}


def handle_contact(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a single contact event.

    Upserts a contact into the nodes table.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Single contact object with fields:
            - public_key: Contact's public key
            - adv_name: Advertised name
            - type: Numeric node type (0=none, 1=chat, 2=repeater, 3=room)
        db: Database manager
    """
    contact_key = payload.get("public_key")
    if not contact_key:
        logger.warning("Contact event missing public_key field")
        return

    # Device uses 'adv_name' for the advertised name
    name = payload.get("adv_name") or payload.get("name")

    logger.info(f"Processing contact: {contact_key[:12]}... adv_name={name}")

    # Device uses numeric 'type' field, convert to string
    raw_type = payload.get("type")
    if raw_type is not None:
        node_type: str | None = NODE_TYPE_MAP.get(raw_type, str(raw_type))
    else:
        node_type = payload.get("node_type")

    now = datetime.now(timezone.utc)

    with db.session_scope() as session:
        # Find or create node
        node_query = select(Node).where(Node.public_key == contact_key)
        node = session.execute(node_query).scalar_one_or_none()

        if node:
            # Update existing node - always update name if we have one
            if name and name != node.name:
                logger.info(
                    f"Updating node {contact_key[:12]}... "
                    f"name: {node.name!r} -> {name!r}"
                )
                node.name = name
            if node_type and not node.adv_type:
                node.adv_type = node_type
            node.last_seen = now
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
            logger.info(f"Created node from contact: {contact_key[:12]}... ({name})")
