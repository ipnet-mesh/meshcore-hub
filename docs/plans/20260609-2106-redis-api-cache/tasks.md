# Tasks: Redis Caching Layer for API Endpoints

> Generated from `plan.md` on 2026-06-09

## 1. Dependencies & Configuration

- [x] 1.1 Add `redis[hiredis]` to `pyproject.toml`
  - [x] Add `"redis[hiredis]"` to the `dependencies` list in `[project]`
  - [x] Add `"redis.*"` to the first `[[tool.mypy.overrides]]` module ignore list (line 116, alongside `paho.*`, `uvicorn.*`, etc.)

- [x] 1.2 Add Redis settings to `common/config.py`
  - [x] In `APISettings` class (which extends `CommonSettings`), add fields:
    - `REDIS_ENABLED: bool = False` (code default `False`, safe fallback)
    - `REDIS_HOST: str = "localhost"`
    - `REDIS_PORT: int = 6379`
    - `REDIS_DB: int = 0`
    - `REDIS_PASSWORD: Optional[str] = None`
    - `REDIS_KEY_PREFIX: str = "hub"` (multi-instance key namespace isolation)
    - `REDIS_CACHE_TTL: int = 30` (default TTL, matches `WEB_AUTO_REFRESH_SECONDS`)
    - `REDIS_CACHE_TTL_DASHBOARD: int = 30` (override for all `/dashboard/*` endpoints)
  - [x] Follow existing field patterns: `Field(default=..., env=...)` with Pydantic `SettingsConfigDict`

- [x] 1.3 Add Redis Click options to `api/cli.py`
  - [x] Add `@click.option` blocks before the `api()` function for each Redis setting, matching the `--metrics-cache-ttl` pattern:
    - `--redis-enabled/--no-redis` (boolean flag, `envvar="REDIS_ENABLED"`, default `False`)
    - `--redis-host` (`str`, `envvar="REDIS_HOST"`, default `"localhost"`)
    - `--redis-port` (`int`, `envvar="REDIS_PORT"`, default `6379`)
    - `--redis-db` (`int`, `envvar="REDIS_DB"`, default `0`)
    - `--redis-password` (`str`, `envvar="REDIS_PASSWORD"`, default `None`)
    - `--redis-key-prefix` (`str`, `envvar="REDIS_KEY_PREFIX"`, default `"hub"`)
    - `--redis-cache-ttl` (`int`, `envvar="REDIS_CACHE_TTL"`, default `30`)
    - `--redis-cache-ttl-dashboard` (`int`, `envvar="REDIS_CACHE_TTL_DASHBOARD"`, default `30`)
  - [x] Add corresponding parameters to the `api()` function signature
  - [x] Add `click.echo` lines in the startup banner section (after metrics lines, before reload) showing Redis enabled/disabled and TTL values
  - [x] Pass all Redis parameters through to `create_app()` in the non-reload branch (line 225)
  - [x] In the reload branch (line 210), add a `click.echo` note that Redis defaults to disabled in reload mode

- [x] 1.4 Add Redis parameters to `create_app()` in `api/app.py`
  - [x] Add 8 new parameters to `create_app()` signature (after `metrics_cache_ttl`): `redis_enabled: bool = False`, `redis_host: str = "localhost"`, `redis_port: int = 6379`, `redis_db: int = 0`, `redis_password: str | None = None`, `redis_key_prefix: str = "hub"`, `redis_cache_ttl: int = 30`, `redis_cache_ttl_dashboard: int = 30`
  - [x] Store all on `app.state` (after `metrics_cache_ttl` on line 107): `app.state.redis_enabled`, `app.state.redis_host`, etc.
  - [x] Update docstring with new parameters

## 2. Redis Client & App Integration

