"""Node adoption API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from meshcore_hub.api.auth import RequireOperatorOrAdmin
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.profile_utils import get_or_create_profile
from meshcore_hub.common.models import Node, UserProfileNode
from meshcore_hub.common.schemas.user_profiles import AdoptedNodeRead, NodeAdoptRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=AdoptedNodeRead, status_code=201)
async def adopt_node(
    adopt_request: NodeAdoptRequest,
    caller_info: RequireOperatorOrAdmin,
    session: DbSession,
    request: Request,
) -> AdoptedNodeRead:
    """Adopt a node. Requires operator or admin role."""
    caller_id, _ = caller_info
    profile = get_or_create_profile(session, caller_id, request)

    public_key = adopt_request.public_key.lower()

    node_query = select(Node).where(Node.public_key == public_key)
    node = session.execute(node_query).scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with public_key '{public_key}' not found",
        )

    existing_query = select(UserProfileNode).where(UserProfileNode.node_id == node.id)
    existing = session.execute(existing_query).scalar_one_or_none()
    if existing:
        if existing.user_profile_id == profile.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Node already adopted by this user",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node already adopted by another user",
        )

    association = UserProfileNode(
        user_profile_id=profile.id,
        node_id=node.id,
    )
    session.add(association)
    session.commit()
    session.refresh(association)

    logger.info(
        "User %s adopted node %s",
        caller_id,
        public_key[:12],
    )

    return AdoptedNodeRead(
        public_key=node.public_key,
        name=node.name,
        adv_type=node.adv_type,
        adopted_at=association.adopted_at,
    )


@router.delete("/{public_key}", status_code=204)
async def release_node(
    public_key: str,
    caller_info: RequireOperatorOrAdmin,
    request: Request,
    session: DbSession,
) -> None:
    """Release (unadopt) a node.

    Operators can only release their own adopted nodes.
    Admins can release any node.
    """
    caller_id, roles = caller_info
    admin_role = getattr(request.app.state, "oidc_role_admin", "admin")
    is_admin = admin_role in roles

    normalized_key = public_key.lower()

    node_query = select(Node).where(Node.public_key == normalized_key)
    node = session.execute(node_query).scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with public_key '{public_key}' not found",
        )

    assoc_query = (
        select(UserProfileNode)
        .where(UserProfileNode.node_id == node.id)
        .options(selectinload(UserProfileNode.user_profile))
    )
    association = session.execute(assoc_query).scalar_one_or_none()
    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node is not adopted",
        )

    if not is_admin and association.user_profile.user_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the adopting user or an admin can release this node",
        )

    session.delete(association)
    session.commit()

    logger.info(
        "User %s released node %s",
        caller_id,
        normalized_key[:12],
    )
