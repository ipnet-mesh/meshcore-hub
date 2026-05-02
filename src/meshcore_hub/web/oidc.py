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
    if not discovery_url.endswith("/.well-known/openid-configuration"):
        discovery_url = discovery_url.rstrip("/") + "/.well-known/openid-configuration"
    scope_list = scopes.strip('"').strip("'").split()
    oauth.register(
        name="oidc",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=discovery_url,
        client_kwargs={"scope": scope_list},
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


def get_session_roles(request: Request, roles_claim: str) -> list[str]:
    """Extract roles from session. Returns list of role name strings."""
    user = get_session_user(request)
    if not user:
        return []
    roles: Any = user.get(roles_claim, [])
    if isinstance(roles, str):
        return [roles]
    if isinstance(roles, list):
        return roles
    return []


def strip_userinfo(userinfo: dict[str, Any], roles_claim: str) -> dict[str, Any]:
    """Strip userinfo to essential fields for session storage."""
    name = (
        userinfo.get("name")
        or userinfo.get("preferred_username")
        or userinfo.get("username")
        or userinfo.get("nickname")
    )
    return {
        "sub": userinfo.get("sub"),
        "name": name,
        "email": userinfo.get("email"),
        "picture": userinfo.get("picture"),
        roles_claim: userinfo.get(roles_claim, []),
    }
