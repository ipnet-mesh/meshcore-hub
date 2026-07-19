"""RouteResult model — cached evaluation result for a Route."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

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

    ``quality_avg`` holds the rolling 7-day average tier computed from the
    last 7 ``RouteResultHistory`` rows plus today's snapshot. It backs the
    route card badge and the dashboard strip summary so a flapping route
    that's currently up still shows as marginal/failing if the week's mean
    warrants it.

    The top-N recent matches for the detail page live in the separate
    ``route_recent_matches`` table (normalized link to ``raw_packets``)
    rather than on this row, so they stay consistent with raw-packet
    retention and ``event_hash`` backfills without manual resync.

    Attributes:
        id: UUID primary key
        route_id: FK to routes (unique, cascades on delete)
        state: Alerting axis (healthy / unhealthy / no_coverage)
        quality: Display axis (clear / marginal / failing / unknown)
        matched_count: Distinct packet count (lower bound when short-circuited)
        threshold: Snapshot of route.packet_count_threshold at eval time
        effective_clear: Snapshot of effective_clear_threshold at eval time
        evaluated_at: When this evaluation ran
        quality_avg: Rolling 7-day average quality tier (clear/marginal/failing)
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
    quality_avg: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
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