- [x] 2.1 Create `common/redis.py`
  - [x] Implement `CacheBackend` abstract base class / Protocol with methods:
    - `get(key: str) -> str | None` — retrieve cached JSON string
    - `set(key: str, value: str, ttl: int) -> None` — store with TTL
    - `delete(prefix: str) -> None` — delete keys matching prefix
    - `ping() -> bool` — health check
  - [x] Implement `RedisCacheBackend(CacheBackend)`:
    - Uses sync `redis.Redis` client with connection pool
    - Constructor accepts `host`, `port`, `db`, `password`, `key_prefix`
    - `key_prefix` is prepended to all keys internally (e.g., `{prefix}:{suffix}`)
    - All Redis operations use timeouts and exception handling — catch `redis.ConnectionError`, `redis.TimeoutError`, log at WARNING level
    - `get()` returns `None` on cache miss or error (never raises)
    - `set()` silently logs Redis errors (never raises)
    - `ping()` calls Redis `PING` command, returns `True`/`False`
  - [x] Implement `NullCache(CacheBackend)`:
    - `get()` always returns `None`
    - `set()` is a no-op
    - `ping()` returns `False`
    - Used when `REDIS_ENABLED=false` or Redis is unreachable

- [x] 2.2 Wire Redis into FastAPI lifespan in `api/app.py`
  - [x] In `lifespan()` startup (before `yield`):
    - Read `redis_enabled`, `redis_host`, `redis_port`, `redis_db`, `redis_password`, `redis_key_prefix` from `app.state`
    - If `redis_enabled` is True: create a `RedisCacheBackend` instance, store as `app.state.redis_cache`
    - If `redis_enabled` is False: create a `NullCache` instance, store as `app.state.redis_cache`
    - Log Redis status at INFO level
  - [x] In `lifespan()` shutdown (after `yield`):
    - Close Redis connection (if any) — call `.close()` on the cache backend

## 3. Cache Decorator

- [x] 3.1 Create `api/cache.py`
  - [x] Implement `sorted_query_string(request: Request) -> str`:
    - Extract query params from `request.query_params`
    - Sort by key alphabetically
    - URL-encode each key-value pair
    - Join with `&`, return the string (e.g., `"limit=50&offset=0&sort=last_seen"`)
    - Return `""` for empty query params

  - [x] Implement `cached()` decorator factory:
    - Signature: `cached(endpoint_name: str, ttl_setting: str = "redis_cache_ttl", key_builder: Callable[[Request], str] | None = None)`
    - Default `key_builder`: `f"{endpoint_name}:{sorted_query_string(request)}"` (suffix only — the `CacheBackend` prepends the key prefix)
    - Custom `key_builder` receives `Request`, returns a suffix string

  - [x] Decorator implementation (inner `decorator` function):
    - Uses `functools.wraps` to preserve the wrapped function's `__name__`, `__module__`, `__annotations__`
    - Locates the `Request` parameter from `kwargs` by type inspection
    - Reads the cache TTL from `app.state`: `ttl = getattr(request.app.state, ttl_setting, 30)`
    - Builds cache key using `key_builder(request)` (suffix) — the full key is built by the cache backend
    - Tries `cache.get(cache_key)` — on cache hit: deserializes JSON, sets `request.state.cache_status = "HIT"`, returns cached result
    - On cache miss: calls handler, serializes result, stores in cache, sets `request.state.cache_status = "MISS"`
    - Catches Redis errors: logs WARNING, falls through to handler
    - Caches serialization errors: logs WARNING, returns handler result

- [x] 3.2 Add `X-Cache` middleware to `api/app.py`
  - [x] Add a FastAPI middleware using `@app.middleware("http")` after the CORS middleware
  - [x] The middleware reads `getattr(request.state, "cache_status", None)` after the response is generated
  - [x] If set, adds `X-Cache: HIT` or `X-Cache: MISS` header to the response
  - [x] If not set (non-cached endpoints), no `X-Cache` header is added

## 4. Apply Caching to API Routes

