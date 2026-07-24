"""Route health monitoring API routes."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from meshcore_hub.api.auth import RequireOperatorOrAdmin, RequireRead, X_USER_ID_HEADER
from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.api.cache_invalidation import invalidate_routes
from meshcore_hub.api.channel_visibility import (
    VISIBILITY_LEVELS,
    get_max_visibility_level,
    resolve_user_role,
)
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.profile_utils import get_or_create_profile
from meshcore_hub.collector.routes import (
    compute_persisted_quality_avg,
    derive_expected_hash,
    evaluate_route,
    preview_route,
    read_route_history_from_db,
    recent_matches,
    upsert_route_recent_matches,
    upsert_route_result,
)
from meshcore_hub.common.config import get_collector_settings
from meshcore_hub.common.models.node import Node
from meshcore_hub.common.models.packet_path_hop import PacketPathHop
from meshcore_hub.common.models.raw_packet import RawPacket
from meshcore_hub.common.models.route import Route
from meshcore_hub.common.models.route_node import RouteNode
from meshcore_hub.common.models.route_observer import RouteObserver
from meshcore_hub.common.models.route_recent_match import RouteRecentMatch
from meshcore_hub.common.models.route_result import RouteResult
from meshcore_hub.common.models.user_profile import UserProfile
from meshcore_hub.common.schemas.routes import (
    ContributingObserver,
    RecentMatchPath,
    RouteCreate,
    RouteDetail,
    RouteDayQuality,
    RouteHistory,
    RouteList,
    RouteNodeRead,
    RouteObserverRead,
    RouteOwner,
    RoutePreviewRequest,
    RoutePreviewResponse,
    RouteRead,
    RouteResultSummary,
    RouteUpdate,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Sentinel distinguishing "use the precomputed value" from "explicitly None"
# (the latter is what create_route passes to preserve the "brand-new route
# has no meaningful average yet" semantics on the POST response).
_UNSET = object()


def _routes_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"{request.url.path}:role={role}:{sorted_query_string(request)}"


def _caller_max_visibility_level(request: Request) -> int:
    """Max visibility tier the current caller may set or modify.

    Operators can manage routes at or below the operator tier; admins at or
    below the admin tier. This is the same role resolution the read handlers
    use, so read and write visibility stay consistent.
    """
    return get_max_visibility_level(resolve_user_role(request))


def _assert_visibility_within_role(request: Request, visibility: str) -> None:
    """Reject a visibility value above the caller's own role tier.

    Stops a user scoping a route to a role they could then never see or
    modify (e.g. an operator creating an admin-visibility route).
    """
    if VISIBILITY_LEVELS.get(visibility, 0) > _caller_max_visibility_level(request):
        raise HTTPException(
            status_code=403,
            detail="Cannot set route visibility above your own role",
        )


def _assert_route_modifiable(request: Request, route: Route) -> None:
    """Reject modifying a route the caller is not allowed to touch.

    Layer 1 — visibility: a route above the caller's tier yields **404**
    so its existence is not leaked (mirrors GET detail behaviour).

    Layer 2 — ownership: operators may only modify routes *they* created.
    A visible-but-unowned route yields **403** (the caller can see it in
    the list, so a transparent rejection is better UX).  ``created_by``
    is ``None`` for legacy routes (pre-ownership-tracking) and is treated
    as admin-only.  Admins bypass the ownership check entirely.
    """
    if VISIBILITY_LEVELS.get(route.visibility, 0) > _caller_max_visibility_level(
        request
    ):
        raise HTTPException(status_code=404, detail="Route not found")
    if resolve_user_role(request) != "admin":
        caller_id = request.headers.get(X_USER_ID_HEADER, "")
        if route.created_by is None or route.created_by != caller_id:
            raise HTTPException(
                status_code=403,
                detail="You can only modify routes you created",
            )


def _route_node_to_read(rn: RouteNode) -> RouteNodeRead:
    return RouteNodeRead(
        node_id=rn.node_id,
        position=rn.position,
        expected_hash=rn.expected_hash,
        name=rn.node.name if rn.node else None,
        public_key=rn.node.public_key if rn.node else None,
    )


def _route_observer_to_read(ro: RouteObserver) -> RouteObserverRead:
    return RouteObserverRead(
        node_id=ro.node_id,
        name=ro.node.name if ro.node else None,
        public_key=ro.node.public_key if ro.node else None,
    )


def _result_to_summary(result: RouteResult | None) -> RouteResultSummary | None:
    if result is None:
        return None
    return RouteResultSummary(
        state=result.state,
        quality=result.quality,
        matched_count=result.matched_count,
        threshold=result.threshold,
        effective_clear=result.effective_clear,
        evaluated_at=result.evaluated_at,
    )


def _profile_to_owner(profile: UserProfile) -> RouteOwner:
    """Convert a UserProfile to the lightweight RouteOwner display schema."""
    return RouteOwner(
        user_id=profile.user_id,
        name=profile.name,
        callsign=profile.callsign,
        profile_id=profile.id,
    )


def _resolve_owner(session: DbSession, created_by: str | None) -> UserProfile | None:
    """Resolve a single ``created_by`` user_id to a UserProfile."""
    if not created_by:
        return None
    return session.execute(
        select(UserProfile).where(UserProfile.user_id == created_by)
    ).scalar_one_or_none()


def _resolve_owners_batch(
    session: DbSession, routes: list[Route]
) -> dict[str, UserProfile]:
    """Batch-resolve creator profiles for a list of routes (avoids N+1)."""
    owner_ids = {r.created_by for r in routes if r.created_by}
    if not owner_ids:
        return {}
    return {
        p.user_id: p
        for p in session.execute(
            select(UserProfile).where(UserProfile.user_id.in_(owner_ids))
        )
        .scalars()
        .all()
    }


def _route_to_read(
    route: Route,
    *,
    quality_avg: Any = _UNSET,
    owner: UserProfile | None = None,
) -> RouteRead:
    """Serialize a Route to its list-level read schema.

    ``quality_avg`` defaults to the precomputed value persisted on
    ``route.route_result.quality_avg`` (written by the background
    evaluator). Callers may pass an explicit value (e.g. ``None`` on
    create responses) to override.

    ``owner`` is the resolved UserProfile for ``route.created_by``, if
    any.  Callers should pass it in to avoid per-row queries in list
    contexts (use ``_resolve_owners_batch``).
    """
    if quality_avg is _UNSET:
        quality_avg = route.route_result.quality_avg if route.route_result else None
    return RouteRead(
        id=route.id,
        from_label=route.from_label,
        to_label=route.to_label,
        description=route.description,
        visibility=route.visibility,
        match_width=route.match_width,
        window_hours=route.window_hours,
        packet_count_threshold=route.packet_count_threshold,
        clear_threshold=route.clear_threshold,
        max_hop_span=route.max_hop_span,
        max_path_length=route.max_path_length,
        enabled=route.enabled,
        reversible=route.reversible,
        route_nodes=[_route_node_to_read(rn) for rn in route.route_nodes],
        route_observers=[_route_observer_to_read(ro) for ro in route.route_observers],
        route_result=_result_to_summary(route.route_result),
        quality_avg=quality_avg,
        created_by=route.created_by,
        owner=_profile_to_owner(owner) if owner else None,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def _resolve_nodes_by_pubkey(session: DbSession, public_keys: list[str]) -> list[Node]:
    """Resolve node public keys to Node objects, preserving input order."""
    lowered = [pk.strip().lower() for pk in public_keys]
    nodes_by_key = {
        n.public_key: n
        for n in session.execute(select(Node).where(Node.public_key.in_(lowered)))
        .scalars()
        .all()
    }
    return [nodes_by_key[k] for k in lowered if k in nodes_by_key]


def _sync_path_nodes(session: DbSession, route: Route, nodes: list[Node]) -> None:
    """Replace all RouteNode children wholesale."""
    for rn in list(route.route_nodes):
        session.delete(rn)
    session.flush()
    for pos, node in enumerate(nodes):
        session.add(
            RouteNode(
                route_id=route.id,
                node_id=node.id,
                position=pos,
                expected_hash=derive_expected_hash(node.public_key, route.match_width),
            )
        )


def _sync_observers(
    session: DbSession, route: Route, observer_nodes: list[Node]
) -> None:
    """Replace all RouteObserver children wholesale."""
    for ro in list(route.route_observers):
        session.delete(ro)
    session.flush()
    for node in observer_nodes:
        session.add(RouteObserver(route_id=route.id, node_id=node.id))


def _reevaluate_route(session: DbSession, route: Route) -> None:
    """Synchronously evaluate *route* and persist every derived field.

    The background evaluator (collector.route_evaluator) writes
    ``RouteResult`` on a schedule (default 60s). Without this synchronous
    re-eval, the route's ``packet_count_threshold`` / ``clear_threshold``
    changes take up to that interval to surface in the UI — the list card
    displays ``route_result.threshold`` / ``effective_clear``, not the
    route's just-updated direct fields, so it shows the stale snapshot
    until the next evaluator cycle. Running the eval inline on every
    create/update keeps the post-mutation GET consistent with the new
    config at the cost of one bounded DB scan per write.

    Refreshes the current snapshot, the persisted top-3 recent matches
    (so the detail page is fresh), and the rolling ``quality_avg`` (so
    the list/detail badge updates immediately when the snapshot tier
    changes).
    """
    if not route.enabled:
        return
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=route.window_hours)
    state, quality, matched_count = evaluate_route(session, route, since)

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
    session.commit()
    session.refresh(route)


@router.get("", response_model=RouteList)
@cached("routes", key_builder=_routes_key_builder)
def list_routes(
    _: RequireRead,
    session: DbSession,
    request: Request,
) -> RouteList:
    """List routes, filtered by user role visibility."""
    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)

    routes = session.execute(select(Route).order_by(Route.from_label)).scalars().all()
    visible = [r for r in routes if VISIBILITY_LEVELS.get(r.visibility, 0) <= max_level]
    owners_by_id = _resolve_owners_batch(session, visible)
    filtered = [
        _route_to_read(
            r, owner=owners_by_id.get(r.created_by) if r.created_by else None
        )
        for r in visible
    ]
    return RouteList(items=filtered, total=len(filtered))


@router.post("", response_model=RouteRead, status_code=201)
def create_route(
    caller: RequireOperatorOrAdmin,
    session: DbSession,
    body: RouteCreate,
    request: Request,
) -> RouteRead:
    """Create a new route (operator or admin)."""
    user_id, _ = caller
    get_or_create_profile(session, user_id, request)
    _assert_visibility_within_role(request, body.visibility)
    existing = session.execute(
        select(Route).where(
            Route.from_label == body.from_label,
            Route.to_label == body.to_label,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Route '{body.from_label}' -> '{body.to_label}' already exists",
        )

    nodes = _resolve_nodes_by_pubkey(session, body.node_public_keys)
    if len(nodes) < 2:
        raise HTTPException(status_code=400, detail="Could not resolve >= 2 path nodes")

    observer_nodes = (
        _resolve_nodes_by_pubkey(session, body.observer_public_keys)
        if body.observer_public_keys
        else []
    )

    route = Route(
        from_label=body.from_label,
        to_label=body.to_label,
        description=body.description,
        visibility=body.visibility,
        match_width=body.match_width,
        window_hours=body.window_hours,
        packet_count_threshold=body.packet_count_threshold,
        clear_threshold=body.clear_threshold,
        max_hop_span=body.max_hop_span,
        max_path_length=body.max_path_length,
        enabled=body.enabled,
        reversible=body.reversible,
        created_by=user_id,
    )
    session.add(route)
    session.flush()
    _sync_path_nodes(session, route, nodes)
    _sync_observers(session, route, observer_nodes)
    session.commit()
    session.refresh(route)
    _reevaluate_route(session, route)
    invalidate_routes(request)
    owner = _resolve_owner(session, route.created_by)
    return _route_to_read(route, quality_avg=None, owner=owner)


@router.get("/{route_id}", response_model=RouteDetail)
@cached(
    "routes/{id}",
    ttl_setting="redis_cache_ttl_dashboard",
    key_builder=_routes_key_builder,
)
def get_route(
    _: RequireRead,
    session: DbSession,
    route_id: str,
    request: Request,
) -> RouteDetail:
    """Get full route detail with contributing observers and recent matches."""
    route = session.execute(
        select(Route).where(Route.id == route_id)
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    if VISIBILITY_LEVELS.get(route.visibility, 0) > max_level:
        raise HTTPException(status_code=404, detail="Route not found")

    matches = _load_recent_matches(session, route)

    contributing: dict[str, int] = {}
    for m in matches:
        obs = m.get("observer_node_id")
        if obs:
            contributing[obs] = contributing.get(obs, 0) + 1

    obs_ids = list(contributing.keys())
    obs_nodes = (
        {
            n.id: n
            for n in session.execute(select(Node).where(Node.id.in_(obs_ids)))
            .scalars()
            .all()
        }
        if obs_ids
        else {}
    )

    contributors = [
        ContributingObserver(
            node_id=oid,
            name=obs_nodes[oid].name if oid in obs_nodes else None,
            match_count=cnt,
        )
        for oid, cnt in contributing.items()
    ]

    read = _route_to_read(route, owner=_resolve_owner(session, route.created_by))
    return RouteDetail(
        **read.model_dump(),
        contributing_observers=contributors,
        recent_matches=[RecentMatchPath(**m) for m in matches],
    )


def _load_recent_matches(
    session: DbSession,
    route: Route,
) -> list[dict[str, Any]]:
    """Return the route's top-3 recent matches in the ``RecentMatchPath`` shape.

    Reads the normalized ``route_recent_matches`` table (populated by the
    background evaluator on every 60s tick), JOINs through ``raw_packets``
    for the packet-level metadata, then fetches the matched hop slice from
    ``packet_path_hops`` in a second indexed query and slices
    ``[first_position .. last_position]`` per match in Python. Falls back
    to a live ``recent_matches`` compute when the table is empty for the
    route (fresh route, evaluator hasn't run yet, or older row from before
    this table existed).
    """
    matches = _read_recent_matches_from_table(session, route.id)
    if matches:
        return matches
    if not route.enabled:
        return []
    # Live fallback for fresh routes — produce the same dict shape with
    # an empty hops list (the table will be populated on the next sweep).
    live = recent_matches(session, route, limit=3)
    return [
        {
            "packet_hash": m.get("packet_hash"),
            "event_hash": m.get("event_hash"),
            "received_at": m.get("received_at"),
            "observer_node_id": m.get("observer_node_id"),
            "hops": _slice_hops_for_match(
                session, m["raw_packet_id"], m["first_position"], m["last_position"]
            ),
        }
        for m in live
    ]


def _read_recent_matches_from_table(
    session: DbSession,
    route_id: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Read recent matches from ``route_recent_matches`` + ``raw_packets``.

    Returns ``[]`` when the route has no persisted matches yet.
    """
    rows = session.execute(
        select(
            RouteRecentMatch.raw_packet_id,
            RouteRecentMatch.first_position,
            RouteRecentMatch.last_position,
            RawPacket.packet_hash,
            RawPacket.event_hash,
            RawPacket.received_at,
            RawPacket.observer_node_id,
        )
        .join(RawPacket, RawPacket.id == RouteRecentMatch.raw_packet_id)
        .where(RouteRecentMatch.route_id == route_id)
        .order_by(RawPacket.received_at.desc())
        .limit(limit)
    ).all()
    if not rows:
        return []

    # One IN-query for all the hops we need.
    packet_ids = [r.raw_packet_id for r in rows]
    hop_rows = session.execute(
        select(
            PacketPathHop.raw_packet_id,
            PacketPathHop.position,
            PacketPathHop.node_hash,
            PacketPathHop.packet_hash,
            PacketPathHop.event_hash,
            PacketPathHop.received_at,
            PacketPathHop.observer_node_id,
        )
        .where(PacketPathHop.raw_packet_id.in_(packet_ids))
        .order_by(PacketPathHop.raw_packet_id, PacketPathHop.position)
    ).all()
    hops_by_packet: dict[str, list[dict[str, Any]]] = {}
    for h in hop_rows:
        hops_by_packet.setdefault(h.raw_packet_id, []).append(
            {
                "position": h.position,
                "node_hash": h.node_hash,
                "packet_hash": h.packet_hash,
                "event_hash": h.event_hash,
                "received_at": h.received_at,
                "observer_node_id": h.observer_node_id,
            }
        )

    out: list[dict[str, Any]] = []
    for r in rows:
        all_hops = hops_by_packet.get(r.raw_packet_id, [])
        sliced = all_hops[r.first_position : r.last_position + 1]
        out.append(
            {
                "packet_hash": r.packet_hash,
                "event_hash": r.event_hash,
                "received_at": r.received_at,
                "observer_node_id": r.observer_node_id,
                "hops": sliced,
            }
        )
    return out


