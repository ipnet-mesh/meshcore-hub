"""User profile API routes."""

import logging

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from meshcore_hub.api.auth import RequireRead, RequireUserOwner, X_USER_ID_HEADER
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.profile_utils import get_or_create_profile
from meshcore_hub.common.models import UserProfile
from meshcore_hub.common.models.user_profile_node import UserProfileNode
from meshcore_hub.common.schemas.user_profiles import (
    AdoptedNodeRead,
    UserProfileList,
    UserProfileListItem,
    UserProfilePublicWithNodes,
    UserProfileRead,
    UserProfileUpdate,
    UserProfileWithNodes,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_adopted_nodes(profile: UserProfile) -> list[AdoptedNodeRead]:
    """Extract adopted node list from a profile's eager-loaded associations."""
    adopted_nodes = []
    for assoc in profile.node_associations:
        adopted_nodes.append(
            AdoptedNodeRead(
                public_key=assoc.node.public_key,
                name=assoc.node.name,
                adv_type=assoc.node.adv_type,
                adopted_at=assoc.adopted_at,
            )
        )
    return adopted_nodes


@router.get("/profiles", response_model=UserProfileList)
async def list_profiles(
    _: RequireRead,
    session: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> UserProfileList:
    """List all user profiles with node counts. No user_id exposed."""
    count_query = select(func.count(UserProfile.id))
    total = session.execute(count_query).scalar() or 0

    query = (
        select(UserProfile)
        .options(
            selectinload(UserProfile.node_associations).selectinload(
                UserProfileNode.node
            )
        )
        .order_by(UserProfile.name)
        .offset(offset)
        .limit(limit)
    )
    profiles = session.execute(query).scalars().all()

    items = []
    for profile in profiles:
        adopted_nodes = []
        for assoc in profile.node_associations:
            adopted_nodes.append(
                AdoptedNodeRead(
                    public_key=assoc.node.public_key,
                    name=assoc.node.name,
                    adv_type=assoc.node.adv_type,
                    adopted_at=assoc.adopted_at,
                )
            )
        items.append(
            UserProfileListItem(
                id=profile.id,
                name=profile.name,
                callsign=profile.callsign,
                roles=profile.role_list,
                node_count=len(profile.node_associations),
                adopted_nodes=adopted_nodes,
            )
        )

    return UserProfileList(items=items, total=total, limit=limit, offset=offset)


@router.get("/profile/me", response_model=UserProfileWithNodes)
async def get_my_profile(
    request: Request,
    session: DbSession,
) -> UserProfileWithNodes:
    """Get the current user's profile (via X-User-Id header).

    Auto-creates the profile if it doesn't exist. Returns the full
    profile including user_id and adopted nodes.
    """
    oidc_user_id = request.headers.get(X_USER_ID_HEADER)
    if not oidc_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity required",
        )

    profile = get_or_create_profile(session, oidc_user_id, request)
    return UserProfileWithNodes(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        callsign=profile.callsign,
        roles=profile.role_list,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        nodes=_build_adopted_nodes(profile),
    )


@router.get("/profile/{profile_id}")
async def get_profile(
    profile_id: str,
    request: Request,
    session: DbSession,
) -> UserProfilePublicWithNodes | UserProfileWithNodes:
    """Get a user profile by UUID.

    Public access is allowed for viewing any profile. If the caller is the
    owner (authenticated with matching user_id), the full profile including
    user_id is returned and the profile is auto-created if missing.
    """
    oidc_user_id = request.headers.get(X_USER_ID_HEADER)

    if oidc_user_id:
        caller_query = select(UserProfile).where(UserProfile.user_id == oidc_user_id)
        caller_profile = session.execute(caller_query).scalar_one_or_none()
        if caller_profile and str(caller_profile.id) == str(profile_id):
            profile = get_or_create_profile(session, oidc_user_id, request)
            return UserProfileWithNodes(
                id=profile.id,
                user_id=profile.user_id,
                name=profile.name,
                callsign=profile.callsign,
                roles=profile.role_list,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
                nodes=_build_adopted_nodes(profile),
            )

    public_query = select(UserProfile).where(UserProfile.id == profile_id)
    public_profile = session.execute(public_query).scalar_one_or_none()
    if not public_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    return UserProfilePublicWithNodes(
        id=public_profile.id,
        name=public_profile.name,
        callsign=public_profile.callsign,
        roles=public_profile.role_list,
        created_at=public_profile.created_at,
        updated_at=public_profile.updated_at,
        nodes=_build_adopted_nodes(public_profile),
    )


@router.put("/profile/{profile_id}", response_model=UserProfileRead)
async def update_profile(
    profile_id: str,
    profile_update: UserProfileUpdate,
    caller_id: RequireUserOwner,
    session: DbSession,
    request: Request,
) -> UserProfileRead:
    """Update a user profile. Only the owner or admin can update."""
    profile_query = select(UserProfile).where(UserProfile.id == profile_id)
    profile = session.execute(profile_query).scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    if profile.user_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot modify another user's profile",
        )

    if profile_update.name is not None:
        profile.name = profile_update.name
    if profile_update.callsign is not None:
        profile.callsign = profile_update.callsign

    session.commit()
    session.refresh(profile)

    return UserProfileRead.model_validate(profile)
