"""Cache decorator for API endpoints."""

import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)


def sorted_query_string(request: Request) -> str:
    """Build a deterministic query string from request params, sorted by key.

    Uses multi_items() so repeated query params (e.g. observed_by) are all
    preserved; items() keeps only the last value of a repeated key, which would
    collapse different filter sets onto the same cache key and serve stale
    responses. Sorting by the full (key, value) tuple keeps the result
    order-independent (observed_by=A&observed_by=B == observed_by=B&observed_by=A).
    """
    params = sorted(request.query_params.multi_items())
    if not params:
        return ""
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


def _compute_etag(serialized_body: str) -> str:
    """Compute a strong ETag header value (quoted hex hash) for a body.

    Uses the first 32 hex chars of SHA-256 — collision-safe for cache keys
    and short enough to fit comfortably in a request header.
    """
    digest = hashlib.sha256(serialized_body.encode("utf-8")).hexdigest()[:32]
    return f'"{digest}"'


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """Return True if the client's If-None-Match header matches the ETag.

    Per RFC 7232 the header may carry a comma-separated list or the wildcard
    ``*``. Weak indicators (``W/``) are accepted on the client side. We do not
    emit weak ETags, but clients are allowed to send them.
    """
    if if_none_match.strip() == "*":
        return True
    for token in if_none_match.split(","):
        candidate = token.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


def _serialize_for_cache(result: Any) -> tuple[Any, str]:
    """Convert a handler result into (body_json, serialized_json) for storage.

    Returns the JSON-compatible body (suitable for JSONResponse) and the
    canonical serialized string used to compute the ETag. Pydantic models are
    dumped via ``model_dump(mode="json")`` so datetimes become ISO strings
    deterministically.
    """
    if hasattr(result, "model_dump"):
        body = result.model_dump(mode="json")
    elif isinstance(result, dict):
        body = result
    else:
        body = result
    serialized = json.dumps(body, default=str)
    return body, serialized


def _store(cache: Any, cache_key: str, result: Any, ttl: int) -> tuple[Any, str]:
    """Serialize, ETag, and store a handler result in the cache.

    Returns ``(body, etag)`` so the caller can return the body to FastAPI
    without re-serializing. Stores the new envelope format
    ``{"body": ..., "etag": "..."}`` so future hits can return the ETag
    without re-hashing.
    """
    body, serialized = _serialize_for_cache(result)
    etag = _compute_etag(serialized)
    envelope = json.dumps({"body": body, "etag": etag})
    try:
        cache.set(cache_key, envelope, ttl)
    except Exception as e:
        logger.warning("Cache store error for %s: %s", cache_key, e)
    return body, etag


def _lookup(cache: Any, cache_key: str, request: Request) -> tuple[Any, str]:
    """Return ``(body, etag)`` on hit, or ``(_MISS, "")`` on miss.

    Reads both the new envelope format ``{"body": ..., "etag": "..."}`` and
    the legacy bare-body format (which carried no ETag). Legacy entries are
    hashed on read so they still serve correctly; natural expiry migrates
    them to the envelope format on the next write.
    """
    try:
        raw = cache.get(cache_key)
    except Exception as e:
        logger.warning("Redis GET error for %s: %s", cache_key, e)
        return _MISS, ""

    if raw is None:
        logger.debug("Cache MISS: %s", cache_key)
        request.state.cache_status = "MISS"
        return _MISS, ""

    logger.debug("Cache HIT: %s", cache_key)
    request.state.cache_status = "HIT"
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Garbage in cache — treat as miss and let the next write repair it.
        request.state.cache_status = "MISS"
        return _MISS, ""

    if isinstance(parsed, dict) and "body" in parsed and "etag" in parsed:
        return parsed["body"], parsed["etag"]
    # Legacy entry: body stored bare, no ETag envelope. Hash on the fly so
    # the client still gets a usable ETag; the next MISS overwrites it with
    # the envelope format.
    serialized = json.dumps(parsed, default=str)
    return parsed, _compute_etag(serialized)


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
                ttl = getattr(request.app.state, ttl_setting, 30)
                # Always advertise the client-cache TTL so the middleware can
                # emit Cache-Control regardless of whether Redis is configured.
                request.state.cache_control_ttl = ttl

                if cache is None:
                    return await func(*args, **kwargs)

                cache_key = _build_cache_key(request, endpoint_name, key_builder)
                body, etag = _lookup(cache, cache_key, request)

                if body is _MISS:
                    # MISS: call the handler, store, and return the original
                    # result so FastAPI's response_model handling still sees
                    # the Pydantic model (not the JSON-dumped dict).
                    result = await func(*args, **kwargs)
                    _, etag = _store(cache, cache_key, result, ttl)
                    return_value = result
                else:
                    # HIT: only have the JSON-deserialized body.
                    return_value = body

                # ETag + If-None-Match handling.
                request.state.api_etag = etag
                if_none_match = request.headers.get("if-none-match")
                if if_none_match and _etag_matches(if_none_match, etag):
                    return Response(
                        status_code=304,
                        headers={"ETag": etag},
                    )
                return return_value

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _find_request(kwargs)
            cache = getattr(request.app.state, "redis_cache", None)
            ttl = getattr(request.app.state, ttl_setting, 30)
            request.state.cache_control_ttl = ttl

            if cache is None:
                return func(*args, **kwargs)

            cache_key = _build_cache_key(request, endpoint_name, key_builder)
            body, etag = _lookup(cache, cache_key, request)

            if body is _MISS:
                result = func(*args, **kwargs)
                _, etag = _store(cache, cache_key, result, ttl)
                return_value = result
            else:
                return_value = body

            request.state.api_etag = etag
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and _etag_matches(if_none_match, etag):
                return Response(
                    status_code=304,
                    headers={"ETag": etag},
                )
            return return_value

        return sync_wrapper

    return decorator
