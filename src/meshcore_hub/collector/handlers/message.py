"""Handler for message events."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Message, Node

logger = logging.getLogger(__name__)


def handle_contact_message(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a contact message event.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Message payload
        db: Database manager
    """
    _handle_message(public_key, "contact", payload, db)


def handle_channel_message(
    public_key: str,
    event_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a channel message event.

    Args:
        public_key: Receiver node's public key (from MQTT topic)
        event_type: Event type name
        payload: Message payload
        db: Database manager
    """
    _handle_message(public_key, "channel", payload, db)


def _handle_message(
    public_key: str,
    message_type: str,
    payload: dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Handle a message event (contact or channel).

    Args:
        public_key: Receiver node's public key
        message_type: Message type ('contact' or 'channel')
        payload: Message payload
        db: Database manager
    """
    text = payload.get("text")
    if not text:
        logger.warning(f"Message missing text content")
        return

    now = datetime.now(timezone.utc)

    # Extract fields based on message type
    pubkey_prefix = payload.get("pubkey_prefix") if message_type == "contact" else None
    channel_idx = payload.get("channel_idx") if message_type == "channel" else None
    path_len = payload.get("path_len")
    txt_type = payload.get("txt_type")
    signature = payload.get("signature")
    snr = payload.get("SNR") or payload.get("snr")

    # Parse sender timestamp
    sender_ts = payload.get("sender_timestamp")
    sender_timestamp = None
    if sender_ts:
        try:
            sender_timestamp = datetime.fromtimestamp(sender_ts, tz=timezone.utc)
        except (ValueError, OSError):
            pass

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

        # Create message record
        message = Message(
            receiver_node_id=receiver_node.id if receiver_node else None,
            message_type=message_type,
            pubkey_prefix=pubkey_prefix,
            channel_idx=channel_idx,
            text=text,
            path_len=path_len,
            txt_type=txt_type,
            signature=signature,
            snr=snr,
            sender_timestamp=sender_timestamp,
            received_at=now,
        )
        session.add(message)

    if message_type == "contact":
        logger.info(
            f"Stored contact message from {pubkey_prefix!r}: "
            f"{text[:30]}{'...' if len(text) > 30 else ''}"
        )
    else:
        logger.info(
            f"Stored channel {channel_idx} message: "
            f"{text[:30]}{'...' if len(text) > 30 else ''}"
        )
