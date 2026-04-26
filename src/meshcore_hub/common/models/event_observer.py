"""EventObserver model for tracking which observer nodes captured each event."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now

if TYPE_CHECKING:
    from meshcore_hub.common.models.node import Node


class EventObserver(Base, UUIDMixin, TimestampMixin):
    """Junction model tracking which observers captured each event.

    This table enables multi-observer tracking for deduplicated events.
    When multiple observer nodes capture the same mesh event, each observer
    gets an entry in this table linked by the event_hash.

    Attributes:
        id: UUID primary key
        event_type: Type of event ('message', 'advertisement', 'trace', 'telemetry')
        event_hash: Hash identifying the unique event (links to event tables)
        observer_node_id: FK to the node that observed this event
        snr: Signal-to-noise ratio at this observer (if available)
        path_len: Hop count at this observer (if available)
        observed_at: When this specific observer captured the event
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "event_observers"

    event_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    event_hash: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    observer_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snr: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    path_len: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    observer_node: Mapped["Node"] = relationship(
        "Node",
        foreign_keys=[observer_node_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "event_hash", "observer_node_id", name="uq_event_observers_hash_node"
        ),
        Index("ix_event_observers_type_hash", "event_type", "event_hash"),
    )

    def __repr__(self) -> str:
        return (
            f"<EventObserver(type={self.event_type}, "
            f"hash={self.event_hash[:8]}..., "
            f"node={self.observer_node_id[:8]}...)>"
        )


def add_event_observer(
    session: Session,
    event_type: str,
    event_hash: str,
    observer_node_id: str,
    snr: Optional[float] = None,
    path_len: Optional[int] = None,
    observed_at: Optional[datetime] = None,
) -> bool:
    """Add an observer to an event, handling duplicates gracefully.

    Uses INSERT OR IGNORE to handle the unique constraint on (event_hash, observer_node_id).

    Args:
        session: SQLAlchemy session
        event_type: Type of event ('message', 'advertisement', 'trace', 'telemetry')
        event_hash: Hash identifying the unique event
        observer_node_id: UUID of the observer node
        snr: Signal-to-noise ratio at this observer (optional)
        path_len: Hop count at this observer (optional)
        observed_at: When this observer captured the event (defaults to now)

    Returns:
        True if a new observer entry was added, False if it already existed.
    """
    from datetime import timezone

    now = observed_at or datetime.now(timezone.utc)

    stmt = (
        sqlite_insert(EventObserver)
        .values(
            id=str(uuid4()),
            event_type=event_type,
            event_hash=event_hash,
            observer_node_id=observer_node_id,
            snr=snr,
            path_len=path_len,
            observed_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["event_hash", "observer_node_id"])
    )
    result = session.execute(stmt)
    rowcount = getattr(result, "rowcount", 0)
    return bool(rowcount and rowcount > 0)
