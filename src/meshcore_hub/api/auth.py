"""Authentication middleware for the API."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


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
    if token == read_key or token == admin_key:
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
    if token == admin_key:
        return token

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


# Dependency types for use in routes
RequireRead = Annotated[str | None, Depends(require_read)]
RequireAdmin = Annotated[str, Depends(require_admin)]
