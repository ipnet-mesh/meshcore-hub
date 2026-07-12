"""Route health matching engine.

Fetch-and-check strategy: fetch candidate receptions whose path contains the
first configured node prefix, then run a trivial two-pointer subsequence match
per reception.  Scales with (candidates) only, not (candidates × depth).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshcore_hub.common.models.node import Node
from meshcore_hub.common.models.packet_path_hop import PacketPathHop
from meshcore_hub.common.models.route import Route
from meshcore_hub.common.models.route_result import (
    RouteQuality,
    RouteResult,
    RouteState,
)

logger = logging.getLogger(__name__)

#: Multiplier for the relative default comfort bar (``degraded_threshold = None``
#: means ``effective_degraded = 2 × packet_count_threshold``).
DEGRADED_DEFAULT_MULTIPLIER = 2

#: Cap on candidate receptions for preview to bound work per call.
PREVIEW_CANDIDATE_CAP = 5000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex_prefix_end(prefix: str) -> str:
    """Exclusive upper bound for a hex prefix range scan.

    Increments the last character's ASCII value by one.  For hex digits this
    yields the correct lexicographic boundary ('9' → ':', 'A' → 'B', 'F' → 'G').
    """
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)


def derive_expected_hash(public_key: str, match_width: int) -> str:
    """Derive the uppercase path-hash prefix for a node at a given width."""
    return public_key[: 2 * match_width].upper()


def effective_degraded_threshold(route: Route) -> int:
    """The effective comfort bar: explicit value or ``2 × threshold``."""
    return route.degraded_threshold or (
        route.packet_count_threshold * DEGRADED_DEFAULT_MULTIPLIER
    )


def derive_quality(
    state: str,
    matched_count: int,
    threshold: int,
    effective_degraded: int,
) -> str:
    """Map ``(state, matched_count, thresholds)`` to a quality band."""
    if state == RouteState.HEALTHY.value:
        if matched_count >= effective_degraded:
            return RouteQuality.CLEAR.value
        return RouteQuality.MARGINAL.value
    if state == RouteState.UNHEALTHY.value:
        return RouteQuality.FAILING.value
    return RouteQuality.UNKNOWN.value


def is_subsequence(
    path: list[dict[str, Any]],
    expected: list[str],
    max_hop_span: Optional[int] = None,
) -> bool:
    """Pure two-pointer subsequence prefix match with gaps allowed.

    Each entry in *path* is a dict with ``position`` and ``node_hash``.
    *expected* is the ordered list of uppercase hash prefixes to find.
    A hop matches when ``node_hash.startswith(expected_hash)``.
    ``max_hop_span`` constrains ``position(last) - position(first)`` when set.
    """
    if not expected:
        return False
    pi = 0
    first_pos: Optional[int] = None
    last_pos: Optional[int] = None
    for needed in expected:
        found = False
        while pi < len(path):
            hop = path[pi]
            pi += 1
            if hop["node_hash"].startswith(needed):
                pos = hop["position"]
                if first_pos is None:
                    first_pos = pos
                last_pos = pos
                found = True
                break
        if not found:
            return False
    if max_hop_span is not None and first_pos is not None and last_pos is not None:
        return last_pos - first_pos <= max_hop_span
    return True


def prefix_collision_counts(session: Session, match_width: int) -> dict[str, int]:
    """Count how many nodes share each public-key prefix at *match_width*.

    Returns a mapping ``{prefix: count}`` where *prefix* is the uppercased
    first ``2*match_width`` hex chars of each node's public key.
    """
    chars = 2 * match_width
    prefix_expr = func.upper(func.substr(Node.public_key, 1, chars))
    rows = session.execute(
        select(prefix_expr, func.count(Node.id)).group_by(prefix_expr)
    ).all()
    return {str(prefix): int(count) for prefix, count in rows if prefix}


def detect_observed_widths(session: Session, public_key: str) -> set[int]:
    """Detect which path-hash prefix widths a node has been observed at."""
    widths: set[int] = set()
    for width in (1, 2, 3):
        prefix = derive_expected_hash(public_key, width)
        prefix_end = _hex_prefix_end(prefix)
        count = (
            session.execute(
                select(func.count())
                .select_from(PacketPathHop)
                .where(
                    PacketPathHop.node_hash >= prefix,
                    PacketPathHop.node_hash < prefix_end,
                )
            ).scalar()
            or 0
        )
        if count > 0:
            widths.add(width)
    return widths


# ---------------------------------------------------------------------------
# Candidate fetching
# ---------------------------------------------------------------------------


def _route_expected_hashes(route: Route) -> list[str]:
    """Ordered expected hash prefixes from the route's nodes."""
    expected: list[str] = []
    for rn in route.route_nodes:
        if rn.expected_hash:
            expected.append(rn.expected_hash)
        elif rn.node and rn.node.public_key:
            expected.append(derive_expected_hash(rn.node.public_key, route.match_width))
    return expected


