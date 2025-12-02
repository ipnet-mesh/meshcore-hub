"""Advertisement model for storing node advertisements."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class Advertisement(Base, UUIDMixin, TimestampMixin):
    """Advertisement model for storing node advertisements.

    Attributes:
        id: UUID primary key
        receiver_node_id: FK to nodes (receiving interface)
        node_id: FK to nodes (advertised node)
        public_key: Advertised public key
        name: Advertised name
        adv_type: Node type (chat, repeater, room, none)
        flags: Capability flags
        received_at: When received by interface
        created_at: Record creation timestamp
    """

    __tablename__ = "advertisements"

    receiver_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    public_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    adv_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    flags: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_advertisements_received_at", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<Advertisement(id={self.id}, public_key={self.public_key[:12]}..., name={self.name})>"
