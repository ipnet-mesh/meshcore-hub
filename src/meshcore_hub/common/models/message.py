"""Message model for storing received messages."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class Message(Base, UUIDMixin, TimestampMixin):
    """Message model for storing contact and channel messages.

    Attributes:
        id: UUID primary key
        receiver_node_id: FK to nodes (receiving interface)
        message_type: Message type (contact, channel)
        pubkey_prefix: Sender's public key prefix (12 chars, contact msgs)
        channel_idx: Channel index (channel msgs)
        text: Message content
        path_len: Number of hops
        txt_type: Message type indicator
        signature: Message signature (8 hex chars)
        snr: Signal-to-noise ratio
        sender_timestamp: Sender's timestamp
        received_at: When received by interface
        created_at: Record creation timestamp
    """

    __tablename__ = "messages"

    receiver_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    pubkey_prefix: Mapped[Optional[str]] = mapped_column(
        String(12),
        nullable=True,
    )
    channel_idx: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    path_len: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    txt_type: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    signature: Mapped[Optional[str]] = mapped_column(
        String(8),
        nullable=True,
    )
    snr: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    sender_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_messages_message_type", "message_type"),
        Index("ix_messages_pubkey_prefix", "pubkey_prefix"),
        Index("ix_messages_channel_idx", "channel_idx"),
        Index("ix_messages_received_at", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, type={self.message_type}, text={self.text[:20]}...)>"