def fetch_candidate_paths(
    session: Session,
    first_prefix: str,
    since: datetime,
    observer_ids: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch all hops for receptions whose path starts with *first_prefix*.

    Returns a dict ``{raw_packet_id: [{position, node_hash, packet_hash,
    received_at, observer_node_id}, ...]}`` ordered by position within each
    reception.
    """
    prefix_end = _hex_prefix_end(first_prefix)

    subq = (
        select(PacketPathHop.raw_packet_id)
        .where(
            PacketPathHop.node_hash >= first_prefix,
            PacketPathHop.node_hash < prefix_end,
            PacketPathHop.received_at >= since,
        )
        .group_by(PacketPathHop.raw_packet_id)
    )
    if observer_ids:
        subq = subq.where(PacketPathHop.observer_node_id.in_(observer_ids))
    if limit is not None:
        subq = subq.limit(limit)
    subq_obj = subq.subquery()

    stmt = (
        select(
            PacketPathHop.raw_packet_id,
            PacketPathHop.position,
            PacketPathHop.node_hash,
            PacketPathHop.packet_hash,
            PacketPathHop.received_at,
            PacketPathHop.observer_node_id,
        )
        .where(PacketPathHop.raw_packet_id.in_(select(subq_obj.c.raw_packet_id)))
        .order_by(PacketPathHop.raw_packet_id, PacketPathHop.position)
    )

    paths: dict[str, list[dict[str, Any]]] = {}
    for row in session.execute(stmt).all():
        rp_id = row.raw_packet_id
        if rp_id not in paths:
            paths[rp_id] = []
        paths[rp_id].append(
            {
                "position": row.position,
                "node_hash": row.node_hash,
                "packet_hash": row.packet_hash,
                "received_at": row.received_at,
                "observer_node_id": row.observer_node_id,
            }
        )
    return paths


def _count_candidate_receptions(
    session: Session,
    first_prefix: str,
    since: datetime,
    observer_ids: Optional[list[str]] = None,
) -> int:
    """Count distinct receptions matching the first prefix in the window."""
    prefix_end = _hex_prefix_end(first_prefix)
    stmt = select(func.count(func.distinct(PacketPathHop.raw_packet_id))).where(
        PacketPathHop.node_hash >= first_prefix,
        PacketPathHop.node_hash < prefix_end,
        PacketPathHop.received_at >= since,
    )
    if observer_ids:
        stmt = stmt.where(PacketPathHop.observer_node_id.in_(observer_ids))
    return session.execute(stmt).scalar() or 0


def _has_any_hops_in_window(
    session: Session,
    since: datetime,
    observer_ids: Optional[list[str]] = None,
) -> bool:
    """Existence check: are there ANY in-scope hops in the window?"""
    stmt = (
        select(func.count())
        .select_from(PacketPathHop)
        .where(PacketPathHop.received_at >= since)
    )
    if observer_ids:
        stmt = stmt.where(PacketPathHop.observer_node_id.in_(observer_ids))
    return (session.execute(stmt).scalar() or 0) > 0


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_route(
    session: Session,
    route: Route,
    since: datetime,
) -> tuple[str, str, int]:
    """Evaluate a single route.

    Returns ``(state, quality, matched_count)``.  *matched_count* is a lower
    bound when the evaluation short-circuits at the comfort bar.
    """
    expected = _route_expected_hashes(route)
    if len(expected) < 2:
        return RouteState.NO_COVERAGE.value, RouteQuality.UNKNOWN.value, 0

    observer_ids = (
        [ro.node_id for ro in route.route_observers] if route.route_observers else None
    )

    paths = fetch_candidate_paths(session, expected[0], since, observer_ids)

    eff_degraded = effective_degraded_threshold(route)

    matched_packets: set[str] = set()
    for hops in paths.values():
        if is_subsequence(hops, expected, route.max_hop_span):
            ph = hops[0]["packet_hash"]
            if ph:
                matched_packets.add(ph)
                if len(matched_packets) >= eff_degraded:
                    return (
                        RouteState.HEALTHY.value,
                        RouteQuality.CLEAR.value,
                        len(matched_packets),
                    )

    matched_count = len(matched_packets)
    threshold = route.packet_count_threshold

    if matched_count >= threshold:
        state = RouteState.HEALTHY.value
    else:
        exists = _has_any_hops_in_window(session, since, observer_ids)
        state = RouteState.UNHEALTHY.value if exists else RouteState.NO_COVERAGE.value

    quality = derive_quality(state, matched_count, threshold, eff_degraded)
    return state, quality, matched_count


def evaluate_all_routes(
    session: Session, now: datetime
) -> dict[str, tuple[str, str, int]]:
    """Evaluate every enabled route.

    Returns ``{route_id: (state, quality, matched_count)}``.
    """
    routes = (
        session.execute(select(Route).where(Route.enabled.is_(True))).scalars().all()
    )

    results: dict[str, tuple[str, str, int]] = {}
    for route in routes:
        try:
            route_since = now - timedelta(hours=route.window_hours)
            results[route.id] = evaluate_route(session, route, route_since)
        except Exception:
            logger.exception("Error evaluating route '%s'", route.name)
    return results


def upsert_route_result(
    session: Session,
    route: Route,
    state: str,
    quality: str,
    matched_count: int,
) -> RouteResult:
    """Upsert a route evaluation result (ORM check-then-update/insert)."""
    now = datetime.now(timezone.utc)
    eff_degraded = effective_degraded_threshold(route)

    existing = session.execute(
        select(RouteResult).where(RouteResult.route_id == route.id)
    ).scalar_one_or_none()

    if existing:
        existing.state = state
        existing.quality = quality
        existing.matched_count = matched_count
        existing.threshold = route.packet_count_threshold
        existing.effective_degraded = eff_degraded
        existing.evaluated_at = now
        return existing

    result = RouteResult(
        id=str(uuid4()),
        route_id=route.id,
        state=state,
        quality=quality,
        matched_count=matched_count,
        threshold=route.packet_count_threshold,
        effective_degraded=eff_degraded,
        evaluated_at=now,
    )
    session.add(result)
    return result


# ---------------------------------------------------------------------------
# Card expand + preview
# ---------------------------------------------------------------------------


def recent_matches(
    session: Session,
    route: Route,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return the latest *limit* matching paths for a route."""
    expected = _route_expected_hashes(route)
    if len(expected) < 2:
        return []

    observer_ids = (
        [ro.node_id for ro in route.route_observers] if route.route_observers else None
    )
    since = datetime.now(timezone.utc) - timedelta(hours=route.window_hours)

    paths = fetch_candidate_paths(session, expected[0], since, observer_ids)

    matches: list[dict[str, Any]] = []
    for hops in paths.values():
        if is_subsequence(hops, expected, route.max_hop_span):
            first = hops[0] if hops else {}
            matches.append(
                {
                    "packet_hash": first.get("packet_hash"),
                    "hops": hops,
                    "received_at": first.get("received_at"),
                    "observer_node_id": first.get("observer_node_id"),
                }
            )

    matches.sort(
        key=lambda m: m["received_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return matches[:limit]


def preview_route(
    session: Session,
    config: dict[str, Any],
    since: datetime,
) -> dict[str, Any]:
    """Preview matching for an unsaved route config.

    *config* keys: ``node_ids``, ``match_width``, ``observer_ids``,
    ``max_hop_span``, ``packet_count_threshold``, ``degraded_threshold``.
    """
    node_ids: list[str] = config.get("node_ids") or []
    match_width: int = config.get("match_width") or 1
    observer_ids: Optional[list[str]] = config.get("observer_ids") or None
    max_hop_span: Optional[int] = config.get("max_hop_span")
    threshold: int = config.get("packet_count_threshold") or 3
    degraded: Optional[int] = config.get("degraded_threshold")

    if len(node_ids) < 2:
        return {
            "matched_count": 0,
            "quality": RouteQuality.UNKNOWN.value,
            "state": RouteState.NO_COVERAGE.value,
            "contributing_observers": {},
            "collisions": {},
            "truncated": False,
        }

    nodes = session.execute(select(Node).where(Node.id.in_(node_ids))).scalars().all()
    node_map = {n.id: n for n in nodes}

    expected = [
        derive_expected_hash(node_map[nid].public_key, match_width)
        for nid in node_ids
        if nid in node_map and node_map[nid].public_key
    ]
    if len(expected) < 2:
        return {
            "matched_count": 0,
            "quality": RouteQuality.UNKNOWN.value,
            "state": RouteState.NO_COVERAGE.value,
            "contributing_observers": {},
            "collisions": {},
            "truncated": False,
        }

    first_prefix = expected[0]

    candidate_count = _count_candidate_receptions(
        session, first_prefix, since, observer_ids
    )
    if candidate_count > PREVIEW_CANDIDATE_CAP:
        return {
            "matched_count": None,
            "quality": None,
            "truncated": True,
            "candidate_count": candidate_count,
        }

    paths = fetch_candidate_paths(session, first_prefix, since, observer_ids)

    eff_degraded = degraded or (threshold * DEGRADED_DEFAULT_MULTIPLIER)

    matched_packets: set[str] = set()
    contributing: dict[str, int] = {}

    for hops in paths.values():
        if is_subsequence(hops, expected, max_hop_span):
            ph = hops[0]["packet_hash"]
            if ph:
                matched_packets.add(ph)
            obs = hops[0]["observer_node_id"]
            if obs:
                contributing[obs] = contributing.get(obs, 0) + 1

    matched_count = len(matched_packets)

    if matched_count >= threshold:
        state = RouteState.HEALTHY.value
    else:
        exists = _has_any_hops_in_window(session, since, observer_ids)
        state = RouteState.UNHEALTHY.value if exists else RouteState.NO_COVERAGE.value

    quality = derive_quality(state, matched_count, threshold, eff_degraded)

    collisions_map = prefix_collision_counts(session, match_width)
    node_collisions = {
        nid: collisions_map.get(
            derive_expected_hash(node_map[nid].public_key, match_width), 1
        )
        for nid in node_ids
        if nid in node_map
    }

    return {
        "matched_count": matched_count,
        "quality": quality,
        "state": state,
        "contributing_observers": contributing,
        "collisions": node_collisions,
        "truncated": False,
    }
