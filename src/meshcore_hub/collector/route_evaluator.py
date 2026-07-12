"""Route health evaluator — background evaluation driver.

Wraps :mod:`meshcore_hub.collector.routes` to evaluate every enabled route
and upsert the results into ``route_results``.  Called on a scheduler thread
inside the collector subscriber (mirroring the spam re-scoring sweep).
"""

import logging
from datetime import datetime, timezone

from meshcore_hub.collector.routes import upsert_route_result
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models.route import Route
from sqlalchemy import select

logger = logging.getLogger(__name__)


def run_evaluation(db: DatabaseManager) -> int:
    """Evaluate all enabled routes and upsert results.

    Returns the number of routes evaluated.
    """
    now = datetime.now(timezone.utc)
    with db.session_scope() as session:
        routes = (
            session.execute(select(Route).where(Route.enabled.is_(True)))
            .scalars()
            .all()
        )

        count = 0
        for route in routes:
            try:
                from datetime import timedelta

                route_since = now - timedelta(hours=route.window_hours)
                from meshcore_hub.collector.routes import evaluate_route

                state, quality, matched_count = evaluate_route(
                    session, route, route_since
                )
                upsert_route_result(session, route, state, quality, matched_count)
                count += 1
            except Exception:
                logger.exception("Error evaluating route '%s'", route.name)

        return count
