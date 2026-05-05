"""Node API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import (
    Advertisement,
    EventObserver,
    Message,
    Node,
    NodeTag,
    Telemetry,
    TracePath,
    UserProfileNode,
)
from meshcore_hub.common.schemas.nodes import AdoptedByUser, NodeList, NodeRead

router = APIRouter()


def _get_adopted_by(node: Node) -> Optional[AdoptedByUser]:
    """Extract adopted_by info from a node's eager-loaded associations."""
    if node.user_profile_associations:
        profile = node.user_profile_associations[0].user_profile
        return AdoptedByUser(
            user_id=profile.user_id,
            name=profile.name,
            callsign=profile.callsign,
            profile_id=profile.id,
        )
    return None


def _node_to_read(node: Node) -> NodeRead:
    """Convert a Node ORM object to NodeRead schema with adopted_by."""
    node_read = NodeRead.model_validate(node)
    node_read.adopted_by = _get_adopted_by(node)
    return node_read


VALID_NODE_SORT_COLUMNS = {"name", "public_key", "last_seen"}


@router.get("", response_model=NodeList)
async def list_nodes(
    _: RequireRead,
    session: DbSession,
    search: Optional[str] = Query(
        None, description="Search in name tag, node name, or public key"
    ),
    adv_type: Optional[str] = Query(None, description="Filter by advertisement type"),
    adopted_by: Optional[str] = Query(
        None, description="Filter by adopting user profile UUID"
    ),
    role: Optional[str] = Query(None, description="Filter by role tag value"),
    observer: Optional[bool] = Query(
        None, description="Filter to nodes that have observed events"
    ),
    sort: Optional[str] = Query(None, description="Sort column"),
    order: Optional[str] = Query(None, description="Sort direction: asc or desc"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> NodeList:
    """List all nodes with pagination and filtering."""
    # Build base query with tags and adoption info loaded
    query = select(Node).options(
        selectinload(Node.tags),
        selectinload(Node.user_profile_associations).selectinload(
            UserProfileNode.user_profile
        ),
    )

    if search:
        # Search in public key, node name, or name tag
        # For name tag search, we need to join with NodeTag
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Node.public_key.ilike(search_pattern),
                Node.name.ilike(search_pattern),
                Node.id.in_(
                    select(NodeTag.node_id).where(
                        NodeTag.key == "name", NodeTag.value.ilike(search_pattern)
                    )
                ),
            )
        )

    if adv_type:
        normalized_adv_type = adv_type.strip().lower()
        if normalized_adv_type == "repeater":
            query = query.where(
                or_(
                    Node.adv_type == "repeater",
                    Node.adv_type.ilike("%repeater%"),
                    Node.adv_type.ilike("%relay%"),
                )
            )
        elif normalized_adv_type == "companion":
            query = query.where(
                or_(
                    Node.adv_type == "companion",
                    Node.adv_type.ilike("%companion%"),
                    Node.adv_type.ilike("%observer%"),
                )
            )
        elif normalized_adv_type == "room":
            query = query.where(
                or_(
                    Node.adv_type == "room",
                    Node.adv_type.ilike("%room%"),
                )
            )
        elif normalized_adv_type == "chat":
            query = query.where(
                or_(
                    Node.adv_type == "chat",
                    Node.adv_type.ilike("%chat%"),
                )
            )
        else:
            query = query.where(Node.adv_type == adv_type)

    if adopted_by:
        query = query.where(
            Node.id.in_(
                select(UserProfileNode.node_id).where(
                    UserProfileNode.user_profile_id == adopted_by
                )
            )
        )

    if role:
        # Filter nodes that have a role tag with the specified value
        query = query.where(
            Node.id.in_(
                select(NodeTag.node_id).where(
                    NodeTag.key == "role", NodeTag.value == role
                )
            )
        )

    if observer is not None:
        if observer:
            query = query.where(
                or_(
                    Node.id.in_(
                        select(Advertisement.observer_node_id).where(
                            Advertisement.observer_node_id.is_not(None)
                        )
                    ),
                    Node.id.in_(
                        select(Message.observer_node_id).where(
                            Message.observer_node_id.is_not(None)
                        )
                    ),
                    Node.id.in_(
                        select(Telemetry.observer_node_id).where(
                            Telemetry.observer_node_id.is_not(None)
                        )
                    ),
                    Node.id.in_(
                        select(TracePath.observer_node_id).where(
                            TracePath.observer_node_id.is_not(None)
                        )
                    ),
                    Node.id.in_(select(EventObserver.observer_node_id)),
                )
            )
        else:
            query = query.where(
                ~Node.id.in_(
                    select(Advertisement.observer_node_id).where(
                        Advertisement.observer_node_id.is_not(None)
                    )
                ),
                ~Node.id.in_(
                    select(Message.observer_node_id).where(
                        Message.observer_node_id.is_not(None)
                    )
                ),
                ~Node.id.in_(
                    select(Telemetry.observer_node_id).where(
                        Telemetry.observer_node_id.is_not(None)
                    )
                ),
                ~Node.id.in_(
                    select(TracePath.observer_node_id).where(
                        TracePath.observer_node_id.is_not(None)
                    )
                ),
                ~Node.id.in_(select(EventObserver.observer_node_id)),
            )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Resolve sort column and direction
    sort = sort if sort in VALID_NODE_SORT_COLUMNS else "name"
    order = order if order in ("asc", "desc") else ("asc" if sort == "name" else "desc")

    name_tag_subq = (
        select(NodeTag.value)
        .where(NodeTag.node_id == Node.id, NodeTag.key == "name")
        .correlate(Node)
        .scalar_subquery()
    )

    if sort == "name":
        _col = func.coalesce(name_tag_subq, Node.name, Node.public_key)
        query = query.order_by(_col.desc() if order == "desc" else _col.asc())
    elif sort == "public_key":
        query = query.order_by(
            Node.public_key.desc() if order == "desc" else Node.public_key.asc()
        )
    elif sort == "last_seen":
        query = query.order_by(
            Node.last_seen.desc() if order == "desc" else Node.last_seen.asc()
        )
    else:
        _col = func.coalesce(name_tag_subq, Node.name, Node.public_key)
        query = query.order_by(_col.desc() if order == "desc" else _col.asc())

    # Apply pagination
    query = query.offset(offset).limit(limit)

    # Execute
    nodes = session.execute(query).scalars().all()

    return NodeList(
        items=[_node_to_read(n) for n in nodes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/prefix/{prefix}", response_model=NodeRead)
async def get_node_by_prefix(
    _: RequireRead,
    session: DbSession,
    prefix: str = Path(description="Public key prefix to search for"),
) -> NodeRead:
    """Get a single node by public key prefix.

    Returns the first node (alphabetically by public_key) that matches the prefix.
    """
    query = (
        select(Node)
        .options(
            selectinload(Node.tags),
            selectinload(Node.user_profile_associations).selectinload(
                UserProfileNode.user_profile
            ),
        )
        .where(Node.public_key.startswith(prefix))
        .order_by(Node.public_key)
        .limit(1)
    )
    node = session.execute(query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return _node_to_read(node)


@router.get("/{public_key}", response_model=NodeRead)
async def get_node(
    _: RequireRead,
    session: DbSession,
    public_key: str = Path(description="Full 64-character public key"),
) -> NodeRead:
    """Get a single node by exact public key match."""
    query = (
        select(Node)
        .options(
            selectinload(Node.tags),
            selectinload(Node.user_profile_associations).selectinload(
                UserProfileNode.user_profile
            ),
        )
        .where(Node.public_key == public_key)
    )
    node = session.execute(query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return _node_to_read(node)