- [x] 4.1 Update `routes/nodes.py` — `list_nodes()` (line 50)
  - [x] Add `request: Request` parameter (after `session: DbSession`, before query params)
  - [x] Import `Request` from `fastapi`
  - [x] Apply `@cached("nodes")` decorator (default key builder: endpoint name + sorted query params)

- [x] 4.2 Update `routes/advertisements.py` — `list_advertisements()` (line 47)
  - [x] Add `request: Request` parameter (after `session: DbSession`, before query params)
  - [x] Import `Request` from `fastapi`
  - [x] Apply `@cached("advertisements")` decorator

- [x] 4.3 Update `routes/messages.py` — `list_messages()` (line 37)
  - [x] Already has `request: Request` — no parameter change needed
  - [x] Create a `_messages_key_builder(request: Request) -> str` function
  - [x] Import `resolve_user_role` from `meshcore_hub.api.channel_visibility`
  - [x] Import `sorted_query_string` from `meshcore_hub.api.cache`
  - [x] Apply `@cached("messages", key_builder=_messages_key_builder)` decorator

- [x] 4.4 Update `routes/channels.py` — `list_channels()` (line 41)
  - [x] Already has `request: Request` — no parameter change needed
  - [x] Create a `_channels_key_builder(request: Request) -> str` function
  - [x] Apply `@cached("channels", key_builder=_channels_key_builder)` decorator

- [x] 4.5 Update `routes/dashboard.py` — `get_stats()` (line 52)
  - [x] Already has `request: Request` — no parameter change needed
  - [x] Create a `_dashboard_stats_key_builder(request: Request) -> str` function
  - [x] Apply `@cached("dashboard/stats", ttl_setting="redis_cache_ttl_dashboard", key_builder=_dashboard_stats_key_builder)` decorator

- [x] 4.6 Update `routes/dashboard.py` — `get_activity()` (line 309)
  - [x] Add `request: Request` parameter (after `session: DbSession`, before `days` param)
  - [x] Apply `@cached("dashboard/activity", ttl_setting="redis_cache_ttl_dashboard")` decorator

- [x] 4.7 Update `routes/dashboard.py` — `get_message_activity()` (line 363)
  - [x] Already has `request: Request` — no parameter change needed
  - [x] Create a `_dashboard_msg_activity_key_builder(request: Request) -> str` function
  - [x] Apply `@cached("dashboard/message-activity", ttl_setting="redis_cache_ttl_dashboard", key_builder=_dashboard_msg_activity_key_builder)` decorator

- [x] 4.8 Update `routes/dashboard.py` — `get_node_count_history()` (line 422)
  - [x] Add `request: Request` parameter (after `session: DbSession`, before `days` param)
  - [x] Apply `@cached("dashboard/node-count", ttl_setting="redis_cache_ttl_dashboard")` decorator

- [x] 4.9 Add required imports to each route file
  - [x] `from fastapi import Request` (where not already present)
  - [x] `from meshcore_hub.api.cache import cached, sorted_query_string` (all files)
  - [x] `from meshcore_hub.api.channel_visibility import resolve_user_role` (messages.py, channels.py, dashboard.py — where key_builder uses it)

## 5. Docker Compose & Environment Variables

- [x] 5.1 Add Redis service to `docker-compose.yml`
  - [x] Insert the Redis service definition (after the `observer` service block, before `collector`):
    - Image: `redis:7-alpine`
    - Container name: `${COMPOSE_PROJECT_NAME:-hub}-redis`
    - Profiles: `all`, `cache`
    - Restart: `unless-stopped`
    - Command: `redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru`
    - Volume: `redis_data:/data`
    - Healthcheck: `test: ["CMD", "redis-cli", "ping"]`, interval 10s, timeout 5s, retries 3
    - Follow existing service block formatting (comments, spacing)
    - Add descriptive comment block above service definition

