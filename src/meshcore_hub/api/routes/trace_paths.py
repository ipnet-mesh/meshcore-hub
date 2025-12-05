"""Trace path API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node, TracePath
from meshcore_hub.common.schemas.messages import TracePathList, TracePathRead

router = APIRouter()


@router.get("", response_model=TracePathList)
async def list_trace_paths(
    _: RequireRead,
    session: DbSession,
    received_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> TracePathList:
    """List trace paths with filtering and pagination."""
    # Alias for receiver node join
    ReceiverNode = aliased(Node)

    # Build query with receiver node join
    query = select(TracePath, ReceiverNode.public_key.label("receiver_pk")).outerjoin(
        ReceiverNode, TracePath.receiver_node_id == ReceiverNode.id
    )

    if received_by:
        query = query.where(ReceiverNode.public_key == received_by)

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

    # Build response with received_by
    items = []
    for tp, receiver_pk in results:
        data = {
            "id": tp.id,
            "receiver_node_id": tp.receiver_node_id,
            "received_by": receiver_pk,
            "initiator_tag": tp.initiator_tag,
            "path_len": tp.path_len,
            "flags": tp.flags,
            "auth": tp.auth,
            "path_hashes": tp.path_hashes,
            "snr_values": tp.snr_values,
            "hop_count": tp.hop_count,
            "received_at": tp.received_at,
            "created_at": tp.created_at,
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
    ReceiverNode = aliased(Node)
    query = (
        select(TracePath, ReceiverNode.public_key.label("receiver_pk"))
        .outerjoin(ReceiverNode, TracePath.receiver_node_id == ReceiverNode.id)
        .where(TracePath.id == trace_path_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Trace path not found")

    tp, receiver_pk = result
    data = {
        "id": tp.id,
        "receiver_node_id": tp.receiver_node_id,
        "received_by": receiver_pk,
        "initiator_tag": tp.initiator_tag,
        "path_len": tp.path_len,
        "flags": tp.flags,
        "auth": tp.auth,
        "path_hashes": tp.path_hashes,
        "snr_values": tp.snr_values,
        "hop_count": tp.hop_count,
        "received_at": tp.received_at,
        "created_at": tp.created_at,
    }
    return TracePathRead(**data)
