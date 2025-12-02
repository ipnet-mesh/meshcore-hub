"""EventLog model for storing all event payloads."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class EventLog(Base, UUIDMixin, TimestampMixin):
    """EventLog model for storing all event payloads for audit/debugging.

    Attributes:
        id: UUID primary key
        receiver_node_id: FK to nodes (receiving interface)
        event_type: Event type name
        payload: Full event payload as JSON
        received_at: When received by interface
        created_at: Record creation timestamp
    """

    __tablename__ = "events_log"

    receiver_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_events_log_event_type", "event_type"),
        Index("ix_events_log_received_at", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<EventLog(id={self.id}, event_type={self.event_type})>"
