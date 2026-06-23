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
        observer_node_id: FK to nodes (observing interface)
        message_type: Message type (contact, channel)
        pubkey_prefix: Sender's public key prefix (12 chars, contact msgs)
        channel_idx: Channel index (channel msgs)
        text: Message content
        path_len: Number of hops
        txt_type: Message type indicator
        signature: Message signature (hex), or the packet_hash fallback
        snr: Signal-to-noise ratio
        sender_timestamp: Sender's timestamp
        received_at: When received by interface
        created_at: Record creation timestamp
        path_prefix: First N origin-side hop hashes joined (spam scoring signal)
        sender_normalized: Lower-cased sender name with trailing digits stripped
        spam_score: Likely-spam score 0.0-1.0 (null when scoring disabled)
    """

    __tablename__ = "messages"

    observer_node_id: Mapped[Optional[str]] = mapped_column(
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
        String(32),
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
    event_hash: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        unique=True,
    )
    # LetsMesh wire packet hash, links this event to its raw_packets rows.
    packet_hash: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    # Spam scoring: first N origin-side hop hashes joined (e.g. "16,69,23");
    # null below the path-length gate so short paths don't pollute path counts.
    path_prefix: Mapped[Optional[str]] = mapped_column(
        String(48),
        nullable=True,
    )
    # Spam scoring: lower-cased sender name with trailing digits stripped
    # (e.g. "bob17" -> "bob"), so suffix rotation collapses to one identity.
    sender_normalized: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    # Spam scoring: likely-spam score 0.0-1.0; null when scoring is disabled.
    spam_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    __table_args__ = (
        Index("ix_messages_message_type", "message_type"),
        Index("ix_messages_pubkey_prefix", "pubkey_prefix"),
        Index("ix_messages_channel_idx", "channel_idx"),
        Index("ix_messages_received_at", "received_at"),
        Index("ix_messages_path_prefix_received_at", "path_prefix", "received_at"),
        Index(
            "ix_messages_sender_normalized_received_at",
            "sender_normalized",
            "received_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, type={self.message_type}, text={self.text[:20]}...)>"
