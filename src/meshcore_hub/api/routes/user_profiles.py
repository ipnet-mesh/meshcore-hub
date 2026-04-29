"""User profile API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from meshcore_hub.api.auth import RequireUserOwner, X_USER_NAME_HEADER
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import UserProfile
from meshcore_hub.common.schemas.user_profiles import (
    AdoptedNodeRead,
    UserProfileRead,
    UserProfileUpdate,
    UserProfileWithNodes,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_owner(user_id: str, requested_id: str) -> None:
    """Verify the authenticated user matches the requested user_id."""
    if user_id != requested_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot access another user's profile",
        )


def _get_or_create_profile(
    session: DbSession, user_id: str, request: Request
) -> UserProfile:
    """Get existing profile or create a new one with name from IdP."""
    query = select(UserProfile).where(UserProfile.user_id == user_id)
    profile = session.execute(query).scalar_one_or_none()
    if profile:
        return profile

    idp_name = request.headers.get(X_USER_NAME_HEADER) or None
    profile = UserProfile(user_id=user_id, name=idp_name)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    logger.info("Created new user profile for user_id=%s", user_id)
    return profile


@router.get("/profile/{user_id}", response_model=UserProfileWithNodes)
async def get_profile(
    user_id: str,
    caller_id: RequireUserOwner,
    session: DbSession,
    request: Request,
) -> UserProfileWithNodes:
    """Get or create a user profile. Auto-creates on first access."""
    _verify_owner(caller_id, user_id)
    profile = _get_or_create_profile(session, user_id, request)

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

    return UserProfileWithNodes(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        callsign=profile.callsign,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        nodes=adopted_nodes,
    )


@router.put("/profile/{user_id}", response_model=UserProfileRead)
async def update_profile(
    user_id: str,
    profile_update: UserProfileUpdate,
    caller_id: RequireUserOwner,
    session: DbSession,
    request: Request,
) -> UserProfileRead:
    """Update a user profile."""
    _verify_owner(caller_id, user_id)
    profile = _get_or_create_profile(session, user_id, request)

    if profile_update.name is not None:
        profile.name = profile_update.name
    if profile_update.callsign is not None:
        profile.callsign = profile_update.callsign

    session.commit()
    session.refresh(profile)

    return UserProfileRead.model_validate(profile)
