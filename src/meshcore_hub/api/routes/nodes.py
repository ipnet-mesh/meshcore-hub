"""Node API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node, NodeTag
from meshcore_hub.common.schemas.nodes import NodeList, NodeRead

router = APIRouter()


@router.get("", response_model=NodeList)
async def list_nodes(
    _: RequireRead,
    session: DbSession,
    search: Optional[str] = Query(
        None, description="Search in name tag, node name, or public key"
    ),
    adv_type: Optional[str] = Query(None, description="Filter by advertisement type"),
    member_id: Optional[str] = Query(None, description="Filter by member_id tag value"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> NodeList:
    """List all nodes with pagination and filtering."""
    # Build base query with tags loaded
    query = select(Node).options(selectinload(Node.tags))

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
        query = query.where(Node.adv_type == adv_type)

    if member_id:
        # Filter nodes that have a member_id tag with the specified value
        query = query.where(
            Node.id.in_(
                select(NodeTag.node_id).where(
                    NodeTag.key == "member_id", NodeTag.value == member_id
                )
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(Node.last_seen.desc()).offset(offset).limit(limit)

    # Execute
    nodes = session.execute(query).scalars().all()

    return NodeList(
        items=[NodeRead.model_validate(n) for n in nodes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{public_key}", response_model=NodeRead)
async def get_node(
    _: RequireRead,
    session: DbSession,
    public_key: str,
) -> NodeRead:
    """Get a single node by public key."""
    query = select(Node).where(Node.public_key == public_key)
    node = session.execute(query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return NodeRead.model_validate(node)
