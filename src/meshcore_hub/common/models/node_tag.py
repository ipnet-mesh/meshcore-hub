"""NodeTag model for custom node metadata."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.node import Node


class NodeTag(Base, UUIDMixin, TimestampMixin):
    """NodeTag model for custom node metadata.

    Allows users to assign arbitrary key-value tags to nodes.

    Attributes:
        id: UUID primary key
        node_id: Foreign key to nodes table
        key: Tag name/key
        value: Tag value (stored as text, can be JSON for typed values)
        value_type: Type hint (string, number, boolean, coordinate)
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "node_tags"

    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    value: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    value_type: Mapped[str] = mapped_column(
        String(20),
        default="string",
        nullable=False,
    )

    # Relationships
    node: Mapped["Node"] = relationship(
        "Node",
        back_populates="tags",
    )

    __table_args__ = (
        UniqueConstraint("node_id", "key", name="uq_node_tags_node_key"),
        Index("ix_node_tags_key", "key"),
    )

    def __repr__(self) -> str:
        return f"<NodeTag(node_id={self.node_id}, key={self.key}, value={self.value})>"
