"""Node API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node
from meshcore_hub.common.schemas.nodes import NodeList, NodeRead

router = APIRouter()


@router.get("", response_model=NodeList)
async def list_nodes(
    _: RequireRead,
    session: DbSession,
    search: Optional[str] = Query(None, description="Search in name or public key"),
    adv_type: Optional[str] = Query(None, description="Filter by advertisement type"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> NodeList:
    """List all nodes with pagination and filtering."""
    # Build query
    query = select(Node)

    if search:
        query = query.where(
            (Node.name.ilike(f"%{search}%")) | (Node.public_key.ilike(f"%{search}%"))
        )

    if adv_type:
        query = query.where(Node.adv_type == adv_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Apply pagination
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
