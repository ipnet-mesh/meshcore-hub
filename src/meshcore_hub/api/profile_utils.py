"""Shared utility for getting or creating user profiles."""

import logging

from fastapi import Request
from sqlalchemy import select

from meshcore_hub.api.auth import X_USER_NAME_HEADER, X_USER_ROLES_HEADER
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import UserProfile

logger = logging.getLogger(__name__)


def get_or_create_profile(
    session: DbSession,
    user_id: str,
    request: Request,
) -> UserProfile:
    """Get existing profile or create a new one, updating roles from headers.

    Looks up by ``user_id``.  If not found, creates a new profile with the
    name from the ``X-User-Name`` header.  On every call the ``roles`` column
    is updated from the ``X-User-Roles`` header so IdP role changes are
    reflected on the next authenticated request.

    Args:
        session: SQLAlchemy database session.
        user_id: OIDC subject identifier.
        request: FastAPI request (for header access).

    Returns:
        The resolved :class:`UserProfile` instance.
    """
    query = select(UserProfile).where(UserProfile.user_id == user_id)
    profile = session.execute(query).scalar_one_or_none()
    if not profile:
        idp_name = request.headers.get(X_USER_NAME_HEADER) or None
        profile = UserProfile(user_id=user_id, name=idp_name)
        logger.info("Created new user profile for user_id=%s", user_id)

    roles_header = request.headers.get(X_USER_ROLES_HEADER, "")
    profile.roles = roles_header or None

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
