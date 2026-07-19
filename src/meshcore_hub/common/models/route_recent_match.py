"""RouteRecentMatch model — normalized link from a route to its recent matches.

One row per ``(route, raw_packet)`` pair that the background evaluator
identified as a recent match. Capped at ``ROUTE_RECENT_MATCHES_LIMIT``
rows per route (default 3); the sweep replaces the set on every tick.

The actual packet / path data stays in its canonical home
(``raw_packets`` / ``packet_path_hops``) — this table only stores the
link plus the ``[first_position, last_position]`` slice of the packet's
path that matched the route's expected sequence. The detail page JOINs
through ``raw_packet_id`` to render the full match card, so late
``event_hash`` backfills and raw-packet retention purges propagate
automatically (via the ``ON DELETE CASCADE`` FK) without manual resync.

Cascade rules:

* ``route_id`` FK cascades on route delete (matches disappear with the
  route).
* ``raw_packet_id`` FK cascades on raw-packet delete (matches disappear
  with the underlying packet — retention cleanup handles this).
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.raw_packet import RawPacket
    from meshcore_hub.common.models.route import Route


# Default cap enforced by the evaluator sweep. Reads also LIMIT by this
# value as a safety net.
ROUTE_RECENT_MATCHES_LIMIT = 3


class RouteRecentMatch(Base, UUIDMixin, TimestampMixin):
    """A single recent ``route ↔ raw_packet`` match identified by the sweep.

    Attributes:
        id: UUID primary key
        route_id: FK to routes (cascades on delete)
        raw_packet_id: FK to raw_packets (cascades on delete)
        first_position: Index into the packet's path of the first matched hop
        last_position: Index into the packet's path of the last matched hop
            (inclusive). The matched subpath is ``hops[first_position ..
            last_position]``.
    """

    __tablename__ = "route_recent_matches"
    __table_args__ = (
        UniqueConstraint(
            "route_id", "raw_packet_id", name="uq_route_recent_matches_route_packet"
        ),
    )

    route_id: Mapped[str] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_packet_id: Mapped[str] = mapped_column(
        ForeignKey("raw_packets.id", ondelete="CASCADE"),
        nullable=False,
    )
    first_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    last_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="route_recent_matches",
    )
    raw_packet: Mapped["RawPacket"] = relationship(
        "RawPacket",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<RouteRecentMatch(route_id={self.route_id[:8]}..., "
            f"raw_packet_id={self.raw_packet_id[:8]}..., "
            f"positions=[{self.first_position}..{self.last_position}])>"
        )
