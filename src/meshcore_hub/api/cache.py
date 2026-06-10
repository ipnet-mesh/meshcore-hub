"""Cache decorator for API endpoints."""

import functools
import json
import logging
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from fastapi import Request

logger = logging.getLogger(__name__)


def sorted_query_string(request: Request) -> str:
    """Build a deterministic query string from request params, sorted by key."""
    params = list(request.query_params.items())
    if not params:
        return ""
    params.sort(key=lambda p: p[0])
    return urlencode(params)


def _find_request(kwargs: dict[str, Any]) -> Request:
    """Locate the Request object in handler kwargs by type inspection."""
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    raise TypeError("No Request parameter found in handler arguments")


def cached(
    endpoint_name: str,
    ttl_setting: str = "redis_cache_ttl",
    key_builder: Optional[Callable[[Request], str]] = None,
) -> Callable[..., Any]:
    """Decorator factory for caching API endpoint responses.

    Args:
        endpoint_name: Cache key prefix for this endpoint.
        ttl_setting: Attribute name on app.state holding the TTL value.
        key_builder: Optional custom function to build cache key suffix.
                     Receives the Request, returns a string suffix.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _find_request(kwargs)
            cache = getattr(request.app.state, "redis_cache", None)
            if cache is None:
                return await func(*args, **kwargs)

            ttl = getattr(request.app.state, ttl_setting, 30)

            if key_builder is not None:
                cache_key = key_builder(request)
            else:
                cache_key = f"{endpoint_name}:{sorted_query_string(request)}"

            try:
                cached_value = cache.get(cache_key)
            except Exception as e:
                logger.warning("Redis GET error for %s: %s", cache_key, e)
                cached_value = None

            if cached_value is not None:
                logger.debug("Cache HIT: %s", cache_key)
                request.state.cache_status = "HIT"
                return json.loads(cached_value)

            logger.debug("Cache MISS: %s", cache_key)
            request.state.cache_status = "MISS"

            result = await func(*args, **kwargs)

            try:
                if hasattr(result, "model_dump"):
                    serialized = json.dumps(result.model_dump(mode="json"))
                elif isinstance(result, dict):
                    serialized = json.dumps(result)
                else:
                    serialized = json.dumps(result, default=str)
                cache.set(cache_key, serialized, ttl)
            except Exception as e:
                logger.warning("Cache store error for %s: %s", cache_key, e)

            return result

        return wrapper

    return decorator
