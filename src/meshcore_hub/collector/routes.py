"""Route health matching engine.

Fetch-and-check strategy: fetch candidate receptions whose path contains the
first configured node prefix, then run a trivial two-pointer subsequence match
per reception.  Scales with (candidates) only, not (candidates × depth).
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from meshcore_hub.common.models.node import Node
from meshcore_hub.common.models.packet_path_hop import PacketPathHop
from meshcore_hub.common.models.route import Route
from meshcore_hub.common.models.route_recent_match import RouteRecentMatch
from meshcore_hub.common.models.route_result import (
    RouteQuality,
    RouteResult,
    RouteState,
)
from meshcore_hub.common.models.route_result_history import RouteResultHistory

logger = logging.getLogger(__name__)

#: Multiplier for the relative default comfort bar (``clear_threshold = None``
#: means ``effective_clear = 3 × packet_count_threshold``).
CLEAR_DEFAULT_MULTIPLIER = 3

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


def effective_clear_threshold(route: Route) -> int:
    """The effective comfort bar: explicit value or ``3 × threshold``."""
    return route.clear_threshold or (
        route.packet_count_threshold * CLEAR_DEFAULT_MULTIPLIER
    )


def derive_quality(
    state: str,
    matched_count: int,
    threshold: int,
    effective_clear: int,
) -> str:
    """Map ``(state, matched_count, thresholds)`` to a quality band."""
    if state == RouteState.HEALTHY.value:
        if matched_count >= effective_clear:
            return RouteQuality.CLEAR.value
        return RouteQuality.MARGINAL.value
    if state == RouteState.UNHEALTHY.value:
        return RouteQuality.FAILING.value
    return RouteQuality.UNKNOWN.value


def _match_identity(hops: list[dict[str, Any]]) -> Optional[str]:
    """Identity used to dedup matched receptions into one match per event.

    Prefers the denormalized ``event_hash`` (the underlying structured
    event's identity, populated at ingest) so that retransmissions of the
    same advert/message/telemetry/trace count once instead of once per
    on-air copy.  Falls back to the per-transmission wire ``packet_hash``
    when ``event_hash`` is NULL (legacy rows captured before the column
    existed, or unclassified packets that didn't trigger a structured
    handler).
    """
    if not hops:
        return None
    first = hops[0]
    return first.get("event_hash") or first.get("packet_hash")


def _subsequence_indices(
    path: list[dict[str, Any]],
    expected: list[str],
    max_hop_span: Optional[int] = None,
) -> Optional[tuple[int, int]]:
    """Two-pointer subsequence prefix match with gaps allowed.

    Each entry in *path* is a dict with ``position`` and ``node_hash``.
    *expected* is the ordered list of uppercase hash prefixes to find.
    A hop matches when ``node_hash.startswith(expected_hash)``.
    ``max_hop_span`` constrains ``position(last) - position(first)`` when set.

    Returns the ``(first_i, last_i)`` indices into *path* of the matched
    endpoints, or ``None`` when no match is found.
    """
    if not expected:
        return None
    pi = 0
    first_i: Optional[int] = None
    last_i: Optional[int] = None
    first_pos: Optional[int] = None
    last_pos: Optional[int] = None
    for needed in expected:
        found = False
        while pi < len(path):
            i = pi
            hop = path[pi]
            pi += 1
            if hop["node_hash"].startswith(needed):
                pos = hop["position"]
                if first_i is None:
                    first_i = i
                    first_pos = pos
                last_i = i
                last_pos = pos
                found = True
                break
        if not found:
            return None
    if max_hop_span is not None and first_pos is not None and last_pos is not None:
        if last_pos - first_pos > max_hop_span:
            return None
    if first_i is not None and last_i is not None:
        return (first_i, last_i)
    return None


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
    return _subsequence_indices(path, expected, max_hop_span) is not None


def _matched_subpath(
    hops: list[dict[str, Any]],
    expected: list[str],
    max_hop_span: Optional[int] = None,
    reversible: bool = True,
) -> Optional[list[dict[str, Any]]]:
    """Return the slice of *hops* between the first and last matched node.

    Forward match is tried first; if *reversible* and the expected sequence
    has > 1 node, the reverse-ordered match is also tried.  Returns ``None``
    when no match is found.  The returned slice is in packet-traversal order
    (never reversed), so a reverse-direction packet shows as To -> ... -> From.
    """
    subpath, _first, _last = _matched_subpath_with_indices(
        hops, expected, max_hop_span, reversible
    )
    return subpath


def _matched_subpath_with_indices(
    hops: list[dict[str, Any]],
    expected: list[str],
    max_hop_span: Optional[int] = None,
    reversible: bool = True,
) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int]]:
    """Variant of :func:`_matched_subpath` that also returns match indices.

    Returns ``(subpath, first_index, last_index)`` where ``first_index`` and
    ``last_index`` are the inclusive positions into *hops* of the matched
    slice. On no match, returns ``(None, None, None)``. The indices power
    the persisted ``first_position`` / ``last_position`` columns in
    ``route_recent_matches`` so the detail page can slice the live hop
    list without re-running the matcher.
    """
    idx = _subsequence_indices(hops, expected, max_hop_span)
    if idx is not None:
        return hops[idx[0] : idx[1] + 1], idx[0], idx[1]
    if reversible and len(expected) > 1:
        idx = _subsequence_indices(hops, list(reversed(expected)), max_hop_span)
        if idx is not None:
            return hops[idx[0] : idx[1] + 1], idx[0], idx[1]
    return None, None, None


def _match_hops(
    hops: list[dict[str, Any]],
    expected: list[str],
    max_hop_span: Optional[int] = None,
    reversible: bool = True,
) -> bool:
    """Check whether *hops* match *expected* forward (and optionally reverse)."""
    return _matched_subpath(hops, expected, max_hop_span, reversible) is not None


def _fetch_candidate_paths_maybe_bidirectional(
    session: Session,
    expected: list[str],
    since: datetime,
    observer_ids: Optional[list[str]] = None,
    reversible: bool = True,
    until: Optional[datetime] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch candidate paths from one or both endpoints of *expected*."""
    paths = fetch_candidate_paths(
        session, expected[0], since, observer_ids, until=until
    )
    if reversible and len(expected) > 1 and expected[-1] != expected[0]:
        for rp_id, hops in fetch_candidate_paths(
            session, expected[-1], since, observer_ids, until=until
        ).items():
            if rp_id not in paths:
                paths[rp_id] = hops
    return paths


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
    until: Optional[datetime] = None,
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
    if until is not None:
        subq = subq.where(PacketPathHop.received_at < until)
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
            PacketPathHop.event_hash,
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
                "event_hash": row.event_hash,
                "received_at": row.received_at,
                "observer_node_id": row.observer_node_id,
            }
        )
    return paths


