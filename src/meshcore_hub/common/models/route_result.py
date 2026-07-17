"""RouteResult model — cached evaluation result for a Route."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now

if TYPE_CHECKING:
    from meshcore_hub.common.models.route import Route


class RouteState(str, Enum):
    """Alerting axis of route health (see F4)."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    NO_COVERAGE = "no_coverage"


class RouteQuality(str, Enum):
    """Display axis of route health (traffic-light band, see F4)."""

    CLEAR = "clear"
    MARGINAL = "marginal"
    FAILING = "failing"
    UNKNOWN = "unknown"


class RouteResult(Base, UUIDMixin, TimestampMixin):
    """The latest cached evaluation result for a route (one row per route).

    Written by the background evaluator and read by the API/UI.  ``threshold``
    and ``effective_clear`` are snapshotted at evaluation time so the display
    stays self-consistent if thresholds are later changed.

    Attributes:
        id: UUID primary key
        route_id: FK to routes (unique, cascades on delete)
        state: Alerting axis (healthy / unhealthy / no_coverage)
        quality: Display axis (clear / marginal / failing / unknown)
        matched_count: Distinct packet count (lower bound when short-circuited)
        threshold: Snapshot of route.packet_count_threshold at eval time
        effective_clear: Snapshot of effective_clear_threshold at eval time
        evaluated_at: When this evaluation ran
    """

    __tablename__ = "route_results"

    route_id: Mapped[str] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    quality: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    matched_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    effective_clear: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="route_result",
    )

    def __repr__(self) -> str:
        return (
            f"<RouteResult(route_id={self.route_id[:8]}..., "
            f"state={self.state}, quality={self.quality}, "
            f"matched={self.matched_count})>"
        )
