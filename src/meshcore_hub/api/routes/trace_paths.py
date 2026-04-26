"""Trace path API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.observer_utils import fetch_observers_for_events
from meshcore_hub.common.models import Node, TracePath
from meshcore_hub.common.schemas.messages import TracePathList, TracePathRead

router = APIRouter()


@router.get("", response_model=TracePathList)
async def list_trace_paths(
    _: RequireRead,
    session: DbSession,
    observed_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> TracePathList:
    """List trace paths with filtering and pagination."""
    # Alias for receiver node join
    ObserverNode = aliased(Node)

    # Build query with receiver node join
    query = select(TracePath, ObserverNode.public_key.label("observer_pk")).outerjoin(
        ObserverNode, TracePath.observer_node_id == ObserverNode.id
    )

    if observed_by:
        query = query.where(ObserverNode.public_key == observed_by)

    if since:
        query = query.where(TracePath.received_at >= since)

    if until:
        query = query.where(TracePath.received_at <= until)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Apply pagination
    query = query.order_by(TracePath.received_at.desc()).offset(offset).limit(limit)

    # Execute
    results = session.execute(query).all()

    # Fetch observers for these trace paths
    event_hashes = [tp.event_hash for tp, _ in results if tp.event_hash]
    observers_by_hash = fetch_observers_for_events(session, "trace", event_hashes)

    # Build response with observed_by
    items = []
    for tp, observer_pk in results:
        data = {
            "id": tp.id,
            "observer_node_id": tp.observer_node_id,
            "observed_by": observer_pk,
            "initiator_tag": tp.initiator_tag,
            "path_len": tp.path_len,
            "flags": tp.flags,
            "auth": tp.auth,
            "path_hashes": tp.path_hashes,
            "snr_values": tp.snr_values,
            "hop_count": tp.hop_count,
            "received_at": tp.received_at,
            "created_at": tp.created_at,
            "observers": (
                observers_by_hash.get(tp.event_hash, []) if tp.event_hash else []
            ),
        }
        items.append(TracePathRead(**data))

    return TracePathList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{trace_path_id}", response_model=TracePathRead)
async def get_trace_path(
    _: RequireRead,
    session: DbSession,
    trace_path_id: str,
) -> TracePathRead:
    """Get a single trace path by ID."""
    ObserverNode = aliased(Node)
    query = (
        select(TracePath, ObserverNode.public_key.label("observer_pk"))
        .outerjoin(ObserverNode, TracePath.observer_node_id == ObserverNode.id)
        .where(TracePath.id == trace_path_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Trace path not found")

    tp, observer_pk = result

    observers = []
    if tp.event_hash:
        observers_by_hash = fetch_observers_for_events(
            session, "trace", [tp.event_hash]
        )
        observers = observers_by_hash.get(tp.event_hash, [])

    data = {
        "id": tp.id,
        "observer_node_id": tp.observer_node_id,
        "observed_by": observer_pk,
        "initiator_tag": tp.initiator_tag,
        "path_len": tp.path_len,
        "flags": tp.flags,
        "auth": tp.auth,
        "path_hashes": tp.path_hashes,
        "snr_values": tp.snr_values,
        "hop_count": tp.hop_count,
        "received_at": tp.received_at,
        "created_at": tp.created_at,
        "observers": observers,
    }
    return TracePathRead(**data)
