# Redis Caching Layer for API Endpoints

## Summary

Add a Redis-backed caching layer to the MeshCore Hub API to reduce database load and improve response times for read-heavy endpoints (Nodes, Messages, Advertisements, Channels, Map, Dashboard). The cache TTL should be short enough (defaulting to match the web dashboard's 30-second auto-refresh interval) to preserve near-real-time updates. Redis will be added as an optional service to the Docker Compose stack, configurable via environment variables, with graceful fallback to no-cache operation when Redis is unavailable.

## Background & Motivation

The MeshCore Hub API currently executes every read query directly against SQLite on every request. The web dashboard's SPA auto-refreshes list pages every 30 seconds (`WEB_AUTO_REFRESH_SECONDS`), meaning each active browser session generates repeated identical queries. As the network grows (more nodes, more advertisements, more messages), these queries become increasingly expensive -- particularly the Nodes list with its multi-join filters (tags, adoptions, observers), the Dashboard stats endpoint (which runs ~15 separate SQL queries), and the Map data endpoint.

The metrics endpoint (`api/metrics.py:30`) already implements an in-process TTL cache pattern, but it uses a module-level dict -- this doesn't scale across API worker processes or support cache invalidation. A Redis-backed approach provides:

- **Shared cache across workers**: Multiple uvicorn workers or API containers share the same cache
- **Configurable TTL per endpoint group**: Dashboard stats can cache longer than node lists
- **Graceful degradation**: If Redis is down, requests fall through to the database (no errors)
- **Foundation for future scaling**: Enables horizontal API scaling behind a load balancer

### Current Query Load Profile

| Endpoint | Query Complexity | Typical Call Frequency |
|----------|-----------------|----------------------|
| `GET /api/v1/dashboard/stats` | ~15 SQL queries (counts, joins, subqueries) | Every 30s per browser |
| `GET /api/v1/nodes` | Multi-join with tag/adoption/observer filters | Every 30s per browser |
| `GET /api/v1/advertisements` | Aliased joins, observer lookups | Every 30s per browser |
| `GET /api/v1/messages` | Channel visibility filtering, observer lookups | Every 30s per browser |
| `GET /api/v1/channels` | Simple select with visibility filter | Every 30s per browser |

## Goals

- Reduce database query load by caching API responses in Redis
- Keep cache TTL aligned with the web auto-refresh interval (default 30s) for near-real-time UX
- Make Redis fully optional -- the API works identically without Redis (no errors, no performance regression)
- Support per-endpoint-group TTL configuration via environment variables
- Add Redis service to `docker-compose.yml` for out-of-the-box Docker deployments
- Support both synchronous and async Redis clients for future async migration

## Non-Goals

- Caching write endpoints (POST, PUT, DELETE) -- these always hit the database directly
- Caching authenticated/per-user responses (e.g., user-specific channel visibility) -- cache only public responses or cache per-role
- Cache warming or pre-computation -- rely on natural request patterns to populate cache
- Replacing SQLite with Redis for data storage -- Redis is cache-only
- Client-side caching (browser Cache-Control headers) -- this is already handled by the web middleware for static assets
- Caching the Prometheus metrics endpoint -- it already has its own TTL cache pattern
- Caching the web `/map/data` endpoint -- it lives in `web/app.py` (not the API) and its heavy query work is already cached via `GET /api/v1/nodes`
- Full cache invalidation on write events (e.g., invalidate node cache when a new node is seen by the collector) -- future enhancement

## Requirements

### Functional Requirements

1. Redis cache is used for GET endpoints: `/api/v1/nodes`, `/api/v1/advertisements`, `/api/v1/messages`, `/api/v1/channels`, and `/api/v1/dashboard/*`
2. Cache keys include the full request query string to differentiate filtered/paginated responses (e.g., `nodes:?limit=50&offset=0&sort=last_seen`). For role-sensitive endpoints (messages, channels, dashboard stats, message-activity), the resolved user role is included in the cache key as `role=anonymous` (for unauthenticated/`None`), `role=member`, `role=operator`, or `role=admin`.
3. Cached responses are served with correct `X-Cache: HIT` / `X-Cache: MISS` headers for observability
4. When Redis is not configured or unreachable, the API falls back to direct database queries with no errors
5. Cache TTL defaults to the web auto-refresh interval (30 seconds) and is configurable per endpoint group via `REDIS_CACHE_TTL` (default) and `REDIS_CACHE_TTL_DASHBOARD` (dashboard override)
6. Cache can be globally disabled via `REDIS_ENABLED=false`
7. Cache is bypassed for authenticated admin/operator write operations (no stale data issues)
8. Health check endpoint (`/health/ready`) includes Redis connectivity status when configured

### Technical Requirements

1. Use `redis[hiredis]` Python package (binary protocol parser for performance)
2. Redis connection managed via a singleton connection pool, initialized during FastAPI lifespan startup
3. All Redis operations use timeouts and exception handling -- never block the API on Redis failures
4. Configuration via environment variables matching existing patterns (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`)
5. Cache serialization uses JSON (not pickle) for safety and debuggability
6. Docker Compose includes Redis service with persistent volume and health check
7. Existing tests pass without Redis (tests mock or disable the cache layer)

## Implementation Plan

### Phase 1: Configuration & Redis Client

- Add `redis[hiredis]` to `dependencies` in `pyproject.toml`
- Add `redis` to mypy ignore list in `pyproject.toml` (add `"redis.*"` to `[[tool.mypy.overrides]]` ignore list, consistent with existing pattern for `paho.mqtt`, etc.)
- Add `RedisSettings` or extend `APISettings` in `common/config.py` with:
  - `REDIS_ENABLED: bool = False` (code default; Docker Compose overrides to `true` via `REDIS_ENABLED:-true`)
  - `REDIS_HOST: str = "localhost"`
  - `REDIS_PORT: int = 6379`
  - `REDIS_DB: int = 0`
  - `REDIS_PASSWORD: Optional[str] = None`
  - `REDIS_KEY_PREFIX: str = "hub"` (prefix for all cache keys, enables multiple Hub instances to share one Redis without key collisions)
  - `REDIS_CACHE_TTL: int = 30` (default cache TTL in seconds, aligned with `WEB_AUTO_REFRESH_SECONDS`)
  - `REDIS_CACHE_TTL_DASHBOARD: int = 30` (override for all `/dashboard/*` endpoints)
- Create `common/redis.py` with:
  - `RedisClient` class wrapping a `redis.Redis` connection pool
  - `get_redis()` / `get_redis_settings()` helper functions
  - `CacheBackend` protocol/class with `get(key)`, `set(key, value, ttl)`, `delete(prefix)` methods
  - A `NullCache` no-op implementation for when Redis is disabled
- Add Redis parameters to `create_app()` in `api/app.py` (matching existing parameter pattern): `redis_enabled`, `redis_host`, `redis_port`, `redis_db`, `redis_password`, `redis_key_prefix`, `redis_cache_ttl`, `redis_cache_ttl_dashboard`. Store them on `app.state` during `create_app()` (same pattern as `app.state.database_url`, `app.state.metrics_cache_ttl`).
- Add corresponding Click options to `api/cli.py` and pass them through to `create_app()` (same pattern as `--metrics-cache-ttl` → `metrics_cache_ttl`).

> **Note — reload mode**: When running `meshcore-hub api --reload`, uvicorn uses the factory pattern (calling `create_app()` with no arguments), so all parameters default to their code defaults. This means `REDIS_ENABLED=false` (safe fallback, no Redis) in reload mode. This is the same pre-existing limitation that affects `metrics_cache_ttl` and `metrics_enabled` in reload mode.

### Phase 2: Cache Middleware / Dependency

- Create `api/cache.py` with:
  - `sorted_query_string(request: Request) -> str`: extracts query params from the Request, sorts them by key, URL-encodes each, and returns a deterministic string (e.g., `limit=50&offset=0`). Empty query string returns `""`.
  - `CacheKey` builder: generates deterministic keys from `REDIS_KEY_PREFIX` + endpoint path + sorted query params + user role (for role-sensitive endpoints like channels/messages). Role is resolved via `resolve_user_role(request)` — `None` is mapped to `"anonymous"` in the key. Example keys: `hub:nodes:limit=50&offset=0`, `hub:messages:role=anonymous:limit=50`, `hub:messages:role=admin:limit=50`, `hub-stg:dashboard:stats:role=member:`
  - `cached_response()` helper/decorator that:
    1. Checks Redis for a cached JSON response
    2. On hit: returns the cached response with `X-Cache: HIT` header
    3. On miss: executes the route handler, stores the result in Redis with TTL, returns with `X-Cache: MISS`
    4. On Redis error: logs a warning and falls through to the handler
- Create a FastAPI dependency `get_cache` that provides the cache backend (either Redis or NullCache)
- Initialize Redis connection in the FastAPI lifespan handler (`api/app.py`)
- Add Redis disposal to the lifespan shutdown

### Phase 3: Apply Caching to API Routes

Apply the cache to read endpoints. The approach wraps the route handler logic rather than using middleware, to ensure cache keys include query parameters:

- **`api/routes/nodes.py`**: Cache `list_nodes()` (list endpoint only; single-node lookups by public key are fast enough)
- **`api/routes/advertisements.py`**: Cache `list_advertisements()`
- **`api/routes/messages.py`**: Cache `list_messages()` (include role in cache key for channel visibility)
- **`api/routes/channels.py`**: Cache `list_channels()` (include role in cache key)
- **`api/routes/dashboard.py`**: Cache `get_stats()` (~15 SQL queries), `get_activity()`, `get_message_activity()`, `get_node_count_history()` (all `/dashboard/*` endpoints share `REDIS_CACHE_TTL_DASHBOARD`). Both `get_stats()` and `get_message_activity()` need role-based cache keys (they filter channel counts/messages by visibility).
- **Web map data**: Not cached directly. `/map/data` lives in `web/app.py` (not the API) and its heavy query work is already cached via `GET /api/v1/nodes`. The in-memory aggregation step is lightweight.

Note: The `@cached` decorator requires `request: Request` in the handler's signature to read TTL settings and build cache keys. The following endpoints must gain this parameter:
- `list_nodes()` (routes/nodes.py:50) — currently has no `Request`
- `list_advertisements()` (routes/advertisements.py:47) — currently has no `Request`
- `get_activity()` (routes/dashboard.py:309) — currently has no `Request`
- `get_node_count_history()` (routes/dashboard.py:422) — currently has no `Request`

All other cached endpoints (list_messages, list_channels, get_stats, get_message_activity) already include `request: Request`.

Implementation pattern using the decorator:

**Default (query-string key), uses `REDIS_CACHE_TTL`:**
```python
from meshcore_hub.api.cache import cached

@cached("nodes")
@router.get("", response_model=NodeList)
async def list_nodes(...) -> NodeList:
    # existing logic unchanged
```

**With dashboard TTL override and custom key builder (role-sensitive):**
```python
def dashboard_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"dashboard:stats:role={role}:{sorted_query_string(request)}"
    # produces e.g. "dashboard:stats:role=anonymous:" (unauthenticated, no query params)
    # produces e.g. "dashboard:stats:role=admin:" (admin user, no query params)

@cached("dashboard/stats", ttl_setting="redis_cache_ttl_dashboard", key_builder=dashboard_key_builder)
@router.get("/stats", response_model=DashboardStats)
async def get_stats(...) -> DashboardStats:
    # existing logic unchanged

def messages_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"messages:role={role}:{sorted_query_string(request)}"

@cached("messages", key_builder=messages_key_builder)
@router.get("", response_model=MessageList)
async def list_messages(...) -> MessageList:
    # existing logic unchanged
```

`ttl_setting` is optional — when omitted, the decorator uses `redis_cache_ttl` (the default). Only dashboard endpoints need the explicit `redis_cache_ttl_dashboard` override.

### Phase 4: Docker Compose & Environment Variables

- Add Redis service to `docker-compose.yml`:
  ```yaml
  # ==========================================================================
  # Redis Cache - Optional shared cache for API response caching
  # Use --profile cache to start with the bundled Redis, or point
  # REDIS_HOST at an external Redis instance for multi-instance setups.
  # ==========================================================================
  redis:
    image: redis:7-alpine
    container_name: ${COMPOSE_PROJECT_NAME:-hub}-redis
    profiles:
      - all
      - cache
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
  ```
  Redis is in the `cache` profile (not `core`), so `docker compose --profile core up` starts API+web+collector without Redis. Use `--profile cache` (or `--profile all`) to include the bundled Redis. For production multi-instance setups, point `REDIS_HOST` at an external shared Redis and use `REDIS_KEY_PREFIX` to namespace keys per instance (e.g., `hub` for prod, `hub-stg` for staging).
- Add `redis_data` volume to volumes section:
  ```yaml
  redis_data:
    name: ${COMPOSE_PROJECT_NAME:-hub}_redis_data
  ```
- Update `api` service in `docker-compose.yml`:
  - No `depends_on` for Redis — the API must start and work fine without Redis (graceful fallback)
  - Add environment variables:
    ```
    - REDIS_ENABLED=${REDIS_ENABLED:-true}
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - REDIS_PASSWORD=${REDIS_PASSWORD:-}
    - REDIS_KEY_PREFIX=${REDIS_KEY_PREFIX:-hub}
    - REDIS_CACHE_TTL=${REDIS_CACHE_TTL:-30}
    - REDIS_CACHE_TTL_DASHBOARD=${REDIS_CACHE_TTL_DASHBOARD:-30}
    ```
- Note: `REDIS_ENABLED` defaults `false` in code (safe for bare-metal) but `true` in Docker Compose (where Redis is always present). This ensures non-Docker installs work without Redis.
- The `depends_on` is intentionally omitted for Redis — if the API starts before Redis, it falls back gracefully. Redis is optional.
- Update `docker-compose.dev.yml` to expose Redis port for local development:
  ```yaml
  redis:
    ports:
      - "${REDIS_PORT:-6379}:6379"
  ```
- Add Redis env vars to `api/cli.py` Click options

### Phase 5: Health Check & Observability

- Update `/health/ready` endpoint to check Redis connectivity when `REDIS_ENABLED=true`:
  - Uses Redis `PING` command (fast, no data access)
  - Connection failure returns `{"status": "not_ready", "database": "connected", "redis": "unreachable"}` — not a fatal error since Redis is optional
- Log cache hits/misses at DEBUG level for troubleshooting
- Add `X-Cache` response header (`HIT` or `MISS`) to all cached endpoints

**Decorator technical notes:**
- The `@cached` decorator uses `functools.wraps` to preserve the wrapped function's type signature (required for FastAPI's `response_model` resolution)
- TTL values are read from `request.app.state` at invocation time (set during `create_app()` from environment variables), not from module-level globals
- `ttl_setting` is the attribute name on `app.state`; the decorator reads it via `getattr(request.app.state, ttl_setting, 30)`. When omitted, defaults to `"redis_cache_ttl"`
- Default key builder: `"{redis_key_prefix}:{endpoint_name}:{sorted_urlencoded_query_params}"` (e.g., `hub:nodes:limit=50&offset=0`). The `{redis_key_prefix}` component is read from `app.state.redis_key_prefix` by the `CacheBackend`, not by individual `key_builder` callbacks
- Custom `key_builder` receives the `Request` object and returns a string key (suffix only — the `CacheBackend` prepends the key prefix)
- The decorator wrapper locates the `Request` parameter from the handler's arguments by type (inspecting `kwargs` for a `Request` instance). All cached endpoints **must** include `request: Request` in their function signature
- Redis errors (ConnectionError, TimeoutError) are caught and logged at WARNING level; the handler executes normally without cache

### Phase 6: Tests

- Add `tests/test_api/test_cache.py` with:
  - Test cache key generation (deterministic, includes query params)
  - Test cache hit/miss flow with mocked Redis
  - Test fallback when Redis raises connection errors
  - Test NullCache is used when `REDIS_ENABLED=false`
  - Test TTL is applied correctly
- Update existing route tests to work with cache dependency (mock or disable)
- Add integration test with a real Redis instance (optional, CI-only)

### Phase 7: Documentation

- Update `AGENTS.md` with new environment variables and Redis configuration
- Update `README.md` with Redis setup instructions
- Update `.env.example` with all new `REDIS_*` environment variables and comments
- Update `docs/upgrading.md`: add a new `###` subsection under the existing `## v0.12.0` section documenting the new optional dependency (`redis[hiredis]`), all new `REDIS_*` environment variables, Docker Compose `cache` profile, and that Redis is entirely optional (no migration required)
- Update `docker-compose.yml` comments

## Decisions

1. **Per-role caching for channel-visibility endpoints**: **Resolved — include resolved role in cache key.** Messages, channels, and role-sensitive dashboard endpoints incorporate the user's role into the cache key using `resolve_user_role()` return values: `"admin"`, `"operator"`, `"member"`, or `"anonymous"` (for unauthenticated/`None`). Note that `"anonymous"` is the cache-key role — channel visibility levels use `"community"` (formerly `"public"`), but the cache key uses the resolved role, not the visibility level name. This prevents leaking restricted channel data to unauthenticated users while still caching for all role levels. The number of roles is small (4 max), so the cache multiplier is minimal.

2. **Cache invalidation on write**: **Resolved — skip for now.** Rely on the 30s TTL for stale data self-correction. The web dashboard auto-refreshes every 30s anyway, so the UX impact is negligible. Active invalidation can be added as a future enhancement if needed.

3. **Pagination cache effectiveness**: **Resolved — cache per query string.** Each unique combination of query parameters gets its own cache entry. No full-result-set slicing. Page 1 gets the highest hit rate, which matches real traffic patterns.

4. **Redis memory limits**: **Resolved — 128MB with `allkeys-lru` eviction.** Provides generous headroom for large networks while keeping the container footprint modest. LRU eviction handles any overflow gracefully.

5. **Async vs sync Redis client**: **Resolved — sync `redis` client.** Matches the current synchronous SQLAlchemy session pattern used throughout the API. Will migrate to `redis.asyncio` when/if the broader DB layer goes async.

6. **Decorator vs inline pattern**: **Resolved — decorator with optional `key_builder` callback.** A `@cached(endpoint_name, ttl=..., key_builder=...)` decorator keeps handlers clean. Role-sensitive endpoints (messages, channels) provide a custom `key_builder` that includes the resolved role. Default key builder uses endpoint name + sorted query params.

7. **Multi-instance key isolation**: **Resolved — configurable key prefix via `REDIS_KEY_PREFIX`.** Production hosts multiple Hub instances (prod, staging) that may share a single Redis. Each instance uses `REDIS_KEY_PREFIX` to namespace its cache keys (e.g., `hub` for prod, `hub-stg` for staging). The prefix is prepended to all keys by the `CacheBackend`, not by individual `key_builder` callbacks. The bundled Docker Compose Redis uses the `cache` profile (not `core`), so `--profile core` starts without Redis.

## References

- `docs/plans/20260505-1735-caching-bundling/plan.md` -- Prior caching/bundling plan (focused on static asset caching, not API response caching)
- `src/meshcore_hub/api/metrics.py` -- Existing in-process TTL cache pattern (module-level dict)
- `src/meshcore_hub/api/routes/dashboard.py` -- Most expensive endpoint (~15 SQL queries per request)
- `src/meshcore_hub/api/routes/nodes.py` -- Complex multi-join node listing
- `src/meshcore_hub/api/routes/messages.py` -- Role-based channel visibility filtering
- `src/meshcore_hub/api/routes/channels.py` -- Role-based channel listing
- `src/meshcore_hub/api/channel_visibility.py` -- `resolve_user_role()`, `get_visible_channel_indices()` helpers
- `src/meshcore_hub/common/config.py` -- Settings pattern to follow
- `src/meshcore_hub/api/cli.py` -- CLI option pattern to follow
- `src/meshcore_hub/api/app.py` -- FastAPI lifespan handler (Redis init/cleanup goes here)
- `src/meshcore_hub/web/app.py:758` -- `/map/data` endpoint (web app, not API -- not cached by this plan)

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-06-09 (two passes — 18 resolutions total)

### Resolutions

- **Dashboard role sensitivity**: `get_stats()` and `get_message_activity()` both filter channel data by role. They now get custom `key_builder` callbacks (like messages/channels) to include the resolved role in cache keys. This prevents leaking restricted channel counts/stats to community users.
- **Map/data endpoint**: The `/map/data` endpoint is in `web/app.py` (not the API) and proxies+aggregates from `GET /api/v1/nodes`. Since the underlying nodes endpoint is cached, and the in-memory aggregation is lightweight, `/map/data` will not be directly cached. Added to Non-Goals.
- **TTL env vars**: Reduced from 7 to 2: `REDIS_CACHE_TTL` (default for all endpoints) and `REDIS_CACHE_TTL_DASHBOARD` (override for expensive `/dashboard/*` queries). All non-dashboard endpoints fall back to `REDIS_CACHE_TTL`. `REDIS_CACHE_TTL_MAP` was removed — it will be added alongside the future map-cache feature, not as dead config now.
- **Dashboard sub-endpoints**: `/dashboard/activity`, `/dashboard/message-activity`, and `/dashboard/node-count` share `REDIS_CACHE_TTL_DASHBOARD` with `/dashboard/stats`.
- **`REDIS_ENABLED` default mismatch**: Code defaults `false` (safe for bare-metal), Docker Compose overrides to `true` (Redis always present in Docker). Documented in Phase 4.
- **Decorator technical details**: Clarified that `@cached` uses `functools.wraps` for type signature preservation, reads TTL from `app.state` at runtime via `getattr(request.app.state, ttl_setting, 30)`, locates the `Request` parameter by type inspection, and catches Redis errors gracefully.
- **Health check**: `/health/ready` will use Redis `PING`, return `"redis": "unreachable"` on failure (non-fatal since Redis is optional).
- **Multi-instance isolation**: Added `REDIS_KEY_PREFIX` config (default `hub`) to namespace cache keys. Production instances sharing one Redis set different prefixes (e.g., `hub` vs `hub-stg`). Bundled Docker Compose Redis uses `cache` profile (not `core`), keeping it optional.
- **`Request` parameter requirement**: Four endpoints currently lack `request: Request` in their signatures: `list_nodes()`, `list_advertisements()`, `get_activity()`, and `get_node_count_history()`. These must gain the parameter for the decorator to access TTL settings and build cache keys. Noted in Phase 3.
- **`sorted_query_string()` helper**: Specified — lives in `api/cache.py`, extracts query params from `Request`, sorts by key, URL-encodes, returns a deterministic string. Added to Phase 2.
- **`ttl_setting` → `app.state` mapping**: Clarified that `ttl_setting` is an attribute name on `app.state`, read via `getattr(request.app.state, ttl_setting, 30)`. Defaults to `"redis_cache_ttl"` when omitted. Added to decorator technical notes.
- **Docker volume naming**: `redis_data` volume follows `${COMPOSE_PROJECT_NAME:-hub}_redis_data` naming convention (consistent with existing `data`, `mqtt_data`, `observer_data` volumes).
- **Dev port exposure**: `docker-compose.dev.yml` exposes Redis on `${REDIS_PORT:-6379}:6379` for local development.
- **Role `None` mapping**: `resolve_user_role()` returns `None` for unauthenticated users, not `"public"`. All `key_builder` callbacks map `None` → `"anonymous"` (e.g., `role=anonymous`). Updated FR #2, Phase 2 key builder, and Phase 3 examples.
- **`create_app()` and CLI expansion**: Added explicit notes to Phase 1 that `create_app()` needs new parameters matching existing pattern (stored on `app.state`), and `cli.py` needs corresponding Click options passed through (matching `--metrics-cache-ttl` pattern).
- **Decision #1 role naming**: Corrected `"public"` to `"anonymous"` for the cache-key role mapping. Channel visibility levels use `"community"` (renamed from `"public"` in commit `f8c2a7b`), but cache keys use `resolve_user_role()` return values (`"anonymous"` for `None`, not `"community"` or `"public"`).
- **Phase 7 missing `docs/upgrading.md`**: Added to documentation checklist — new `###` subsection under `## v0.12.0` for the new optional dependency, environment variables, Docker Compose `cache` profile, and that Redis is optional.
- **Reload mode limitation**: Documented in Phase 1 that `--reload` mode uses factory pattern (uvicorn calls `create_app()` with no args), so Redis settings default to code defaults (`REDIS_ENABLED=false`). Same pre-existing limitation as metrics. Noted in Phase 1.

### Remaining Action Items

- None
