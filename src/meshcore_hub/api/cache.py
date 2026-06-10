"""Cache decorator for API endpoints."""

import functools
import inspect
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


# Sentinel distinguishing "cache miss" from "cache hit holding a JSON null".
_MISS = object()


def _build_cache_key(
    request: Request,
    endpoint_name: str,
    key_builder: Optional[Callable[[Request], str]],
) -> str:
    """Build the cache key for a request."""
    if key_builder is not None:
        return key_builder(request)
    return f"{endpoint_name}:{sorted_query_string(request)}"


def _lookup(cache: Any, cache_key: str, request: Request) -> Any:
    """Return the cached value, or _MISS, and record the cache status."""
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
    return _MISS


def _store(cache: Any, cache_key: str, result: Any, ttl: int) -> None:
    """Serialize and store a handler result in the cache."""
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
        # Async handlers keep an async wrapper (runs on the event loop); sync
        # handlers get a sync wrapper so FastAPI runs them in its threadpool,
        # keeping blocking DB/Redis calls off the event loop.
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                request = _find_request(kwargs)
                cache = getattr(request.app.state, "redis_cache", None)
                if cache is None:
                    return await func(*args, **kwargs)

                ttl = getattr(request.app.state, ttl_setting, 30)
                cache_key = _build_cache_key(request, endpoint_name, key_builder)

                cached = _lookup(cache, cache_key, request)
                if cached is not _MISS:
                    return cached

                result = await func(*args, **kwargs)
                _store(cache, cache_key, result, ttl)
                return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _find_request(kwargs)
            cache = getattr(request.app.state, "redis_cache", None)
            if cache is None:
                return func(*args, **kwargs)

            ttl = getattr(request.app.state, ttl_setting, 30)
            cache_key = _build_cache_key(request, endpoint_name, key_builder)

            cached = _lookup(cache, cache_key, request)
            if cached is not _MISS:
                return cached

            result = func(*args, **kwargs)
            _store(cache, cache_key, result, ttl)
            return result

        return sync_wrapper

    return decorator