def _slice_hops_for_match(
    session: DbSession,
    raw_packet_id: str,
    first_position: int,
    last_position: int,
) -> list[dict[str, Any]]:
    """Fetch and slice the hops for one match (live-fallback path only)."""
    rows = session.execute(
        select(
            PacketPathHop.position,
            PacketPathHop.node_hash,
            PacketPathHop.packet_hash,
            PacketPathHop.event_hash,
            PacketPathHop.received_at,
            PacketPathHop.observer_node_id,
        )
        .where(PacketPathHop.raw_packet_id == raw_packet_id)
        .order_by(PacketPathHop.position)
    ).all()
    all_hops = [
        {
            "position": r.position,
            "node_hash": r.node_hash,
            "packet_hash": r.packet_hash,
            "event_hash": r.event_hash,
            "received_at": r.received_at,
            "observer_node_id": r.observer_node_id,
        }
        for r in rows
    ]
    return all_hops[first_position : last_position + 1]


@router.get("/{route_id}/history", response_model=RouteHistory)
@cached(
    "routes/{id}/history",
    ttl_setting="redis_cache_ttl_dashboard",
    key_builder=_routes_key_builder,
)
def get_route_history(
    _: RequireRead,
    session: DbSession,
    route_id: str,
    request: Request,
    days: int = 7,
) -> RouteHistory:
    """Per-route health history over the last *days* (includes today)."""
    route = session.execute(
        select(Route).where(Route.id == route_id)
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    if VISIBILITY_LEVELS.get(route.visibility, 0) > max_level:
        raise HTTPException(status_code=404, detail="Route not found")

    retention = get_collector_settings().effective_raw_packet_retention_days
    days = min(days, retention)

    history = read_route_history_from_db(session, route, days, include_today=True)

    return RouteHistory(
        route_id=route.id,
        days=len(history),
        data=[
            RouteDayQuality(date=d, quality=q, state=s, matched_count=c)
            for d, q, s, c in history
        ],
    )


@router.put("/{route_id}", response_model=RouteRead)
def update_route(
    caller: RequireOperatorOrAdmin,
    session: DbSession,
    route_id: str,
    body: RouteUpdate,
    request: Request,
) -> RouteRead:
    """Update a route (operator or admin).

    Operators may only modify routes they created; admins can modify any
    route. Admins claim ownership of legacy (unowned) routes on edit but
    do not displace an existing creator.
    """
    user_id, _ = caller
    route = session.execute(
        select(Route).where(Route.id == route_id)
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    _assert_route_modifiable(request, route)

    # Admin claims ownership of legacy (unowned) routes on edit
    if resolve_user_role(request) == "admin" and route.created_by is None:
        route.created_by = user_id
        logger.info("Admin %s claimed ownership of legacy route %s", user_id, route.id)

    if body.from_label is not None or body.to_label is not None:
        new_from = body.from_label if body.from_label is not None else route.from_label
        new_to = body.to_label if body.to_label is not None else route.to_label
        dup = session.execute(
            select(Route).where(
                Route.from_label == new_from,
                Route.to_label == new_to,
                Route.id != route_id,
            )
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Route '{new_from}' -> '{new_to}' already exists",
            )
        route.from_label = new_from
        route.to_label = new_to

    if body.description is not None:
        route.description = body.description
    if body.visibility is not None:
        _assert_visibility_within_role(request, body.visibility)
        route.visibility = body.visibility
    if body.match_width is not None:
        route.match_width = body.match_width
    if body.window_hours is not None:
        route.window_hours = body.window_hours
    if body.packet_count_threshold is not None:
        route.packet_count_threshold = body.packet_count_threshold
    if body.clear_threshold is not None:
        route.clear_threshold = body.clear_threshold
    if body.max_hop_span is not None:
        route.max_hop_span = body.max_hop_span
    if body.max_path_length is not None:
        route.max_path_length = body.max_path_length
    if body.enabled is not None:
        route.enabled = body.enabled
    if body.reversible is not None:
        route.reversible = body.reversible

    if body.node_public_keys is not None:
        nodes = _resolve_nodes_by_pubkey(session, body.node_public_keys)
        if len(nodes) < 2:
            raise HTTPException(
                status_code=400, detail="Could not resolve >= 2 path nodes"
            )
        _sync_path_nodes(session, route, nodes)

    if body.observer_public_keys is not None:
        observer_nodes = _resolve_nodes_by_pubkey(session, body.observer_public_keys)
        _sync_observers(session, route, observer_nodes)

    session.commit()
    session.refresh(route)
    _reevaluate_route(session, route)
    invalidate_routes(request)
    owner = _resolve_owner(session, route.created_by)
    return _route_to_read(route, owner=owner)


@router.delete("/{route_id}", status_code=204)
def delete_route(
    __: RequireOperatorOrAdmin,
    session: DbSession,
    route_id: str,
    request: Request,
) -> None:
    """Delete a route (operator or admin)."""
    route = session.execute(
        select(Route).where(Route.id == route_id)
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    _assert_route_modifiable(request, route)
    session.delete(route)
    session.commit()
    invalidate_routes(request)


@router.post("/preview", response_model=RoutePreviewResponse)
def preview(
    _: RequireRead,
    session: DbSession,
    body: RoutePreviewRequest,
) -> RoutePreviewResponse:
    """Preview matching for an unsaved route config (any authenticated user)."""
    since = datetime.now(timezone.utc) - timedelta(hours=body.window_hours)

    nodes = _resolve_nodes_by_pubkey(session, body.node_public_keys)
    if len(nodes) < 2:
        return RoutePreviewResponse(
            matched_count=0,
            quality="unknown",
            state="no_coverage",
            contributing_observers={},
            collisions={},
            truncated=False,
        )

    observer_nodes = (
        _resolve_nodes_by_pubkey(session, body.observer_public_keys)
        if body.observer_public_keys
        else []
    )

    config = {
        "node_ids": [n.id for n in nodes],
        "match_width": body.match_width,
        "observer_ids": [n.id for n in observer_nodes] if observer_nodes else None,
        "max_hop_span": body.max_hop_span,
        "max_path_length": body.max_path_length,
        "packet_count_threshold": body.packet_count_threshold,
        "clear_threshold": body.clear_threshold,
        "reversible": body.reversible,
    }
    result = preview_route(session, config, since)
    return RoutePreviewResponse(**result)
