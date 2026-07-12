"""RouteObserver model — observer scope entry within a Route."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.node import Node
    from meshcore_hub.common.models.route import Route


class RouteObserver(Base, UUIDMixin, TimestampMixin):
    """An observer node in a route's optional observer scope.

    When a route has observer entries, only receptions by those observers are
    considered during evaluation.  When the scope is empty, all observers are
    considered.

    Attributes:
        id: UUID primary key
        route_id: FK to routes (cascades on delete)
        node_id: FK to nodes
    """

    __tablename__ = "route_observers"

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

    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="route_observers",
    )
    node: Mapped["Node"] = relationship(
        "Node",
        foreign_keys=[node_id],
    )

    def __repr__(self) -> str:
        return f"<RouteObserver(route_id={self.route_id[:8]}..., node_id={self.node_id[:8]}...)>"