- [x] 5.2 Add `redis_data` volume to `docker-compose.yml`
  - [x] Add to the `volumes:` section at the bottom:
    - `redis_data:` with `name: ${COMPOSE_PROJECT_NAME:-hub}_redis_data` (matching existing naming convention)

- [x] 5.3 Add Redis environment variables to `api` service in `docker-compose.yml`
  - [x] In the `api` service `environment:` block (after `METRICS_CACHE_TTL` line):
    - `REDIS_ENABLED=${REDIS_ENABLED:-true}` (Docker overrides code default)
    - `REDIS_HOST=redis` (container name within Docker network)
    - `REDIS_PORT=6379`
    - `REDIS_PASSWORD=${REDIS_PASSWORD:-}`
    - `REDIS_KEY_PREFIX=${REDIS_KEY_PREFIX:-hub}`
    - `REDIS_CACHE_TTL=${REDIS_CACHE_TTL:-30}`
    - `REDIS_CACHE_TTL_DASHBOARD=${REDIS_CACHE_TTL_DASHBOARD:-30}`
  - [x] Do NOT add `depends_on: redis` to the `api` service — Redis is optional, API starts fine without it

- [x] 5.4 Add Redis port exposure to `docker-compose.dev.yml`
  - [x] Add a `redis:` service override:
    - `ports:` with `"${REDIS_PORT:-6379}:6379"` (matching the `mqtt`/`api`/`web` port exposure pattern)

- [x] 5.5 Add Redis env vars to `.env.example`
  - [x] Add a new section `# REDIS CACHE SETTINGS` after the API settings section (before Web Dashboard)
  - [x] Document all new env vars with comments and defaults
  - [x] Note that Redis is the `cache` profile (not `core`) in Docker Compose
  - [x] Note multi-instance guidance: set different `REDIS_KEY_PREFIX` per instance

## 6. Health Check & Observability

- [x] 6.1 Update `/health/ready` endpoint in `api/app.py` (line 138)
  - [x] After the database check, add a Redis check:
    - Only if `app.state.redis_enabled` is True
    - Call `app.state.redis_cache.ping()`
    - On success: include `"redis": "connected"` in the response
    - On failure: include `"redis": "unreachable"` — do NOT mark the overall status as `"not_ready"` (Redis is optional)
  - [x] Update response dict construction accordingly

- [x] 6.2 Add cache hit/miss logging
  - [x] In the `cached()` decorator (in `api/cache.py`), log cache hits at DEBUG level: `logger.debug("Cache HIT: %s", cache_key)`
  - [x] Log cache misses at DEBUG level: `logger.debug("Cache MISS: %s", cache_key)`
  - [x] Log Redis errors at WARNING level: `logger.warning("Redis GET error for %s: %s", cache_key, e)`
  - [x] Use `logging.getLogger(__name__)`

## 7. Tests

- [x] 7.1 Create `tests/test_api/test_cache.py`
  - [x] Test `sorted_query_string()`:
    - Empty query string returns `""`
    - Single param: `?limit=50` → `"limit=50"`
    - Multiple params unsorted: `?offset=0&limit=50` → `"limit=50&offset=0"` (sorted)
    - URL-encoded special chars: `?search=foo+bar` → properly encoded

  - [x] Test `NullCache`:
    - `get()` always returns `None`
    - `set()` does not raise
    - `ping()` returns `False`

  - [x] Test `RedisCacheBackend` with mocked `redis.Redis`:
    - `get()` returns cached value on hit
    - `get()` returns `None` on miss
    - `set()` stores with correct TTL
    - `ping()` returns `True` on success
    - On `ConnectionError`, `get()` returns `None` (no raise)
    - On `TimeoutError`, `set()` logs warning (no raise)
    - Keys include prefix: `hub:nodes:limit=50`

  - [x] Test `@cached` decorator:
    - Cache hit: handler not called, `cache_status = "HIT"`, cached result returned
    - Cache miss: handler called, result cached, `cache_status = "MISS"`
    - No `Request` in handler args → raises `TypeError`
    - Redis disabled (`NullCache`): handler always called, result not cached
    - Redis error: handler called, result returned, no error raised

  - [x] Test `key_builder` callbacks:
    - Default builder produces correct suffix from endpoint name + sorted query params
    - Custom builder with role header includes `role=admin`
    - Dashboard key builders use TTL override

