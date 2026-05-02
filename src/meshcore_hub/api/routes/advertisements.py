"""Advertisement API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.observer_utils import fetch_observers_for_events
from meshcore_hub.common.models import Advertisement, Node, NodeTag, UserProfileNode
from meshcore_hub.common.schemas.messages import (
    AdvertisementList,
    AdvertisementRead,
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


def _get_tag_description(node: Optional[Node]) -> Optional[str]:
    """Extract description tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "description":
            return tag.value
    return None


@router.get("", response_model=AdvertisementList)
async def list_advertisements(
    _: RequireRead,
    session: DbSession,
    search: Optional[str] = Query(
        None, description="Search in name tag, node name, or public key"
    ),
    public_key: Optional[str] = Query(None, description="Filter by public key"),
    observed_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    adopted_by: Optional[str] = Query(
        None, description="Filter by adopting user profile UUID"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> AdvertisementList:
    """List advertisements with filtering and pagination."""
    # Aliases for node joins
    ObserverNode = aliased(Node)
    SourceNode = aliased(Node)

    # Build query with both receiver and source node joins
    query = (
        select(
            Advertisement,
            ObserverNode.public_key.label("observer_pk"),
            ObserverNode.name.label("observer_name"),
            ObserverNode.id.label("observer_id"),
            SourceNode.name.label("source_name"),
            SourceNode.id.label("source_id"),
            SourceNode.adv_type.label("source_adv_type"),
        )
        .outerjoin(ObserverNode, Advertisement.observer_node_id == ObserverNode.id)
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

    if observed_by:
        query = query.where(ObserverNode.public_key == observed_by)

    if adopted_by:
        query = query.where(
            SourceNode.id.in_(
                select(UserProfileNode.node_id).where(
                    UserProfileNode.user_profile_id == adopted_by
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
        if row.observer_id:
            node_ids.add(row.observer_id)
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

    # Fetch all observers for these advertisements
    event_hashes = [r[0].event_hash for r in results if r[0].event_hash]
    observers_by_hash = fetch_observers_for_events(
        session, "advertisement", event_hashes
    )

    # Build response with node details
    items = []
    for row in results:
        adv = row[0]
        observer_node = nodes_by_id.get(row.observer_id) if row.observer_id else None
        source_node = nodes_by_id.get(row.source_id) if row.source_id else None

        data = {
            "observed_by": row.observer_pk,
            "observer_name": row.observer_name,
            "observer_tag_name": _get_tag_name(observer_node),
            "public_key": adv.public_key,
            "name": adv.name,
            "node_name": row.source_name,
            "node_tag_name": _get_tag_name(source_node),
            "node_tag_description": _get_tag_description(source_node),
            "adv_type": adv.adv_type or row.source_adv_type,
            "flags": adv.flags,
            "received_at": adv.received_at,
            "created_at": adv.created_at,
            "observers": (
                observers_by_hash.get(adv.event_hash, []) if adv.event_hash else []
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
    ObserverNode = aliased(Node)
    SourceNode = aliased(Node)
    query = (
        select(
            Advertisement,
            ObserverNode.public_key.label("observer_pk"),
            ObserverNode.name.label("observer_name"),
            ObserverNode.id.label("observer_id"),
            SourceNode.name.label("source_name"),
            SourceNode.id.label("source_id"),
            SourceNode.adv_type.label("source_adv_type"),
        )
        .outerjoin(ObserverNode, Advertisement.observer_node_id == ObserverNode.id)
        .outerjoin(SourceNode, Advertisement.node_id == SourceNode.id)
        .where(Advertisement.id == advertisement_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Advertisement not found")

    adv = result[0]

    # Fetch nodes with tags for friendly names
    node_ids = []
    if result.observer_id:
        node_ids.append(result.observer_id)
    if result.source_id:
        node_ids.append(result.source_id)

    nodes_by_id: dict[str, Node] = {}
    if node_ids:
        nodes_query = (
            select(Node).where(Node.id.in_(node_ids)).options(selectinload(Node.tags))
        )
        nodes = session.execute(nodes_query).scalars().all()
        nodes_by_id = {n.id: n for n in nodes}

    observer_node = nodes_by_id.get(result.observer_id) if result.observer_id else None
    source_node = nodes_by_id.get(result.source_id) if result.source_id else None

    # Fetch observers for this advertisement
    observers = []
    if adv.event_hash:
        observers_by_hash = fetch_observers_for_events(
            session, "advertisement", [adv.event_hash]
        )
        observers = observers_by_hash.get(adv.event_hash, [])

    data = {
        "observed_by": result.observer_pk,
        "observer_name": result.observer_name,
        "observer_tag_name": _get_tag_name(observer_node),
        "public_key": adv.public_key,
        "name": adv.name,
        "node_name": result.source_name,
        "node_tag_name": _get_tag_name(source_node),
        "node_tag_description": _get_tag_description(source_node),
        "adv_type": adv.adv_type or result.source_adv_type,
        "flags": adv.flags,
        "received_at": adv.received_at,
        "created_at": adv.created_at,
        "observers": observers,
    }
    return AdvertisementRead(**data)
