"""Handler for telemetry events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node, Telemetry

logger = logging.getLogger(__name__)


def handle_telemetry(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a telemetry response event.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Telemetry payload
        db: Database manager
    """
    node_public_key = payload.get("node_public_key")
    if not node_public_key:
        logger.warning("Telemetry missing node_public_key")
        return

    now = datetime.now(timezone.utc)

    lpp_data = payload.get("lpp_data")
    parsed_data = payload.get("parsed_data")

    # Convert lpp_data to bytes if it's a string or list
    lpp_bytes = None
    if lpp_data:
        if isinstance(lpp_data, bytes):
            lpp_bytes = lpp_data
        elif isinstance(lpp_data, list):
            lpp_bytes = bytes(lpp_data)
        elif isinstance(lpp_data, str):
            try:
                lpp_bytes = bytes.fromhex(lpp_data)
            except ValueError:
                lpp_bytes = lpp_data.encode()

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

        # Find or create reporting node
        reporting_node = None
        if node_public_key:
            node_query = select(Node).where(Node.public_key == node_public_key)
            reporting_node = session.execute(node_query).scalar_one_or_none()

            if not reporting_node:
                reporting_node = Node(
                    public_key=node_public_key,
                    first_seen=now,
                    last_seen=now,
                )
                session.add(reporting_node)
                session.flush()
            else:
                reporting_node.last_seen = now

        # Create telemetry record
        telemetry = Telemetry(
            receiver_node_id=receiver_node.id if receiver_node else None,
            node_id=reporting_node.id if reporting_node else None,
            node_public_key=node_public_key,
            lpp_data=lpp_bytes,
            parsed_data=parsed_data,
            received_at=now,
        )
        session.add(telemetry)

    # Log telemetry values
    if parsed_data:
        values = ", ".join(f"{k}={v}" for k, v in parsed_data.items())
        logger.info(f"Stored telemetry from {node_public_key[:12]!r}: {values}")
    else:
        logger.info(f"Stored telemetry from {node_public_key[:12]!r}")
