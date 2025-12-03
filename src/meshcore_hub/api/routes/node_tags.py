"""Node tag API routes."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from meshcore_hub.api.auth import RequireAdmin, RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node, NodeTag
from meshcore_hub.common.schemas.nodes import NodeTagCreate, NodeTagRead, NodeTagUpdate

router = APIRouter()


@router.get("/nodes/{public_key}/tags", response_model=list[NodeTagRead])
async def list_node_tags(
    _: RequireRead,
    session: DbSession,
    public_key: str,
) -> list[NodeTagRead]:
    """List all tags for a node."""
    # Find node
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return [NodeTagRead.model_validate(t) for t in node.tags]


@router.get("/nodes/{public_key}/tags/{key}", response_model=NodeTagRead)
async def get_node_tag(
    _: RequireRead,
    session: DbSession,
    public_key: str,
    key: str,
) -> NodeTagRead:
    """Get a specific tag for a node."""
    # Find node
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Find tag
    tag_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == key)
    )
    node_tag = session.execute(tag_query).scalar_one_or_none()

    if not node_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    return NodeTagRead.model_validate(node_tag)


@router.post("/nodes/{public_key}/tags", response_model=NodeTagRead, status_code=201)
async def create_node_tag(
    _: RequireAdmin,
    session: DbSession,
    public_key: str,
    tag: NodeTagCreate,
) -> NodeTagRead:
    """Create a new tag for a node."""
    # Find node
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Check if tag already exists
    existing_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == tag.key)
    )
    existing = session.execute(existing_query).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")

    # Create tag
    node_tag = NodeTag(
        node_id=node.id,
        key=tag.key,
        value=tag.value,
        value_type=tag.value_type,
    )
    session.add(node_tag)
    session.commit()
    session.refresh(node_tag)

    return NodeTagRead.model_validate(node_tag)


@router.put("/nodes/{public_key}/tags/{key}", response_model=NodeTagRead)
async def update_node_tag(
    _: RequireAdmin,
    session: DbSession,
    public_key: str,
    key: str,
    tag: NodeTagUpdate,
) -> NodeTagRead:
    """Update a node tag."""
    # Find node
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Find tag
    tag_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == key)
    )
    node_tag = session.execute(tag_query).scalar_one_or_none()

    if not node_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Update tag
    if tag.value is not None:
        node_tag.value = tag.value
    if tag.value_type is not None:
        node_tag.value_type = tag.value_type

    session.commit()
    session.refresh(node_tag)

    return NodeTagRead.model_validate(node_tag)


@router.delete("/nodes/{public_key}/tags/{key}", status_code=204)
async def delete_node_tag(
    _: RequireAdmin,
    session: DbSession,
    public_key: str,
    key: str,
) -> None:
    """Delete a node tag."""
    # Find node
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Find and delete tag
    tag_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == key)
    )
    node_tag = session.execute(tag_query).scalar_one_or_none()

    if not node_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    session.delete(node_tag)
    session.commit()
