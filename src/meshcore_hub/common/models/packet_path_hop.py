"""PacketPathHop model — denormalized hop index for route matching."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass


class PacketPathHop(Base, UUIDMixin, TimestampMixin):
    """One row per ``(reception, hop position)`` in the packet path index.

    Populated at ingest inside ``store_raw_packet`` from the already-computed
    normalized ``path_hashes``.  The denormalized ``packet_hash``,
    ``received_at``, and ``observer_node_id`` columns let route queries filter
    by time window, observer scope, and distinct-packet count without a join
    back to ``raw_packets``.

    Attributes:
        id: UUID primary key
        raw_packet_id: FK to raw_packets (cascades on delete)
        position: Zero-based hop position in the ordered path
        node_hash: Normalized (uppercase) hex prefix for this hop
        packet_hash: Denormalized packet hash from raw_packets
        received_at: Denormalized reception timestamp from raw_packets
        observer_node_id: Denormalized observer node FK
    """

    __tablename__ = "packet_path_hops"

    raw_packet_id: Mapped[str] = mapped_column(
        ForeignKey("raw_packets.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    node_hash: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
    )
    packet_hash: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    observer_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_packet_path_hops_node_hash_received_at",
            "node_hash",
            "received_at",
        ),
        Index(
            "ix_packet_path_hops_raw_packet_id_position",
            "raw_packet_id",
            "position",
        ),
        Index(
            "ix_packet_path_hops_received_at",
            "received_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PacketPathHop(raw_packet_id={self.raw_packet_id[:8]}..., "
            f"position={self.position}, node_hash={self.node_hash})>"
        )
