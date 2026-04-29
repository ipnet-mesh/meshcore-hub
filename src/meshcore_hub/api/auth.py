"""Authentication middleware for the API."""

import hmac
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

# Header constants for proxy-injected user identity
X_USER_ID_HEADER = "X-User-Id"
X_USER_ROLES_HEADER = "X-User-Roles"


def get_api_keys(request: Request) -> tuple[str | None, str | None]:
    """Get API keys from app state.

    Args:
        request: FastAPI request

    Returns:
        Tuple of (read_key, admin_key)
    """
    return (
        getattr(request.app.state, "read_key", None),
        getattr(request.app.state, "admin_key", None),
    )


async def get_current_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> str | None:
    """Extract bearer token from request.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        Token string or None
    """
    if credentials is None:
        return None
    return credentials.credentials


async def require_read(
    request: Request,
    token: Annotated[str | None, Depends(get_current_token)],
) -> str | None:
    """Require read-level authentication.

    Allows access if:
    - No API keys are configured (open access)
    - Token matches read key
    - Token matches admin key

    Args:
        request: FastAPI request
        token: Bearer token

    Returns:
        Token string

    Raises:
        HTTPException: If authentication fails
    """
    read_key, admin_key = get_api_keys(request)

    # If no keys configured, allow access
    if not read_key and not admin_key:
        return token

    # Require token if keys are configured
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token matches any key
    if (read_key and hmac.compare_digest(token, read_key)) or (
        admin_key and hmac.compare_digest(token, admin_key)
    ):
        return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(
    request: Request,
    token: Annotated[str | None, Depends(get_current_token)],
) -> str:
    """Require admin-level authentication.

    Allows access if:
    - No admin key is configured (open access)
    - Token matches admin key

    Args:
        request: FastAPI request
        token: Bearer token

    Returns:
        Token string

    Raises:
        HTTPException: If authentication fails
    """
    read_key, admin_key = get_api_keys(request)

    # If no admin key configured, allow access
    if not admin_key:
        return token or ""

    # Require token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token matches admin key
    if hmac.compare_digest(token, admin_key):
        return token

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


# Dependency types for use in routes
RequireRead = Annotated[str | None, Depends(require_read)]
RequireAdmin = Annotated[str, Depends(require_admin)]


async def require_user_owner(
    request: Request,
    token: Annotated[str | None, Depends(get_current_token)],
) -> str:
    """Require an authenticated user identity via X-User-Id header.

    The web proxy injects X-User-Id when an OIDC user is authenticated.
    The header is trusted because only the proxy has the API key.

    Returns:
        The user_id string from the X-User-Id header.

    Raises:
        HTTPException: 401 if no valid API key or no X-User-Id header.
    """
    read_key, admin_key = get_api_keys(request)

    if read_key or admin_key:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        key_valid = (read_key and hmac.compare_digest(token, read_key)) or (
            admin_key and hmac.compare_digest(token, admin_key)
        )
        if not key_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id = request.headers.get(X_USER_ID_HEADER)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity required",
        )

    return user_id


async def require_operator(
    request: Request,
    token: Annotated[str | None, Depends(get_current_token)],
) -> tuple[str, list[str]]:
    """Require an authenticated user with the operator role.

    Checks X-User-Roles header (comma-separated) for the operator role.
    Also validates API key and X-User-Id header.

    Returns:
        Tuple of (user_id, roles_list).

    Raises:
        HTTPException: 401 if not authenticated, 403 if not operator.
    """
    user_id = await require_user_owner(request, token)

    roles_header = request.headers.get(X_USER_ROLES_HEADER, "")
    roles = [r.strip() for r in roles_header.split(",") if r.strip()]

    operator_role = getattr(request.app.state, "oidc_role_operator", "operator")
    if operator_role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator role required",
        )

    return user_id, roles


async def require_operator_or_admin(
    request: Request,
    token: Annotated[str | None, Depends(get_current_token)],
) -> tuple[str, list[str]]:
    """Require an authenticated user with operator or admin role.

    Returns:
        Tuple of (user_id, roles_list).

    Raises:
        HTTPException: 401 if not authenticated, 403 if not operator or admin.
    """
    user_id = await require_user_owner(request, token)

    roles_header = request.headers.get(X_USER_ROLES_HEADER, "")
    roles = [r.strip() for r in roles_header.split(",") if r.strip()]

    operator_role = getattr(request.app.state, "oidc_role_operator", "operator")
    admin_role = getattr(request.app.state, "oidc_role_admin", "admin")
    if operator_role not in roles and admin_role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or admin role required",
        )

    return user_id, roles


RequireUserOwner = Annotated[str, Depends(require_user_owner)]
RequireOperator = Annotated[tuple[str, list[str]], Depends(require_operator)]
RequireOperatorOrAdmin = Annotated[
    tuple[str, list[str]], Depends(require_operator_or_admin)
]
