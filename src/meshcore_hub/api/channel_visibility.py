"""Shared channel visibility helpers for API routes.

Resolves user roles from proxy-injected headers and determines which
channel indices are visible based on channel visibility levels.
"""

from fastapi import Request
from sqlalchemy import select

from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models.channel import Channel

VISIBILITY_LEVELS = {"public": 0, "member": 1, "operator": 2, "admin": 3}


def resolve_user_role(request: Request) -> str | None:
    """Resolve the user's highest role from X-User-Roles header."""
    roles_header = request.headers.get("x-user-roles", "")
    if not roles_header:
        return None
    roles = {r.strip() for r in roles_header.split(",") if r.strip()}
    admin_role = getattr(request.app.state, "oidc_role_admin", "admin")
    operator_role = getattr(request.app.state, "oidc_role_operator", "operator")
    member_role = getattr(request.app.state, "oidc_role_member", "member")
    if admin_role in roles:
        return "admin"
    if operator_role in roles:
        return "operator"
    if member_role in roles:
        return "member"
    return None


def get_max_visibility_level(role: str | None) -> int:
    """Get the maximum visibility level for a given role.

    Returns 0 for anonymous users (public only).
    """
    if role is None:
        return 0
    return VISIBILITY_LEVELS.get(role, 0)


def get_visible_channel_indices(
    session: DbSession,
    max_level: int,
) -> set[int]:
    """Get set of visible channel_idx values based on visibility level.

    Only returns indices for channels whose visibility level is at most
    max_level (lower number = more permissive). The built-in Public
    channel (idx 17) is always included.
    """
    channels = session.execute(select(Channel)).scalars().all()
    visible: set[int] = set()
    for ch in channels:
        level = VISIBILITY_LEVELS.get(ch.visibility, 0)
        if level <= max_level:
            idx = int(ch.channel_hash, 16)
            visible.add(idx)
    visible.add(17)  # Built-in Public channel is always visible
    return visible


def get_all_known_channel_indices(session: DbSession) -> set[int]:
    """Get set of all known channel_idx values from DB."""
    channels = session.execute(select(Channel)).scalars().all()
    return {int(ch.channel_hash, 16) for ch in channels}
