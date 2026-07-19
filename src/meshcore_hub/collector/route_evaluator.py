"""Route health evaluator — background evaluation driver.

Two-cadence sweep:

* :func:`run_evaluation` runs on the short (default 60s) tick. For every
  enabled route it computes the current rolling-window snapshot via
  :func:`evaluate_route`, captures the top-3 recent matches, refreshes
  the rolling 7-day ``quality_avg``, and upserts everything into the
  single ``route_results`` row. ``route_result_history`` (one row per
  completed UTC day) is left untouched on this tick — today's data lives
  only in the rolling snapshot until the day rolls over and the hourly
  sweep captures it.

* :func:`run_history_backfill` runs on the longer (default 1h) tick. It
  recomputes the full retention window of ``route_result_history`` rows
  so late-arriving packets and route-config tweaks propagate backward
  into completed historical buckets, then refreshes ``quality_avg``.

The split keeps the hot 60s tick cheap (one bounded scan per route) and
pushes the more expensive history sweep onto a quiet background thread
where it can amortize a multi-day scan across the whole fleet.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select

from meshcore_hub.collector.routes import (
    compute_persisted_quality_avg,
    evaluate_route,
    evaluate_route_history,
    recent_matches,
    upsert_route_history_row,
    upsert_route_recent_matches,
    upsert_route_result,
)
from meshcore_hub.common.config import get_collector_settings
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models.route import Route

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_evaluation(db: DatabaseManager, now: datetime | None = None) -> int:
    """Evaluate every enabled route and upsert its result row.

    Returns the number of routes evaluated. On the short tick this only
    refreshes ``route_results`` (current snapshot + ``quality_avg`` +
    ``recent_matches_json``); completed historical days are written by
    :func:`run_history_backfill`.
    """
    current = now or datetime.now(timezone.utc)
    with db.session_scope() as session:
        routes = (
            session.execute(select(Route).where(Route.enabled.is_(True)))
            .scalars()
            .all()
        )

        count = 0
        for route in routes:
            try:
                _evaluate_one(session, route, current)
                count += 1
            except Exception:
                logger.exception(
                    "Error evaluating route '%s -> %s'",
                    route.from_label,
                    route.to_label,
                )

        return count


def _evaluate_one(session: "Session", route: Route, now: datetime) -> None:
    """Compute and persist the rolling snapshot + average + matches for a route."""
    from datetime import timedelta

    route_since = now - timedelta(hours=route.window_hours)
    state, quality, matched_count = evaluate_route(session, route, route_since)

    matches = recent_matches(session, route, limit=3, now=now)
    upsert_route_recent_matches(session, route.id, matches, limit=3)

    quality_avg = compute_persisted_quality_avg(
        session, route, today_quality=quality, now=now
    )

    upsert_route_result(
        session,
        route,
        state,
        quality,
        matched_count,
        quality_avg=quality_avg,
    )


def run_history_backfill(
    db: DatabaseManager,
    days: int | None = None,
    now: datetime | None = None,
) -> int:
    """Recompute the retention window of ``route_result_history`` for every route.

    Persists one row per completed UTC day (strictly before today) for
    each enabled route, then refreshes ``route_results.quality_avg``
    from the newly-assembled history. ``days`` defaults to the
    configured raw-packet retention window so backfills never scan
    purged data. Returns the number of routes backfilled.
    """
    current = now or datetime.now(timezone.utc)
    settings = get_collector_settings()
    window_days = (
        days if days is not None else settings.effective_raw_packet_retention_days
    )

    if window_days <= 0:
        return 0

    with db.session_scope() as session:
        routes = (
            session.execute(select(Route).where(Route.enabled.is_(True)))
            .scalars()
            .all()
        )

        count = 0
        for route in routes:
            try:
                _backfill_one(session, route, window_days, current)
                count += 1
            except Exception:
                logger.exception(
                    "Error backfilling route '%s -> %s'",
                    route.from_label,
                    route.to_label,
                )

        return count


def _backfill_one(session: "Session", route: Route, days: int, now: datetime) -> None:
    """Recompute persisted history for a single route + refresh ``quality_avg``."""
    today = now.date()

    # evaluate_route_history(include_today=False) yields N historical
    # calendar-day buckets ending yesterday — exactly the rows we persist.
    history = evaluate_route_history(session, route, days, include_today=False, now=now)

    for day, quality, state, matched_count in history:
        if day >= today:
            continue
        upsert_route_history_row(
            session,
            route.id,
            day,
            quality,
            state,
            matched_count,
            evaluated_at=now,
        )

    # Refresh quality_avg from the just-updated history + current snapshot.
    today_quality = route.route_result.quality if route.route_result else None
    if today_quality is not None:
        quality_avg = compute_persisted_quality_avg(
            session, route, today_quality=today_quality, now=now
        )
        if route.route_result is not None and quality_avg is not None:
            route.route_result.quality_avg = quality_avg
