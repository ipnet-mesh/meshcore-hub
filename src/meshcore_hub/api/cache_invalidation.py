"""Cache invalidation helpers for entity mutations.

After any successful write (POST/PUT/DELETE) on a user/admin-mutable entity,
the corresponding read caches must be dropped so the UI reflects the change on
the next page load instead of waiting for TTL expiry.

Cache key layout
----------------
There are two key formats in ``api/cache.py``, and this module must know about
both because they coexist:

1. ``@cached("endpoint_name")`` with no ``key_builder`` stores keys as
   ``{endpoint_name}:{sorted_query_string}`` — examples: ``nodes:``,
   ``profiles:``, ``advertisements:``, ``dashboard/activity:``,
   ``dashboard/packet-breakdown:``.
2. ``@cached(..., key_builder=fn)`` ignores ``endpoint_name`` and uses whatever
   the builder returns. The shared builder pattern across role-aware endpoints
   is ``{request.url.path}:role={role}:{sorted_query_string}``, so the actual
   keys start with the literal URL path — examples: ``/api/v1/channels:``,
   ``/api/v1/routes:``, ``/api/v1/routes/{id}:``,
   ``/api/v1/routes/{id}/history:``, ``/api/v1/dashboard/stats:``.

``CacheBackend.delete(prefix)`` SCANs by ``{prefix}*``, so a single call drops
every key under a namespace (including all role variants and all sub-paths).
Helpers here delete every namespace an entity touches — including cross-entity
embeddings (e.g. adoptions surface inside ``nodes``, ``profiles``, and
``advertisements`` listings).

All helpers are no-ops when ``app.state.redis_cache`` is missing (cache
disabled) and swallow any backend error so a cache outage never breaks a
successful write — matching the resilience pattern in ``RedisCacheBackend``.
"""

import logging
from typing import Optional

from fastapi import Request

from meshcore_hub.common.redis import CacheBackend

logger = logging.getLogger(__name__)


def _cache(request: Request) -> Optional[CacheBackend]:
    """Return the cache backend for this app, or None if caching is disabled."""
    return getattr(request.app.state, "redis_cache", None)


def _drop(request: Request, prefix: str) -> None:
    """Best-effort ``delete(prefix)``; never raises.

    Emits structured log lines so production traces can confirm a mutation
    handler actually fired invalidation and see how many Redis keys were
    deleted. The ``backend=`` field distinguishes ``RedisCacheBackend``
    (real Redis) from ``NullCache`` (Redis disabled) in one glance — useful
    when ``REDIS_ENABLED`` is misconfigured.
    """
    cache = _cache(request)
    if cache is None:
        logger.debug(
            "Cache invalidate skipped (no backend on app.state): prefix=%s",
            prefix,
        )
        return
    logger.info(
        "Cache invalidate start: prefix=%s backend=%s",
        prefix,
        type(cache).__name__,
    )
    try:
        cache.delete(prefix)
        logger.info("Cache invalidate ok: prefix=%s", prefix)
    except Exception as e:
        logger.warning(
            "Cache invalidate error: prefix=%s error=%s",
            prefix,
            e,
        )


def invalidate_channels(request: Request) -> None:
    """Drop cached ``GET /channels`` responses (role-aware, URL-path keys)."""
    _drop(request, "/api/v1/channels")


def invalidate_routes(request: Request) -> None:
    """Drop cached ``GET /routes``, ``/routes/{id}`` and ``/routes/{id}/history``.

    All three endpoints share the ``/api/v1/routes`` URL-path prefix in their
    cache keys (the ``{id}`` and ``{id}/history`` sub-paths glob-match the
    same SCAN), so a single ``delete`` covers them.

    The dashboard's ``GET /dashboard/routes-overview`` endpoint also embeds
    per-route state and history, so it must be invalidated alongside the
    per-route caches. That key lives under the ``dashboard/routes-overview``
    endpoint-name namespace (no ``key_builder``), so it needs its own drop.
    """
    _drop(request, "/api/v1/routes")
    _drop(request, "dashboard/routes-overview")


def invalidate_nodes(request: Request) -> None:
    """Drop cached ``GET /nodes`` responses (endpoint-name keys, no key_builder)."""
    _drop(request, "nodes")


def invalidate_profiles(request: Request) -> None:
    """Drop cached ``GET /user/profiles`` responses (endpoint-name keys)."""
    _drop(request, "profiles")


def invalidate_messages(request: Request) -> None:
    """Drop cached ``GET /messages`` responses (role-aware, URL-path keys)."""
    _drop(request, "/api/v1/messages")


def invalidate_advertisements(request: Request) -> None:
    """Drop cached ``GET /advertisements`` responses (endpoint-name keys)."""
    _drop(request, "advertisements")


def invalidate_dashboard(request: Request) -> None:
    """Drop every cached ``GET /dashboard/*`` response.

    Dashboard endpoints split across both key formats: ``stats`` and
    ``message-activity`` use a ``key_builder`` (URL-path keys under
    ``/api/v1/dashboard``) while ``activity``, ``packet-activity``,
    ``packet-breakdown`` and ``node-count`` use endpoint-name keys under
    ``dashboard``. Delete both prefixes to cover all of them.
    """
    _drop(request, "dashboard")
    _drop(request, "/api/v1/dashboard")
