"""RouteNode model — ordered path-node entry within a Route."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.node import Node
    from meshcore_hub.common.models.route import Route


class RouteNode(Base, UUIDMixin, TimestampMixin):
    """An ordered node in a route's configured path.

    ``expected_hash`` is derived at save time as
    ``public_key[:2*match_width].upper()`` and must match the normalized
    (uppercase) ``node_hash`` column on ``packet_path_hops``.

    Attributes:
        id: UUID primary key
        route_id: FK to routes (cascades on delete)
        node_id: FK to nodes
        position: Zero-based order in the configured path
        expected_hash: Uppercased public-key prefix used for matching
    """

    __tablename__ = "route_nodes"

    route_id: Mapped[str] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    expected_hash: Mapped[Optional[str]] = mapped_column(
        String(6),
        nullable=True,
    )

    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="route_nodes",
    )
    node: Mapped["Node"] = relationship(
        "Node",
        foreign_keys=[node_id],
    )

    def __repr__(self) -> str:
        return (
            f"<RouteNode(route_id={self.route_id[:8]}..., "
            f"position={self.position}, expected_hash={self.expected_hash})>"
        )
