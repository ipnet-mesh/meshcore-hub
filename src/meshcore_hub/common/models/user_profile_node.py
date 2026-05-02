"""UserProfileNode association model for user-to-node adoption."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base

if TYPE_CHECKING:
    from meshcore_hub.common.models.node import Node
    from meshcore_hub.common.models.user_profile import UserProfile


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserProfileNode(Base):
    """Association table linking UserProfiles to Nodes (adoption).

    A node can be adopted by at most one user (enforced by unique constraint
    on node_id). A user can adopt zero or more nodes.

    Attributes:
        user_profile_id: FK to user_profiles.id (part of composite PK)
        node_id: FK to nodes.id (part of composite PK, also unique)
        adopted_at: Timestamp when the adoption occurred
    """

    __tablename__ = "user_profile_nodes"

    user_profile_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    adopted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )

    user_profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        back_populates="node_associations",
    )
    node: Mapped["Node"] = relationship(
        "Node",
        back_populates="user_profile_associations",
    )

    __table_args__ = (
        UniqueConstraint("node_id", name="uq_user_profile_nodes_node_id"),
        Index("ix_user_profile_nodes_node_id", "node_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserProfileNode("
            f"user_profile_id={self.user_profile_id}, "
            f"node_id={self.node_id})>"
        )
