"""RouteResultHistory model — per-day persisted health history for a Route.

One row per ``(route, UTC calendar day)`` carrying that day's evaluated
``quality`` / ``state`` / ``matched_count``. Written by the background
route evaluator on every sweep (today's bucket) and on the slower
backfill sweep (the full retention window, to catch late-arriving
packets and reflect config changes). Read by the API layer (per-route
history endpoint and the dashboard routes-overview widget) so the hot
path never re-scans ``packet_path_hops``.

The ``UNIQUE (route_id, date)`` constraint makes the upsert path
idempotent: a re-evaluation of the same day overwrites the prior row in
place. Cascade-delete on the parent ``routes`` row keeps cleanup
automatic when a route is removed.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now

if TYPE_CHECKING:
    from meshcore_hub.common.models.route import Route


class RouteResultHistory(Base, UUIDMixin, TimestampMixin):
    """One evaluated UTC calendar-day bucket for a route.

    Attributes:
        id: UUID primary key
        route_id: FK to routes (cascades on delete)
        date: UTC calendar day this bucket covers
        quality: Display axis (clear / marginal / failing / unknown)
        state: Alerting axis (healthy / unhealthy / no_coverage)
        matched_count: Distinct matching packet/event count for the day
        evaluated_at: When this bucket was last (re)computed
    """

    __tablename__ = "route_result_history"
    __table_args__ = (
        UniqueConstraint("route_id", "date", name="uq_route_result_history_route_date"),
    )

    route_id: Mapped[str] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    quality: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    matched_count: Mapped[int] = mapped_column(
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
        back_populates="route_result_history",
    )

    def __repr__(self) -> str:
        return (
            f"<RouteResultHistory(route_id={self.route_id[:8]}..., "
            f"date={self.date}, quality={self.quality}, "
            f"matched={self.matched_count})>"
        )
