"""Route model for mesh link health monitoring."""

from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.route_node import RouteNode
    from meshcore_hub.common.models.route_observer import RouteObserver
    from meshcore_hub.common.models.route_recent_match import RouteRecentMatch
    from meshcore_hub.common.models.route_result import RouteResult
    from meshcore_hub.common.models.route_result_history import RouteResultHistory


class RouteVisibility(str, Enum):
    """Route visibility/permission levels (mirrors ChannelVisibility)."""

    COMMUNITY = "community"
    MEMBER = "member"
    OPERATOR = "operator"
    ADMIN = "admin"


class Route(Base, UUIDMixin, TimestampMixin):
    """A monitored multi-hop route across mesh nodes.

    A route is **healthy** when enough distinct packets traverse the configured
    ordered node sequence within the time window.  See the plan for full
    semantics.

    Attributes:
        id: UUID primary key
        from_label: Human-readable label for the route's start endpoint
        to_label: Human-readable label for the route's end endpoint
        description: Optional longer description
        visibility: Role-based visibility level
        match_width: Path-hash prefix width in bytes (1/2/3)
        window_hours: Evaluation lookback window in hours
        packet_count_threshold: Minimum distinct packets for healthy
        clear_threshold: Comfort bar for the clear/marginal split (null = 3x threshold)
        max_hop_span: Max hops between first and last configured node (null = unlimited)
        max_path_length: Max number of hops in a candidate packet's full path (null = unlimited)
        enabled: Whether this route is actively evaluated
    """

    __tablename__ = "routes"
    __table_args__ = (
        Index("ix_routes_from_to", "from_label", "to_label", unique=True),
    )

    from_label: Mapped[str] = mapped_column(String(255), nullable=False)
    to_label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    visibility: Mapped[str] = mapped_column(
        String(20),
        default=RouteVisibility.COMMUNITY.value,
        nullable=False,
    )
    match_width: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    window_hours: Mapped[int] = mapped_column(
        Integer,
        default=48,
        nullable=False,
    )
    packet_count_threshold: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    clear_threshold: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    max_hop_span: Mapped[Optional[int]] = mapped_column(
        Integer,
        default=8,
        nullable=True,
    )
    max_path_length: Mapped[Optional[int]] = mapped_column(
        Integer,
        default=None,
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    reversible: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    route_nodes: Mapped[list["RouteNode"]] = relationship(
        "RouteNode",
        back_populates="route",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RouteNode.position",
    )
    route_observers: Mapped[list["RouteObserver"]] = relationship(
        "RouteObserver",
        back_populates="route",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    route_result: Mapped[Optional["RouteResult"]] = relationship(
        "RouteResult",
        back_populates="route",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    route_result_history: Mapped[list["RouteResultHistory"]] = relationship(
        "RouteResultHistory",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteResultHistory.date",
        passive_deletes=True,
    )
    route_recent_matches: Mapped[list["RouteRecentMatch"]] = relationship(
        "RouteRecentMatch",
        back_populates="route",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Route(from={self.from_label}, to={self.to_label}, enabled={self.enabled})>"
