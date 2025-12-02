"""Node model for tracking MeshCore network nodes."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now

if TYPE_CHECKING:
    from meshcore_hub.common.models.node_tag import NodeTag


class Node(Base, UUIDMixin, TimestampMixin):
    """Node model representing a MeshCore network node.

    Attributes:
        id: UUID primary key
        public_key: Node's 64-character hex public key (unique)
        name: Node display name
        adv_type: Advertisement type (chat, repeater, room, none)
        flags: Capability/status flags bitmask
        first_seen: Timestamp of first advertisement
        last_seen: Timestamp of most recent activity
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "nodes"

    public_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
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
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    tags: Mapped[list["NodeTag"]] = relationship(
        "NodeTag",
        back_populates="node",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_nodes_last_seen", "last_seen"),
        Index("ix_nodes_adv_type", "adv_type"),
    )

    def __repr__(self) -> str:
        return f"<Node(id={self.id}, public_key={self.public_key[:12]}..., name={self.name})>"
