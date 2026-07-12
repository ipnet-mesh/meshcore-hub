"""Route model for mesh link health monitoring."""

from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.route_node import RouteNode
    from meshcore_hub.common.models.route_observer import RouteObserver
    from meshcore_hub.common.models.route_result import RouteResult


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
        name: Unique route display name
        description: Optional longer description
        visibility: Role-based visibility level
        match_width: Path-hash prefix width in bytes (1/2/3)
        window_hours: Evaluation lookback window in hours
        packet_count_threshold: Minimum distinct packets for healthy
        degraded_threshold: Comfort bar for the clear/marginal split (null = 2x threshold)
        max_hop_span: Max hops between first and last configured node (null = unlimited)
        enabled: Whether this route is actively evaluated
    """

    __tablename__ = "routes"

    name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
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
        default=24,
        nullable=False,
    )
    packet_count_threshold: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )
    degraded_threshold: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    max_hop_span: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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

    def __repr__(self) -> str:
        return f"<Route(name={self.name}, enabled={self.enabled})>"
