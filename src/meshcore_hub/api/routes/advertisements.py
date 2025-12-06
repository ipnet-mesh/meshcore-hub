"""Advertisement API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.hash_utils import compute_advertisement_hash
from meshcore_hub.common.models import Advertisement, Node
from meshcore_hub.common.schemas.messages import AdvertisementList, AdvertisementRead

router = APIRouter()


def _get_friendly_name(node: Optional[Node]) -> Optional[str]:
    """Extract friendly_name tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "friendly_name":
            return tag.value
    return None


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
    dedupe: bool = Query(
        True, description="Deduplicate advertisements from multiple receivers"
    ),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> AdvertisementList:
    """List advertisements with filtering and pagination."""
    # Aliases for node joins
    ReceiverNode = aliased(Node)
    SourceNode = aliased(Node)

    # Build query with both receiver and source node joins
    query = (
        select(
            Advertisement,
            ReceiverNode.public_key.label("receiver_pk"),
            ReceiverNode.name.label("receiver_name"),
            ReceiverNode.id.label("receiver_id"),
            SourceNode.name.label("source_name"),
            SourceNode.id.label("source_id"),
            SourceNode.adv_type.label("source_adv_type"),
        )
        .outerjoin(ReceiverNode, Advertisement.receiver_node_id == ReceiverNode.id)
        .outerjoin(SourceNode, Advertisement.node_id == SourceNode.id)
    )

    if public_key:
        query = query.where(Advertisement.public_key == public_key)

    if received_by:
        query = query.where(ReceiverNode.public_key == received_by)

    if since:
        query = query.where(Advertisement.received_at >= since)

    if until:
        query = query.where(Advertisement.received_at <= until)

    # When deduplicating, we need to fetch more results and compute distinct count
    if dedupe:
        # For deduplicated count, count distinct by public_key within time buckets
        # We use a 5-minute time bucket for advertisements
        distinct_subquery = (
            select(
                Advertisement.public_key,
                Advertisement.name,
                Advertisement.adv_type,
                Advertisement.flags,
                # Use date truncation for time bucketing (5 min = 300 seconds)
                (func.strftime("%s", Advertisement.received_at) / 300).label(
                    "time_bucket"
                ),
            )
            .distinct()
            .select_from(query.subquery())
        )
        count_query = select(func.count()).select_from(distinct_subquery.subquery())
        total = session.execute(count_query).scalar() or 0

        # Fetch extra results to account for duplicates
        fetch_limit = (limit + offset) * 3
        query = query.order_by(Advertisement.received_at.desc()).limit(fetch_limit)
    else:
        # Standard count and pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = session.execute(count_query).scalar() or 0
        query = (
            query.order_by(Advertisement.received_at.desc()).offset(offset).limit(limit)
        )

    # Execute
    results = session.execute(query).all()

    # Collect node IDs to fetch tags
    node_ids = set()
    for row in results:
        if row.receiver_id:
            node_ids.add(row.receiver_id)
        if row.source_id:
            node_ids.add(row.source_id)

    # Fetch nodes with tags
    nodes_by_id: dict[str, Node] = {}
    if node_ids:
        nodes_query = (
            select(Node).where(Node.id.in_(node_ids)).options(selectinload(Node.tags))
        )
        nodes = session.execute(nodes_query).scalars().all()
        nodes_by_id = {n.id: n for n in nodes}

    # Build response with node details
    items = []
    seen_hashes: set[str] = set()

    for row in results:
        adv = row[0]

        # Compute hash for deduplication
        if dedupe:
            adv_hash = compute_advertisement_hash(
                public_key=adv.public_key,
                name=adv.name,
                adv_type=adv.adv_type,
                flags=adv.flags,
                received_at=adv.received_at,
                bucket_minutes=5,
            )
            if adv_hash in seen_hashes:
                continue
            seen_hashes.add(adv_hash)

        receiver_node = nodes_by_id.get(row.receiver_id) if row.receiver_id else None
        source_node = nodes_by_id.get(row.source_id) if row.source_id else None

        data = {
            "received_by": row.receiver_pk,
            "receiver_name": row.receiver_name,
            "receiver_friendly_name": _get_friendly_name(receiver_node),
            "public_key": adv.public_key,
            "name": adv.name,
            "node_name": row.source_name,
            "node_friendly_name": _get_friendly_name(source_node),
            "adv_type": adv.adv_type or row.source_adv_type,
            "flags": adv.flags,
            "received_at": adv.received_at,
            "created_at": adv.created_at,
        }
        items.append(AdvertisementRead(**data))

        # Stop once we have enough items (for dedupe mode with pagination)
        if dedupe and len(items) >= offset + limit:
            break

    # Apply offset for dedupe mode (we fetched from beginning)
    if dedupe:
        items = items[offset : offset + limit]

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
    SourceNode = aliased(Node)
    query = (
        select(
            Advertisement,
            ReceiverNode.public_key.label("receiver_pk"),
            ReceiverNode.name.label("receiver_name"),
            ReceiverNode.id.label("receiver_id"),
            SourceNode.name.label("source_name"),
            SourceNode.id.label("source_id"),
            SourceNode.adv_type.label("source_adv_type"),
        )
        .outerjoin(ReceiverNode, Advertisement.receiver_node_id == ReceiverNode.id)
        .outerjoin(SourceNode, Advertisement.node_id == SourceNode.id)
        .where(Advertisement.id == advertisement_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Advertisement not found")

    adv = result[0]

    # Fetch nodes with tags for friendly names
    node_ids = []
    if result.receiver_id:
        node_ids.append(result.receiver_id)
    if result.source_id:
        node_ids.append(result.source_id)

    nodes_by_id: dict[str, Node] = {}
    if node_ids:
        nodes_query = (
            select(Node).where(Node.id.in_(node_ids)).options(selectinload(Node.tags))
        )
        nodes = session.execute(nodes_query).scalars().all()
        nodes_by_id = {n.id: n for n in nodes}

    receiver_node = nodes_by_id.get(result.receiver_id) if result.receiver_id else None
    source_node = nodes_by_id.get(result.source_id) if result.source_id else None

    data = {
        "received_by": result.receiver_pk,
        "receiver_name": result.receiver_name,
        "receiver_friendly_name": _get_friendly_name(receiver_node),
        "public_key": adv.public_key,
        "name": adv.name,
        "node_name": result.source_name,
        "node_friendly_name": _get_friendly_name(source_node),
        "adv_type": adv.adv_type or result.source_adv_type,
        "flags": adv.flags,
        "received_at": adv.received_at,
        "created_at": adv.created_at,
    }
    return AdvertisementRead(**data)
