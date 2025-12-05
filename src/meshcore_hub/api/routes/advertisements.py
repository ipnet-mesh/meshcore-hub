"""Advertisement API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Advertisement, Node
from meshcore_hub.common.schemas.messages import AdvertisementList, AdvertisementRead

router = APIRouter()


@router.get("", response_model=AdvertisementList)
async def list_advertisements(
    _: RequireRead,
    session: DbSession,
    public_key: Optional[str] = Query(None, description="Filter by public key"),
    received_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> AdvertisementList:
    """List advertisements with filtering and pagination."""
    # Alias for receiver node join
    ReceiverNode = aliased(Node)

    # Build query with receiver node join
    query = select(
        Advertisement, ReceiverNode.public_key.label("receiver_pk")
    ).outerjoin(ReceiverNode, Advertisement.receiver_node_id == ReceiverNode.id)

    if public_key:
        query = query.where(Advertisement.public_key == public_key)

    if received_by:
        query = query.where(ReceiverNode.public_key == received_by)

    if since:
        query = query.where(Advertisement.received_at >= since)

    if until:
        query = query.where(Advertisement.received_at <= until)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Apply pagination
    query = query.order_by(Advertisement.received_at.desc()).offset(offset).limit(limit)

    # Execute
    results = session.execute(query).all()

    # Build response with received_by
    items = []
    for adv, receiver_pk in results:
        data = {
            "id": adv.id,
            "receiver_node_id": adv.receiver_node_id,
            "received_by": receiver_pk,
            "node_id": adv.node_id,
            "public_key": adv.public_key,
            "name": adv.name,
            "adv_type": adv.adv_type,
            "flags": adv.flags,
            "received_at": adv.received_at,
            "created_at": adv.created_at,
        }
        items.append(AdvertisementRead(**data))

    return AdvertisementList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{advertisement_id}", response_model=AdvertisementRead)
async def get_advertisement(
    _: RequireRead,
    session: DbSession,
    advertisement_id: str,
) -> AdvertisementRead:
    """Get a single advertisement by ID."""
    ReceiverNode = aliased(Node)
    query = (
        select(Advertisement, ReceiverNode.public_key.label("receiver_pk"))
        .outerjoin(ReceiverNode, Advertisement.receiver_node_id == ReceiverNode.id)
        .where(Advertisement.id == advertisement_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Advertisement not found")

    adv, receiver_pk = result
    data = {
        "id": adv.id,
        "receiver_node_id": adv.receiver_node_id,
        "received_by": receiver_pk,
        "node_id": adv.node_id,
        "public_key": adv.public_key,
        "name": adv.name,
        "adv_type": adv.adv_type,
        "flags": adv.flags,
        "received_at": adv.received_at,
        "created_at": adv.created_at,
    }
    return AdvertisementRead(**data)
