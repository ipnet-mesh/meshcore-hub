"""TracePath model for storing network trace data."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class TracePath(Base, UUIDMixin, TimestampMixin):
    """TracePath model for storing network trace path results.

    Attributes:
        id: UUID primary key
        receiver_node_id: FK to nodes (receiving interface)
        initiator_tag: Unique trace identifier
        path_len: Path length
        flags: Trace flags
        auth: Authentication data
        path_hashes: JSON array of node hash identifiers
        snr_values: JSON array of SNR values per hop
        hop_count: Total number of hops
        received_at: When received by interface
        created_at: Record creation timestamp
    """

    __tablename__ = "trace_paths"

    receiver_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    initiator_tag: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    path_len: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    flags: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    auth: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    path_hashes: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    snr_values: Mapped[Optional[list[float]]] = mapped_column(
        JSON,
        nullable=True,
    )
    hop_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_trace_paths_initiator_tag", "initiator_tag"),
        Index("ix_trace_paths_received_at", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<TracePath(id={self.id}, initiator_tag={self.initiator_tag}, hop_count={self.hop_count})>"
