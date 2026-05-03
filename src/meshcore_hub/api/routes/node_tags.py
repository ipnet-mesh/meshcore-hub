"""Node tag API routes."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from meshcore_hub.api.auth import RequireOperatorOrAdmin, RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node, NodeTag, UserProfile, UserProfileNode
from meshcore_hub.common.schemas.nodes import (
    NodeTagCreate,
    NodeTagRead,
    NodeTagUpdate,
    validate_and_coerce_tag_value,
)

router = APIRouter()


def _check_tag_access(
    session: DbSession,
    caller_info: tuple[str, list[str]],
    request: Request,
    node_id: str,
) -> None:
    """Raise 403 if operator tries to edit tags on a non-adopted node.

    Admins bypass the ownership check.
    """
    caller_id, roles = caller_info
    admin_role: str = getattr(request.app.state, "oidc_role_admin", "admin")
    if admin_role in roles:
        return

    profile_query = select(UserProfile).where(UserProfile.user_id == caller_id)
    profile = session.execute(profile_query).scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit tags on nodes you have adopted",
        )

    adoption_query = select(UserProfileNode).where(
        (UserProfileNode.user_profile_id == profile.id)
        & (UserProfileNode.node_id == node_id)
    )
    adoption = session.execute(adoption_query).scalar_one_or_none()
    if not adoption:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit tags on nodes you have adopted",
        )


@router.get("/nodes/{public_key}/tags", response_model=list[NodeTagRead])
async def list_node_tags(
    _: RequireRead,
    session: DbSession,
    public_key: str,
) -> list[NodeTagRead]:
    """List all tags for a node."""
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return [NodeTagRead.model_validate(t) for t in node.tags]


@router.post("/nodes/{public_key}/tags", response_model=NodeTagRead, status_code=201)
async def create_node_tag(
    caller_info: RequireOperatorOrAdmin,
    session: DbSession,
    request: Request,
    public_key: str,
    tag: NodeTagCreate,
) -> NodeTagRead:
    """Create a new tag for a node."""
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    _check_tag_access(session, caller_info, request, node.id)

    existing_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == tag.key)
    )
    existing = session.execute(existing_query).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")

    coerced_value = tag.value
    try:
        coerced_value = validate_and_coerce_tag_value(tag.value, tag.value_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    node_tag = NodeTag(
        node_id=node.id,
        key=tag.key,
        value=coerced_value,
        value_type=tag.value_type,
    )
    session.add(node_tag)
    session.commit()
    session.refresh(node_tag)

    return NodeTagRead.model_validate(node_tag)


@router.put("/nodes/{public_key}/tags/{key}", response_model=NodeTagRead)
async def update_node_tag(
    caller_info: RequireOperatorOrAdmin,
    session: DbSession,
    request: Request,
    public_key: str,
    key: str,
    tag: NodeTagUpdate,
) -> NodeTagRead:
    """Update a node tag."""
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    _check_tag_access(session, caller_info, request, node.id)

    tag_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == key)
    )
    node_tag = session.execute(tag_query).scalar_one_or_none()

    if not node_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    effective_value = tag.value if tag.value is not None else node_tag.value
    effective_type = (
        tag.value_type if tag.value_type is not None else node_tag.value_type
    )

    try:
        effective_value = validate_and_coerce_tag_value(effective_value, effective_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if tag.value is not None:
        node_tag.value = effective_value
    if tag.value_type is not None:
        node_tag.value_type = tag.value_type
    if (
        tag.value is not None
        and tag.value_type is None
        and effective_value != tag.value
    ):
        node_tag.value = effective_value

    session.commit()
    session.refresh(node_tag)

    return NodeTagRead.model_validate(node_tag)


@router.delete("/nodes/{public_key}/tags/{key}", status_code=204)
async def delete_node_tag(
    caller_info: RequireOperatorOrAdmin,
    session: DbSession,
    request: Request,
    public_key: str,
    key: str,
) -> None:
    """Delete a node tag."""
    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    _check_tag_access(session, caller_info, request, node.id)

    tag_query = select(NodeTag).where(
        (NodeTag.node_id == node.id) & (NodeTag.key == key)
    )
    node_tag = session.execute(tag_query).scalar_one_or_none()

    if not node_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    session.delete(node_tag)
    session.commit()
