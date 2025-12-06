"""EventReceiver model for tracking which nodes received each event."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now

if TYPE_CHECKING:
    from meshcore_hub.common.models.node import Node


class EventReceiver(Base, UUIDMixin, TimestampMixin):
    """Junction model tracking which receivers observed each event.

    This table enables multi-receiver tracking for deduplicated events.
    When multiple receiver nodes observe the same mesh event, each receiver
    gets an entry in this table linked by the event_hash.

    Attributes:
        id: UUID primary key
        event_type: Type of event ('message', 'advertisement', 'trace', 'telemetry')
        event_hash: Hash identifying the unique event (links to event tables)
        receiver_node_id: FK to the node that received this event
        snr: Signal-to-noise ratio at this receiver (if available)
        received_at: When this specific receiver saw the event
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "event_receivers"

    event_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    event_hash: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    receiver_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snr: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationship to receiver node
    receiver_node: Mapped["Node"] = relationship(
        "Node",
        foreign_keys=[receiver_node_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "event_hash", "receiver_node_id", name="uq_event_receivers_hash_node"
        ),
        Index("ix_event_receivers_type_hash", "event_type", "event_hash"),
    )

    def __repr__(self) -> str:
        return (
            f"<EventReceiver(type={self.event_type}, "
            f"hash={self.event_hash[:8]}..., "
            f"node={self.receiver_node_id[:8]}...)>"
        )


def add_event_receiver(
    session: Session,
    event_type: str,
    event_hash: str,
    receiver_node_id: str,
    snr: Optional[float] = None,
    received_at: Optional[datetime] = None,
) -> bool:
    """Add a receiver to an event, handling duplicates gracefully.

    Uses INSERT OR IGNORE to handle the unique constraint on (event_hash, receiver_node_id).

    Args:
        session: SQLAlchemy session
        event_type: Type of event ('message', 'advertisement', 'trace', 'telemetry')
        event_hash: Hash identifying the unique event
        receiver_node_id: UUID of the receiver node
        snr: Signal-to-noise ratio at this receiver (optional)
        received_at: When this receiver saw the event (defaults to now)

    Returns:
        True if a new receiver entry was added, False if it already existed.
    """
    from datetime import timezone

    now = received_at or datetime.now(timezone.utc)

    stmt = (
        sqlite_insert(EventReceiver)
        .values(
            id=str(uuid4()),
            event_type=event_type,
            event_hash=event_hash,
            receiver_node_id=receiver_node_id,
            snr=snr,
            received_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["event_hash", "receiver_node_id"])
    )
    result = session.execute(stmt)
    # CursorResult has rowcount attribute
    rowcount = getattr(result, "rowcount", 0)
    return bool(rowcount and rowcount > 0)