- [x] 7.2 Verify existing route tests pass without Redis
  - [x] `pytest tests/test_api/ -v` — all 336 API tests pass (including new `test_cache.py`)
  - [x] `pytest tests/test_web/ tests/test_common/ tests/test_collector/` — all 567 tests pass
  - [x] No test failures due to new `request: Request` parameter

## 8. Documentation

- [x] 8.1 Update `AGENTS.md`
  - [x] Add `REDIS_*` environment variables to the Environment Variables table
  - [x] Add `redis[hiredis]` to the Technology Stack table
  - [x] Add `src/meshcore_hub/common/redis.py` and `src/meshcore_hub/api/cache.py` to the Project Structure tree

- [x] 8.2 Update `README.md`
  - [x] Add a Redis setup section describing:
    - Redis is optional (API works without it)
    - Docker: `docker compose --profile cache up` to start bundled Redis
    - Bare-metal: install Redis separately, set `REDIS_ENABLED=true` and `REDIS_HOST=localhost`
    - Multi-instance: use `REDIS_KEY_PREFIX` to isolate namespaces
  - [x] Environment variable reference table

- [x] 8.3 Update `docs/upgrading.md`
  - [x] Under the existing `## v0.12.0` section, add a new `###` subsection: "Optional Redis API Cache"
  - [x] Document all new `REDIS_*` environment variables with defaults and descriptions
  - [x] Docker Compose `cache` profile for bundled Redis
  - [x] Redis is entirely optional — no migration or configuration required to upgrade
  - [x] Cache TTL defaults to 30s (matches web dashboard auto-refresh)

- [x] 8.4 Update `docker-compose.yml` comments
  - [x] Add comment noting Redis env vars in the `api` service environment block
  - [x] Redis service comment block clear about the `cache` profile and optionality

## 9. Verification

- [x] 9.1 Lint and type-check
  - [x] Run `pip install -e ".[dev]"` to ensure `redis[hiredis]` is installed
  - [x] Run `pre-commit run --all-files` — all checks pass (black, flake8, mypy)
  - [x] mypy passes (new `redis.*` module in mypy ignore list)

- [x] 9.2 Run targeted tests
  - [x] `pytest tests/test_api/` — 336 passed
  - [x] `pytest tests/test_common/ tests/test_web/ tests/test_collector/` — 567 passed
  - [x] Full suite: 903 passed, 22 skipped

- [ ] 9.3 Manual verification (Docker)
  - [ ] Start with Redis: `docker compose --profile cache up api -d` — verify API starts, `/health/ready` reports `"redis": "connected"`
  - [ ] Start without Redis: `docker compose up api -d` (core profile only) — verify API starts, `/health/ready` reports `"redis": "unreachable"` or Redis section absent
  - [ ] Hit `/api/v1/nodes` twice — first response should have `X-Cache: MISS`, second should have `X-Cache: HIT`
  - [ ] Hit `/api/v1/messages` with different request headers (anonymous vs authenticated) — verify separate cache keys
  - [ ] Stop Redis container mid-operation — verify API continues serving from database (graceful fallback)

- [ ] 9.4 Manual verification (bare-metal)
  - [ ] Run `meshcore-hub api` (no Redis env vars) — verify API starts, `/health/ready` shows database connected, no Redis dependency
  - [ ] Run with `REDIS_ENABLED=true` pointing at a running Redis — verify caching works, `X-Cache` headers present
  - [ ] Run with `--reload` flag — verify Redis defaults to disabled (safe fallback)
