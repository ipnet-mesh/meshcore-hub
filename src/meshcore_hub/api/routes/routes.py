"""Route health monitoring API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from meshcore_hub.api.auth import RequireAdmin, RequireRead
from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.api.channel_visibility import (
    VISIBILITY_LEVELS,
    get_max_visibility_level,
    resolve_user_role,
)
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.collector.routes import (
    derive_expected_hash,
    preview_route,
    recent_matches,
)
from meshcore_hub.common.models.node import Node
from meshcore_hub.common.models.route import Route
from meshcore_hub.common.models.route_node import RouteNode
from meshcore_hub.common.models.route_observer import RouteObserver
from meshcore_hub.common.models.route_result import RouteResult
from meshcore_hub.common.schemas.routes import (
    ContributingObserver,
    RecentMatchPath,
    RouteCreate,
    RouteDetail,
    RouteList,
    RouteNodeRead,
    RouteObserverRead,
    RoutePreviewRequest,
    RoutePreviewResponse,
    RouteRead,
    RouteResultSummary,
    RouteUpdate,
)

router = APIRouter()


def _routes_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"routes:role={role}:{sorted_query_string(request)}"


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
        effective_degraded=result.effective_degraded,
        evaluated_at=result.evaluated_at,
    )


def _route_to_read(route: Route) -> RouteRead:
    return RouteRead(
        id=route.id,
        from_label=route.from_label,
        to_label=route.to_label,
        description=route.description,
        visibility=route.visibility,
        match_width=route.match_width,
        window_hours=route.window_hours,
        packet_count_threshold=route.packet_count_threshold,
        degraded_threshold=route.degraded_threshold,
        max_hop_span=route.max_hop_span,
        enabled=route.enabled,
        reversible=route.reversible,
        route_nodes=[_route_node_to_read(rn) for rn in route.route_nodes],
        route_observers=[_route_observer_to_read(ro) for ro in route.route_observers],
        route_result=_result_to_summary(route.route_result),
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
    filtered = [
        _route_to_read(r)
        for r in routes
        if VISIBILITY_LEVELS.get(r.visibility, 0) <= max_level
    ]
    return RouteList(items=filtered, total=len(filtered))


@router.post("", response_model=RouteRead, status_code=201)
def create_route(
    __: RequireAdmin,
    session: DbSession,
    body: RouteCreate,
) -> RouteRead:
    """Create a new route (admin only)."""
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
        degraded_threshold=body.degraded_threshold,
        max_hop_span=body.max_hop_span,
        enabled=body.enabled,
        reversible=body.reversible,
    )
    session.add(route)
    session.flush()
    _sync_path_nodes(session, route, nodes)
    _sync_observers(session, route, observer_nodes)
    session.commit()
    session.refresh(route)
    return _route_to_read(route)


@router.get("/{route_id}", response_model=RouteDetail)
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

    matches = recent_matches(session, route, limit=3)

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

    read = _route_to_read(route)
    return RouteDetail(
        **read.model_dump(),
        contributing_observers=contributors,
        recent_matches=[RecentMatchPath(**m) for m in matches],
    )


@router.put("/{route_id}", response_model=RouteRead)
def update_route(
    __: RequireAdmin,
    session: DbSession,
    route_id: str,
    body: RouteUpdate,
) -> RouteRead:
    """Update a route (admin only)."""
    route = session.execute(
        select(Route).where(Route.id == route_id)
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

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
        route.visibility = body.visibility
    if body.match_width is not None:
        route.match_width = body.match_width
    if body.window_hours is not None:
        route.window_hours = body.window_hours
    if body.packet_count_threshold is not None:
        route.packet_count_threshold = body.packet_count_threshold
    if body.degraded_threshold is not None:
        route.degraded_threshold = body.degraded_threshold
    if body.max_hop_span is not None:
        route.max_hop_span = body.max_hop_span
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
    return _route_to_read(route)


@router.delete("/{route_id}", status_code=204)
def delete_route(
    __: RequireAdmin,
    session: DbSession,
    route_id: str,
) -> None:
    """Delete a route (admin only)."""
    route = session.execute(
        select(Route).where(Route.id == route_id)
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    session.delete(route)
    session.commit()


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
        "packet_count_threshold": body.packet_count_threshold,
        "degraded_threshold": body.degraded_threshold,
        "reversible": body.reversible,
    }
    result = preview_route(session, config, since)
    return RoutePreviewResponse(**result)
