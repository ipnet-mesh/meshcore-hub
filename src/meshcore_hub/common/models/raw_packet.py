"""RawPacket model for storing raw decoded wire packets."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class RawPacket(Base, UUIDMixin, TimestampMixin):
    """Raw on-air packet captured from the LetsMesh ``packets`` feed.

    One row is stored per observer reception (no deduplication). Rows are
    linkable back to the structured tables (messages, advertisements, ...) by
    ``packet_hash``. The raw hex and decoded summary are retained so the API can
    serve a complete searchable record of wire traffic without re-decoding.

    Attributes:
        id: UUID primary key
        observer_node_id: FK to nodes (the receiving interface)
        packet_hash: LetsMesh packet hash, links rows to structured records and
            groups multi-observer receptions
        raw_hex: The on-air bytes from ``payload["raw"]``
        packet_type: Wire packet type
        payload_type: Decoder payload type
        event_type: How the collector classified the packet
        channel_idx: ``int(channelHash, 16)`` for channel-message packets, else
            NULL; drives channel-visibility redaction
        source_pubkey_prefix: Sender prefix derived from the decoder sourceHash /
            senderPublicKey, for efficient "packets from this node" filtering
        route_type: Mapped route type (flood, transport_flood, direct, ...)
        path_len: Hop count
        snr: Signal-to-noise ratio as reported by the observer
        decoded: Decoder summary JSON, so the detail view needs no re-decode
        received_at: When received by the observing interface
        created_at: Record creation timestamp
    """

    __tablename__ = "raw_packets"

    observer_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    packet_hash: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    raw_hex: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    packet_type: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    payload_type: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    event_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    channel_idx: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    source_pubkey_prefix: Mapped[Optional[str]] = mapped_column(
        String(12),
        nullable=True,
        index=True,
    )
    route_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    path_len: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    snr: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    decoded: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_raw_packets_received_at", "received_at"),
        # Composite indexes serve the common "filter then sort by newest" shape
        # without a full scan + filesort. See plan TR-17 for the write-cost
        # trade-off; do not add further composites speculatively.
        Index("ix_raw_packets_event_type_received_at", "event_type", "received_at"),
        Index("ix_raw_packets_channel_idx_received_at", "channel_idx", "received_at"),
        Index(
            "ix_raw_packets_source_pubkey_prefix_received_at",
            "source_pubkey_prefix",
            "received_at",
        ),
        Index(
            "ix_raw_packets_packet_hash_received_at",
            "packet_hash",
            "received_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RawPacket(id={self.id}, event_type={self.event_type}, "
            f"packet_hash={self.packet_hash})>"
        )