def _fetch_matching_hops(
    session: Session,
    prefixes: list[str],
    since: datetime,
    until: datetime,
    observer_ids: Optional[list[str]] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch only hops whose ``node_hash`` matches any of *prefixes*.

    Unlike :func:`fetch_candidate_paths` (which loads **all** hops for
    matching raw packets), this returns only the hops whose prefix is in
    the set.  The subsequence matcher (:func:`_subsequence_indices`) only
    inspects hops whose ``node_hash`` starts with an expected prefix, so
    filtering at the SQL level is semantically identical but returns far
    fewer rows.
    """
    prefix_ranges = []
    for prefix in dict.fromkeys(prefixes):
        prefix_end = _hex_prefix_end(prefix)
        prefix_ranges.append(
            and_(
                PacketPathHop.node_hash >= prefix,
                PacketPathHop.node_hash < prefix_end,
            )
        )

    stmt = (
        select(
            PacketPathHop.raw_packet_id,
            PacketPathHop.position,
            PacketPathHop.node_hash,
            PacketPathHop.packet_hash,
            PacketPathHop.event_hash,
            PacketPathHop.received_at,
        )
        .where(
            PacketPathHop.received_at >= since,
            PacketPathHop.received_at < until,
            or_(*prefix_ranges),
        )
        .order_by(PacketPathHop.raw_packet_id, PacketPathHop.position)
    )
    if observer_ids:
        stmt = stmt.where(PacketPathHop.observer_node_id.in_(observer_ids))

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
                "event_hash": row.event_hash,
                "received_at": row.received_at,
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
    until: Optional[datetime] = None,
) -> bool:
    """Existence check: are there ANY in-scope hops in the window?"""
    stmt = (
        select(func.count())
        .select_from(PacketPathHop)
        .where(PacketPathHop.received_at >= since)
    )
    if until is not None:
        stmt = stmt.where(PacketPathHop.received_at < until)
    if observer_ids:
        stmt = stmt.where(PacketPathHop.observer_node_id.in_(observer_ids))
    return (session.execute(stmt).scalar() or 0) > 0


def _has_any_hops_per_day(
    session: Session,
    day_starts: list[datetime],
    day_ends: list[datetime],
    observer_ids: Optional[list[str]] = None,
) -> set[date]:
    """Per-day existence check in a single GROUP BY query.

    Returns the set of dates that have at least one hop.  Replaces N
    per-day ``_has_any_hops_in_window`` calls with one query.
    """
    if not day_starts:
        return set()

    window_start = day_starts[0]
    window_end = day_ends[-1]

    day_expr = func.date(PacketPathHop.received_at)

    stmt = (
        select(day_expr)
        .where(
            PacketPathHop.received_at >= window_start,
            PacketPathHop.received_at < window_end,
        )
        .group_by(day_expr)
    )
    if observer_ids:
        stmt = stmt.where(PacketPathHop.observer_node_id.in_(observer_ids))

    result: set[date] = set()
    for row in session.execute(stmt).all():
        day_val = row[0]
        if isinstance(day_val, date):
            result.add(day_val)
        else:
            result.add(date.fromisoformat(str(day_val)))
    return result


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

    reversible = getattr(route, "reversible", True)
    paths = _fetch_candidate_paths_maybe_bidirectional(
        session, expected, since, observer_ids, reversible
    )

    eff_clear = effective_clear_threshold(route)

    matched_packets: set[str] = set()
    for hops in paths.values():
        if _match_hops(hops, expected, route.max_hop_span, reversible):
            identity = _match_identity(hops)
            if identity:
                matched_packets.add(identity)
                if len(matched_packets) >= eff_clear:
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

    quality = derive_quality(state, matched_count, threshold, eff_clear)
    return state, quality, matched_count


def evaluate_route_day(
    session: Session,
    route: Route,
    day_start: datetime,
    day_end: datetime,
) -> tuple[str, str, int]:
    """Evaluate a single route for a bounded day window ``[day_start, day_end)``.

    Mirrors :func:`evaluate_route` exactly but bounds the candidate fetch with
    an upper ``received_at < day_end``.  Returns ``(quality, state,
    matched_count)``.
    """
    expected = _route_expected_hashes(route)
    if len(expected) < 2:
        return RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0

    observer_ids = (
        [ro.node_id for ro in route.route_observers] if route.route_observers else None
    )

    reversible = getattr(route, "reversible", True)
    paths = _fetch_candidate_paths_maybe_bidirectional(
        session, expected, day_start, observer_ids, reversible, until=day_end
    )

    eff_clear = effective_clear_threshold(route)

    matched_packets: set[str] = set()
    for hops in paths.values():
        if _match_hops(hops, expected, route.max_hop_span, reversible):
            identity = _match_identity(hops)
            if identity:
                matched_packets.add(identity)
                if len(matched_packets) >= eff_clear:
                    return (
                        RouteQuality.CLEAR.value,
                        RouteState.HEALTHY.value,
                        len(matched_packets),
                    )

    matched_count = len(matched_packets)
    threshold = route.packet_count_threshold

    if matched_count >= threshold:
        state = RouteState.HEALTHY.value
    else:
        exists = _has_any_hops_in_window(
            session, day_start, observer_ids, until=day_end
        )
        state = RouteState.UNHEALTHY.value if exists else RouteState.NO_COVERAGE.value

    quality = derive_quality(state, matched_count, threshold, eff_clear)
    return quality, state, matched_count


def evaluate_route_history(
    session: Session,
    route: Route,
    days: int,
    *,
    include_today: bool = False,
    now: Optional[datetime] = None,
) -> list[tuple[date, str, str, int]]:
    """Evaluate a route over *days* calendar-day buckets (oldest first).

    Returns a list of ``(date, quality, state, matched_count)`` tuples.
    When *include_today* is True, an extra entry is appended whose
    ``quality``/``state``/``matched_count`` are computed via
    :func:`evaluate_route` over the route's rolling ``window_hours`` window
    (the same call used to populate ``route_result`` for the badge), so the
    rightmost chart segment matches the card's badge. The ``date`` of that
    entry is today's date — its underlying window may extend into yesterday
    when ``window_hours`` > time elapsed since UTC midnight. Historical
    segments remain UTC calendar-day buckets. For a disabled route, every
    day returns ``unknown`` / ``no_coverage`` / ``0`` without hitting the DB.

    Performance: fetches only hops matching the route's expected prefixes
    (one DB query) plus one GROUP BY existence check, then partitions by
    day in Python. When *include_today* is True, an additional bounded
    ``evaluate_route`` call is made for the rolling-window segment.
    """
    current = now or datetime.now(timezone.utc)
    today_midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)

    total_days = days + (1 if include_today else 0)
    oldest = today_midnight - timedelta(days=days)
    day_dates = [(oldest + timedelta(days=i)).date() for i in range(total_days)]

    if not route.enabled:
        return [
            (
                day_dates[i],
                RouteQuality.UNKNOWN.value,
                RouteState.NO_COVERAGE.value,
                0,
            )
            for i in range(total_days)
        ]

    expected = _route_expected_hashes(route)
    if len(expected) < 2:
        return [
            (
                day_dates[i],
                RouteQuality.UNKNOWN.value,
                RouteState.NO_COVERAGE.value,
                0,
            )
            for i in range(total_days)
        ]

    # Compute day boundaries
    day_starts: list[datetime] = []
    day_ends: list[datetime] = []
    for i in range(total_days):
        if include_today and i == total_days - 1:
            day_starts.append(today_midnight)
            day_ends.append(current)
        else:
            ds = oldest + timedelta(days=i)
            day_starts.append(ds)
            day_ends.append(ds + timedelta(days=1))

    window_start = day_starts[0]
    window_end = day_ends[-1]

    observer_ids = (
        [ro.node_id for ro in route.route_observers] if route.route_observers else None
    )
    reversible = getattr(route, "reversible", True)

    # --- Filtered fetch: only hops matching the route's prefixes ---
    # _subsequence_indices only inspects hops whose node_hash starts with
    # an expected prefix, so filtering at SQL level is semantically
    # identical but returns far fewer rows than loading all hops for
    # matching raw packets.
    all_paths = _fetch_matching_hops(
        session, expected, window_start, window_end, observer_ids
    )

    # --- Per-day existence (UNHEALTHY vs NO_COVERAGE) ---
    day_has_hops = _has_any_hops_per_day(session, day_starts, day_ends, observer_ids)

    # --- Partition packets by day in Python ---
    # A packet qualifies for a day if it has at least one hop whose
    # node_hash matches the route's first or last prefix AND received_at
    # falls within that day's [start, end) range.
    first_prefix = expected[0]
    first_prefix_end = _hex_prefix_end(first_prefix)
    last_prefix: Optional[str] = None
    last_prefix_end: Optional[str] = None
    if reversible and len(expected) > 1 and expected[-1] != expected[0]:
        last_prefix = expected[-1]
        last_prefix_end = _hex_prefix_end(last_prefix)

    # When include_today is set, the rightmost segment is evaluated via
    # ``evaluate_route`` over the route's rolling ``window_hours`` window
    # so that it matches ``route_result.quality`` (the badge). Historical
    # segments remain UTC calendar-day buckets. We therefore partition
    # packets only into the historical indices and append today separately.
    historical_days = total_days - (1 if include_today else 0)

    day_paths: list[dict[str, list[dict[str, Any]]]] = [
        {} for _ in range(historical_days)
    ]
    for rp_id, hops in all_paths.items():
        for hop in hops:
            h = hop["node_hash"]
            ra = hop["received_at"]
            if ra.tzinfo is None:
                ra = ra.replace(tzinfo=timezone.utc)
            if not (
                first_prefix <= h < first_prefix_end
                or (last_prefix is not None and last_prefix <= h < last_prefix_end)
            ):
                continue
            for i in range(historical_days):
                if day_starts[i] <= ra < day_ends[i]:
                    if rp_id not in day_paths[i]:
                        day_paths[i][rp_id] = hops
                    break

    # --- Evaluate each historical day (CPU-only, no DB) ---
    eff_clear = effective_clear_threshold(route)
    threshold = route.packet_count_threshold

    results: list[tuple[date, str, str, int]] = []
    for i in range(historical_days):
        matched_packets: set[str] = set()
        for hops in day_paths[i].values():
            if _match_hops(hops, expected, route.max_hop_span, reversible):
                identity = _match_identity(hops)
                if identity:
                    matched_packets.add(identity)
                    if len(matched_packets) >= eff_clear:
                        break

        matched_count = len(matched_packets)
        if matched_count >= threshold:
            state = RouteState.HEALTHY.value
        elif day_has_hops and day_dates[i] in day_has_hops:
            state = RouteState.UNHEALTHY.value
        else:
            state = RouteState.NO_COVERAGE.value

        quality = derive_quality(state, matched_count, threshold, eff_clear)
        results.append((day_dates[i], quality, state, matched_count))

    # --- Today segment: rolling window, same call as the badge evaluator ---
    if include_today:
        rolling_start = current - timedelta(hours=route.window_hours)
        today_state, today_quality, today_matched = evaluate_route(
            session, route, rolling_start
        )
        results.append((day_dates[-1], today_quality, today_state, today_matched))

    return results


# Thresholds for ``compute_average_quality`` — kept in sync with the
# ``averageTier`` helper in ``web/static/js/charts.js`` so the server-side
# rolling-average badge matches the chart's per-route line color.
AVERAGE_QUALITY_CLEAR_AT = 1.5
AVERAGE_QUALITY_MARGINAL_AT = 0.75


def compute_average_quality(
    history: list[tuple[date, str, str, int]],
    *,
    fallback: Optional[str] = None,
) -> str:
    """Average per-day quality over a history window.

    Maps each day's quality onto a 0/1/2 scale (failing < marginal < clear);
    ``no_coverage`` / ``unknown`` / ``disabled`` / ``None`` all collapse to
    0, matching the merged-3-tier design used by the dashboard trend chart.
    Returns ``clear`` / ``marginal`` / ``failing`` based on the mean:

        mean >= 1.5  -> clear
        mean >= 0.75 -> marginal
        else         -> failing

    Empty history returns *fallback* (or ``"failing"`` if also ``None``) so
    brand-new routes don't flash a misleading failing badge before their
    first evaluation cycle.
    """
    if not history:
        return fallback or RouteQuality.FAILING.value

    total = 0.0
    for _d, quality, _s, _c in history:
        if quality == RouteQuality.CLEAR.value:
            total += 2.0
        elif quality == RouteQuality.MARGINAL.value:
            total += 1.0
        # failing / unknown / no_coverage / disabled / None -> 0

    mean = total / len(history)
    if mean >= AVERAGE_QUALITY_CLEAR_AT:
        return RouteQuality.CLEAR.value
    if mean >= AVERAGE_QUALITY_MARGINAL_AT:
        return RouteQuality.MARGINAL.value
    return RouteQuality.FAILING.value


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
            logger.exception(
                "Error evaluating route '%s -> %s'", route.from_label, route.to_label
            )
    return results


def upsert_route_result(
    session: Session,
    route: Route,
    state: str,
    quality: str,
    matched_count: int,
    *,
    quality_avg: Optional[str] = None,
) -> RouteResult:
    """Upsert a route evaluation result (ORM check-then-update/insert).

    ``quality_avg`` is only written when explicitly provided (non-``None``).
    Callers that don't compute it leave the previous persisted value
    intact, which keeps the background snapshot path cheap while letting
    the API layer's synchronous re-evaluation on mutations refresh every
    field at once.

    The top-N recent matches are persisted separately in
    ``route_recent_matches`` via :func:`upsert_route_recent_matches`.
    """
    now = datetime.now(timezone.utc)
    eff_clear = effective_clear_threshold(route)

    existing = session.execute(
        select(RouteResult).where(RouteResult.route_id == route.id)
    ).scalar_one_or_none()

    if existing:
        existing.state = state
        existing.quality = quality
        existing.matched_count = matched_count
        existing.threshold = route.packet_count_threshold
        existing.effective_clear = eff_clear
        existing.evaluated_at = now
        if quality_avg is not None:
            existing.quality_avg = quality_avg
        return existing

    result = RouteResult(
        id=str(uuid4()),
        route_id=route.id,
        state=state,
        quality=quality,
        matched_count=matched_count,
        threshold=route.packet_count_threshold,
        effective_clear=eff_clear,
        evaluated_at=now,
        quality_avg=quality_avg,
    )
    session.add(result)
    return result


def upsert_route_history_row(
    session: Session,
    route_id: str,
    day: date,
    quality: str,
    state: str,
    matched_count: int,
    *,
    evaluated_at: Optional[datetime] = None,
) -> RouteResultHistory:
    """Upsert one calendar-day bucket into ``route_result_history``.

    Idempotent via the ``UNIQUE (route_id, date)`` constraint — a
    re-evaluation of the same day overwrites the prior row in place.
    """
    now = evaluated_at or datetime.now(timezone.utc)

    existing = session.execute(
        select(RouteResultHistory)
        .where(RouteResultHistory.route_id == route_id)
        .where(RouteResultHistory.date == day)
    ).scalar_one_or_none()

    if existing:
        existing.quality = quality
        existing.state = state
        existing.matched_count = matched_count
        existing.evaluated_at = now
        return existing

    row = RouteResultHistory(
        id=str(uuid4()),
        route_id=route_id,
        date=day,
        quality=quality,
        state=state,
        matched_count=matched_count,
        evaluated_at=now,
    )
    session.add(row)
    return row


def compute_persisted_quality_avg(
    session: Session,
    route: Route,
    *,
    today_quality: str,
    now: Optional[datetime] = None,
    days: int = 7,
) -> Optional[str]:
    """Rolling ``days``-day average tier from persisted history + today's snapshot.

    Reads the last ``days`` history rows for completed UTC calendar days
    (strictly before today), appends today's rolling-window ``quality``
    (the same value the badge uses, sourced from the latest
    ``evaluate_route`` call), and feeds both to ``compute_average_quality``.
    Returns ``None`` when no history exists and no today quality is
    available, so brand-new routes don't flash a misleading failing badge
    before the first evaluator cycle.
    """
    current = now or datetime.now(timezone.utc)
    today = current.date()

    if not today_quality:
        return None

    rows = session.execute(
        select(
            RouteResultHistory.date,
            RouteResultHistory.quality,
            RouteResultHistory.state,
            RouteResultHistory.matched_count,
        )
        .where(RouteResultHistory.route_id == route.id)
        .where(RouteResultHistory.date < today)
        .order_by(RouteResultHistory.date.desc())
        .limit(days)
    ).all()

    history_tuples: list[tuple[date, str, str, int]] = [
        (row.date, row.quality, row.state, row.matched_count) for row in reversed(rows)
    ]
    history_tuples.append((today, today_quality, "", 0))

    if not history_tuples:
        return None
    if not rows:
        # Brand-new route: no historical buckets yet. Return None so the
        # frontend's ``quality_avg || route_result?.quality`` fallback
        # kicks in (matches the historical "fresh route" semantics).
        return None
    return compute_average_quality(history_tuples, fallback=today_quality)


def read_route_history_from_db(
    session: Session,
    route: Route,
    days: int,
    *,
    include_today: bool = True,
    now: Optional[datetime] = None,
) -> list[tuple[date, str, str, int]]:
    """Read precomputed history for a route from ``route_result_history``.

    Replaces the on-demand ``evaluate_route_history`` call on the API hot
    path with a single indexed ``SELECT``. Pads missing days with
    ``unknown`` / ``no_coverage`` / ``0`` (matching the disabled-route
    semantics the chart already relies on). When *include_today* is True,
    appends a synthetic today segment sourced from ``route.route_result``
    (the rolling-window snapshot the badge uses) so the rightmost chart
    point stays consistent with the card badge.

    For a disabled route, every entry returns ``unknown`` /
    ``no_coverage`` / ``0`` without hitting the DB.
    """
    current = now or datetime.now(timezone.utc)
    today_midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    today = current.date()
    oldest = today_midnight - timedelta(days=days)
    day_dates = [(oldest + timedelta(days=i)).date() for i in range(days)]

    if not route.enabled:
        results: list[tuple[date, str, str, int]] = [
            (d, RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0)
            for d in day_dates
        ]
        if include_today:
            results.append(
                (today, RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0)
            )
        return results

    rows = session.execute(
        select(
            RouteResultHistory.date,
            RouteResultHistory.quality,
            RouteResultHistory.state,
            RouteResultHistory.matched_count,
        )
        .where(RouteResultHistory.route_id == route.id)
        .where(RouteResultHistory.date >= oldest.date())
        .where(RouteResultHistory.date < today)
        .order_by(RouteResultHistory.date)
    ).all()
    rows_by_date: dict[date, tuple[str, str, int]] = {
        row.date: (row.quality, row.state, row.matched_count) for row in rows
    }

    results = [
        (
            d,
            *rows_by_date.get(
                d, (RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0)
            ),
        )
        for d in day_dates
    ]

    if include_today:
        rr = route.route_result
        if rr is not None:
            results.append((today, rr.quality, rr.state, rr.matched_count))
        else:
            results.append(
                (today, RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0)
            )

    return results


def _legacy_recent_matches_payload(
    matches: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adapter from the new ``recent_matches`` dict shape to the legacy
    ``RecentMatchPath(**m)`` schema expected by the detail-page response.

    The new ``recent_matches`` carries ``raw_packet_id`` / ``first_position``
    / ``last_position`` (for the normalized table) instead of a pre-sliced
    ``hops`` list. The detail-page read path JOINs through
    ``route_recent_matches`` to load hops live, so this shim only exists
    for the rare path where the evaluator hasn't populated the table yet
    and we fall back to a live compute.
    """
    out: list[dict[str, Any]] = []
    for m in matches:
        out.append(
            {
                "packet_hash": m.get("packet_hash"),
                "event_hash": m.get("event_hash"),
                "received_at": m.get("received_at"),
                "observer_node_id": m.get("observer_node_id"),
                "hops": [],  # populated by the caller via packet_path_hops
            }
        )
    return out


# ---------------------------------------------------------------------------
# Card expand + preview
# ---------------------------------------------------------------------------


def recent_matches(
    session: Session,
    route: Route,
    limit: int = 3,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Return metadata for the latest *limit* matching receptions for a route.

    Each dict carries the keys the evaluator needs to persist a
    ``RouteRecentMatch`` row and the API needs to render the detail-page
    match card: ``raw_packet_id``, ``packet_hash``, ``event_hash``,
    ``received_at``, ``observer_node_id``, ``first_position``,
    ``last_position``. The matched hop slice is NOT included — callers
    that need the hops (i.e. the API detail endpoint) JOIN through
    ``raw_packet_id`` → ``packet_path_hops`` and slice on
    ``[first_position .. last_position]`` so the data is sourced from
    its canonical home instead of being denormalized at sweep time.

    Deduplicates by event identity (preferring ``event_hash``, falling back
    to wire ``packet_hash``) so the UI shows one row per underlying event
    rather than one row per retransmission. When multiple receptions share
    an identity, the newest is returned.
    """
    expected = _route_expected_hashes(route)
    if len(expected) < 2:
        return []

    observer_ids = (
        [ro.node_id for ro in route.route_observers] if route.route_observers else None
    )
    current = now or datetime.now(timezone.utc)
    since = current - timedelta(hours=route.window_hours)

    reversible = getattr(route, "reversible", True)
    paths = _fetch_candidate_paths_maybe_bidirectional(
        session, expected, since, observer_ids, reversible
    )

    # Keep the newest match per identity so the UI lists distinct underlying
    # events rather than every retransmission of the same event.
    matches_by_identity: dict[str, dict[str, Any]] = {}
    for rp_id, hops in paths.items():
        subpath, first_idx, last_idx = _matched_subpath_with_indices(
            hops, expected, route.max_hop_span, reversible
        )
        if not subpath or first_idx is None or last_idx is None:
            continue
        identity = _match_identity(subpath)
        if identity is None:
            # Fall back to a synthetic unique key so unmatched-identity
            # receptions still surface (one row each).
            identity = f"__rawid_{id(subpath)}"
        first = subpath[0]
        received_at = first.get("received_at") or datetime.min.replace(
            tzinfo=timezone.utc
        )
        candidate = {
            "raw_packet_id": rp_id,
            "packet_hash": first.get("packet_hash"),
            "event_hash": first.get("event_hash"),
            "received_at": first.get("received_at"),
            "observer_node_id": first.get("observer_node_id"),
            "first_position": first_idx,
            "last_position": last_idx,
        }
        existing = matches_by_identity.get(identity)
        if existing is None or received_at > (
            existing.get("received_at") or datetime.min.replace(tzinfo=timezone.utc)
        ):
            matches_by_identity[identity] = candidate

    matches = sorted(
        matches_by_identity.values(),
        key=lambda m: m["received_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return matches[:limit]


def upsert_route_recent_matches(
    session: Session,
    route_id: str,
    matches: Iterable[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[RouteRecentMatch]:
    """Replace the route's recent-match set with *matches* (capped at *limit*).

    ``matches`` is the output of :func:`recent_matches`. Rows whose
    ``raw_packet_id`` is no longer in the new set are deleted; new and
    changed rows are upserted in place. Returns the resulting ORM rows
    (sorted newest-first by ``raw_packet_id`` for caller convenience;
    order is not persisted — the detail page orders by
    ``raw_packets.received_at`` at read time).

    Cap is enforced at write time as a safety net — :func:`recent_matches`
    already LIMITs.
    """
    new_matches = list(matches)[:limit]
    new_packet_ids = {m["raw_packet_id"] for m in new_matches}

    existing_rows = (
        session.execute(
            select(RouteRecentMatch).where(RouteRecentMatch.route_id == route_id)
        )
        .scalars()
        .all()
    )
    existing_by_packet = {r.raw_packet_id: r for r in existing_rows}

    # Delete rows whose raw_packet_id is no longer in the new set
    for row in existing_rows:
        if row.raw_packet_id not in new_packet_ids:
            session.delete(row)

    # Upsert new / changed
    kept: list[RouteRecentMatch] = []
    for m in new_matches:
        rpid = m["raw_packet_id"]
        existing: Optional[RouteRecentMatch] = existing_by_packet.get(rpid)
        first_pos = m["first_position"]
        last_pos = m["last_position"]
        if existing is None:
            existing = RouteRecentMatch(
                id=str(uuid4()),
                route_id=route_id,
                raw_packet_id=rpid,
                first_position=first_pos,
                last_position=last_pos,
            )
            session.add(existing)
        else:
            existing.first_position = first_pos
            existing.last_position = last_pos
        kept.append(existing)
    return kept


def preview_route(
    session: Session,
    config: dict[str, Any],
    since: datetime,
) -> dict[str, Any]:
    """Preview matching for an unsaved route config.

    *config* keys: ``node_ids``, ``match_width``, ``observer_ids``,
    ``max_hop_span``, ``packet_count_threshold``, ``clear_threshold``,
    ``reversible``.
    """
    node_ids: list[str] = config.get("node_ids") or []
    match_width: int = config.get("match_width") or 1
    observer_ids: Optional[list[str]] = config.get("observer_ids") or None
    max_hop_span: Optional[int] = config.get("max_hop_span")
    threshold: int = config.get("packet_count_threshold") or 5
    clear_bar: Optional[int] = config.get("clear_threshold")
    reversible: bool = config.get("reversible", True)

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
    if reversible and len(expected) > 1 and expected[-1] != expected[0]:
        candidate_count += _count_candidate_receptions(
            session, expected[-1], since, observer_ids
        )
    if candidate_count > PREVIEW_CANDIDATE_CAP:
        return {
            "matched_count": None,
            "quality": None,
            "truncated": True,
            "candidate_count": candidate_count,
        }

    paths = _fetch_candidate_paths_maybe_bidirectional(
        session, expected, since, observer_ids, reversible
    )

    eff_clear = clear_bar or (threshold * CLEAR_DEFAULT_MULTIPLIER)

    matched_packets: set[str] = set()
    contributing: dict[str, int] = {}

    for hops in paths.values():
        if _match_hops(hops, expected, max_hop_span, reversible):
            identity = _match_identity(hops)
            if identity:
                matched_packets.add(identity)
            obs = hops[0]["observer_node_id"]
            if obs:
                contributing[obs] = contributing.get(obs, 0) + 1

    matched_count = len(matched_packets)

    if matched_count >= threshold:
        state = RouteState.HEALTHY.value
    else:
        exists = _has_any_hops_in_window(session, since, observer_ids)
        state = RouteState.UNHEALTHY.value if exists else RouteState.NO_COVERAGE.value

    quality = derive_quality(state, matched_count, threshold, eff_clear)

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
