"""Telemetry API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.observer_utils import fetch_observers_for_events
from meshcore_hub.common.models import Node, Telemetry
from meshcore_hub.common.schemas.messages import TelemetryList, TelemetryRead

router = APIRouter()


@router.get("", response_model=TelemetryList)
async def list_telemetry(
    _: RequireRead,
    session: DbSession,
    node_public_key: Optional[str] = Query(None, description="Filter by node"),
    observed_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> TelemetryList:
    """List telemetry records with filtering and pagination."""
    # Alias for receiver node join
    ObserverNode = aliased(Node)

    # Build query with receiver node join
    query = select(Telemetry, ObserverNode.public_key.label("observer_pk")).outerjoin(
        ObserverNode, Telemetry.observer_node_id == ObserverNode.id
    )

    if node_public_key:
        query = query.where(Telemetry.node_public_key == node_public_key)

    if observed_by:
        query = query.where(ObserverNode.public_key == observed_by)

    if since:
        query = query.where(Telemetry.received_at >= since)

    if until:
        query = query.where(Telemetry.received_at <= until)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Apply pagination
    query = query.order_by(Telemetry.received_at.desc()).offset(offset).limit(limit)

    # Execute
    results = session.execute(query).all()

    # Fetch observers for these telemetry records
    event_hashes = [tel.event_hash for tel, _ in results if tel.event_hash]
    observers_by_hash = fetch_observers_for_events(session, "telemetry", event_hashes)

    # Build response with observed_by
    items = []
    for tel, observer_pk in results:
        data = {
            "id": tel.id,
            "observer_node_id": tel.observer_node_id,
            "observed_by": observer_pk,
            "node_id": tel.node_id,
            "node_public_key": tel.node_public_key,
            "parsed_data": tel.parsed_data,
            "received_at": tel.received_at,
            "created_at": tel.created_at,
            "observers": (
                observers_by_hash.get(tel.event_hash, []) if tel.event_hash else []
            ),
        }
        items.append(TelemetryRead(**data))

    return TelemetryList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{telemetry_id}", response_model=TelemetryRead)
async def get_telemetry(
    _: RequireRead,
    session: DbSession,
    telemetry_id: str,
) -> TelemetryRead:
    """Get a single telemetry record by ID."""
    ObserverNode = aliased(Node)
    query = (
        select(Telemetry, ObserverNode.public_key.label("observer_pk"))
        .outerjoin(ObserverNode, Telemetry.observer_node_id == ObserverNode.id)
        .where(Telemetry.id == telemetry_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Telemetry record not found")

    tel, observer_pk = result

    observers = []
    if tel.event_hash:
        observers_by_hash = fetch_observers_for_events(
            session, "telemetry", [tel.event_hash]
        )
        observers = observers_by_hash.get(tel.event_hash, [])

    data = {
        "id": tel.id,
        "observer_node_id": tel.observer_node_id,
        "observed_by": observer_pk,
        "node_id": tel.node_id,
        "node_public_key": tel.node_public_key,
        "parsed_data": tel.parsed_data,
        "received_at": tel.received_at,
        "created_at": tel.created_at,
        "observers": observers,
    }
    return TelemetryRead(**data)
