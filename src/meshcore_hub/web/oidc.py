"""OIDC/OAuth2 authentication using Authlib."""

import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request

logger = logging.getLogger(__name__)

oauth = OAuth()


def init_oidc(
    client_id: str, client_secret: str, discovery_url: str, scopes: str
) -> None:
    """Register the OIDC client on the OAuth registry."""
    oauth.register(
        name="oidc",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=discovery_url,
        client_kwargs={"scope": scopes},
    )


async def validate_discovery() -> bool:
    """Eagerly validate OIDC discovery endpoint is reachable."""
    try:
        await oauth.oidc.load_server_metadata()
        return True
    except Exception as e:
        logger.error("OIDC discovery failed: %s", e)
        return False


def get_session_user(request: Request) -> dict[str, Any] | None:
    """Get current user from session, or None."""
    return request.session.get("user")


def get_user_roles(
    request: Request, roles_claim: str, admin_role: str, member_role: str
) -> tuple[bool, bool]:
    """Extract roles from session. Returns (is_member, is_admin)."""
    user = get_session_user(request)
    if not user:
        return False, False
    roles: Any = user.get(roles_claim, [])
    if isinstance(roles, str):
        roles = [roles]
    is_admin = admin_role in roles
    is_member = member_role in roles
    return is_member, is_admin


def strip_userinfo(userinfo: dict[str, Any], roles_claim: str) -> dict[str, Any]:
    """Strip userinfo to essential fields for session storage."""
    return {
        "sub": userinfo.get("sub"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "picture": userinfo.get("picture"),
        roles_claim: userinfo.get(roles_claim, []),
    }
