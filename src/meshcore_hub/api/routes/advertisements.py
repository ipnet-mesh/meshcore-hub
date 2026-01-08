"""Advertisement API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Advertisement, EventReceiver, Node, NodeTag
from meshcore_hub.common.schemas.messages import (
    AdvertisementList,
    AdvertisementRead,
    ReceiverInfo,
)

router = APIRouter()


def _get_tag_name(node: Optional[Node]) -> Optional[str]:
    """Extract name tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "name":
            return tag.value
    return None


def _fetch_receivers_for_events(
    session: DbSession,
    event_type: str,
    event_hashes: list[str],
) -> dict[str, list[ReceiverInfo]]:
    """Fetch receiver info for a list of events by their hashes."""
    if not event_hashes:
        return {}

    query = (
        select(
            EventReceiver.event_hash,
            EventReceiver.snr,
            EventReceiver.received_at,
            Node.id.label("node_id"),
            Node.public_key,
            Node.name,
        )
        .join(Node, EventReceiver.receiver_node_id == Node.id)
        .where(EventReceiver.event_type == event_type)
        .where(EventReceiver.event_hash.in_(event_hashes))
        .order_by(EventReceiver.received_at)
    )

    results = session.execute(query).all()
    receivers_by_hash: dict[str, list[ReceiverInfo]] = {}

    node_ids = [r.node_id for r in results]
    tag_names: dict[str, str] = {}
    if node_ids:
        tag_query = (
            select(NodeTag.node_id, NodeTag.value)
            .where(NodeTag.node_id.in_(node_ids))
            .where(NodeTag.key == "name")
        )
        for node_id, value in session.execute(tag_query).all():
            tag_names[node_id] = value

    for row in results:
        if row.event_hash not in receivers_by_hash:
            receivers_by_hash[row.event_hash] = []

        receivers_by_hash[row.event_hash].append(
            ReceiverInfo(
                node_id=row.node_id,
                public_key=row.public_key,
                name=row.name,
                tag_name=tag_names.get(row.node_id),
                snr=row.snr,
                received_at=row.received_at,
            )
        )

    return receivers_by_hash


@router.get("", response_model=AdvertisementList)
async def list_advertisements(
    _: RequireRead,
    session: DbSession,
    search: Optional[str] = Query(
        None, description="Search in name tag, node name, or public key"
    ),
    public_key: Optional[str] = Query(None, description="Filter by public key"),
    received_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    member_id: Optional[str] = Query(
        None, description="Filter by member_id tag value of source node"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
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

    if search:
        # Search in public key, advertisement name, node name, or name tag
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Advertisement.public_key.ilike(search_pattern),
                Advertisement.name.ilike(search_pattern),
                SourceNode.name.ilike(search_pattern),
                SourceNode.id.in_(
                    select(NodeTag.node_id).where(
                        NodeTag.key == "name", NodeTag.value.ilike(search_pattern)
                    )
                ),
            )
        )

    if public_key:
        query = query.where(Advertisement.public_key == public_key)

    if received_by:
        query = query.where(ReceiverNode.public_key == received_by)

    if member_id:
        # Filter advertisements from nodes that have a member_id tag with the specified value
        query = query.where(
            SourceNode.id.in_(
                select(NodeTag.node_id).where(
                    NodeTag.key == "member_id", NodeTag.value == member_id
                )
            )
        )

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

    # Fetch all receivers for these advertisements
    event_hashes = [r[0].event_hash for r in results if r[0].event_hash]
    receivers_by_hash = _fetch_receivers_for_events(
        session, "advertisement", event_hashes
    )

    # Build response with node details
    items = []
    for row in results:
        adv = row[0]
        receiver_node = nodes_by_id.get(row.receiver_id) if row.receiver_id else None
        source_node = nodes_by_id.get(row.source_id) if row.source_id else None

        data = {
            "received_by": row.receiver_pk,
            "receiver_name": row.receiver_name,
            "receiver_tag_name": _get_tag_name(receiver_node),
            "public_key": adv.public_key,
            "name": adv.name,
            "node_name": row.source_name,
            "node_tag_name": _get_tag_name(source_node),
            "adv_type": adv.adv_type or row.source_adv_type,
            "flags": adv.flags,
            "received_at": adv.received_at,
            "created_at": adv.created_at,
            "receivers": (
                receivers_by_hash.get(adv.event_hash, []) if adv.event_hash else []
            ),
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

    # Fetch receivers for this advertisement
    receivers = []
    if adv.event_hash:
        receivers_by_hash = _fetch_receivers_for_events(
            session, "advertisement", [adv.event_hash]
        )
        receivers = receivers_by_hash.get(adv.event_hash, [])

    data = {
        "received_by": result.receiver_pk,
        "receiver_name": result.receiver_name,
        "receiver_tag_name": _get_tag_name(receiver_node),
        "public_key": adv.public_key,
        "name": adv.name,
        "node_name": result.source_name,
        "node_tag_name": _get_tag_name(source_node),
        "adv_type": adv.adv_type or result.source_adv_type,
        "flags": adv.flags,
        "received_at": adv.received_at,
        "created_at": adv.created_at,
        "receivers": receivers,
    }
    return AdvertisementRead(**data)
