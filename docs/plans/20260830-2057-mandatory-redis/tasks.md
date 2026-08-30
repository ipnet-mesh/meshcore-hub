# Tasks: Make Redis Mandatory (PostgreSQL-parity)

> Generated from `plan.md` on 2026-08-30

## Group 1: Core Code Path Removal (Phase 1)

- [x] 1.1 `src/meshcore_hub/common/redis.py`: delete `NullCache` and make errors propagate
  - [x] Delete the `NullCache` class (starts at redis.py:25)
  - [x] Unwrap try/except in `get`/`set`/`delete` so `redis.RedisError` propagates
  - [x] Keep `ping() -> bool` swallowing semantics (health probe interface) and the SCAN-based delete diagnostics
- [x] 1.2 `src/meshcore_hub/api/cache.py`: single code path, 503 on Redis errors
  - [x] Remove `if cache is None: return func(...)` from both the async and sync `@cached` wrappers
  - [x] Remove warn-and-degrade exception handling from `_lookup`/`_store`
  - [x] Catch `redis.exceptions.RedisError` at the wrapper boundary and raise `HTTPException(503, detail="cache backend unavailable")` (FR3)
- [x] 1.3 `src/meshcore_hub/api/cache_invalidation.py`: never-raise invalidation
  - [x] Make `_cache()` return the non-Optional backend
  - [x] Remove the "skipped (no backend)" branch/log
  - [x] Log `_drop` backend errors at ERROR (not WARNING); never raise (FR4)
  - [x] Update module/function docstrings describing disabled-mode / `NullCache` / `REDIS_ENABLED` behaviour (cache_invalidation.py:55-56)
- [x] 1.4 `src/meshcore_hub/api/app.py`: unconditional backend + readiness change
  - [x] Lifespan (app.py:46-63): always construct `RedisCacheBackend(host, port, db, password, key_prefix)` from `app.state`; delete the `redis_enabled` branch and `NullCache` fallback
  - [x] Ping at startup and log connected/error
  - [x] Remove `redis_enabled` from `create_app()` signature (app.py:95), docstring (app.py:128), `app.state` assignment (app.py:172), and `create_app_from_env()` (app.py:375)
  - [x] `health_ready` (app.py:298-322): always ping; unreachable ⇒ `"redis": "unreachable"` + overall `"status": "not_ready"` ⇒ 503; drop the `redis_enabled` guard (app.py:314-315)
  - [x] Update the `health_ready` docstring: "database and optional Redis" → mandatory Redis (app.py:300)
- [x] 1.5 `src/meshcore_hub/api/cli.py`: remove the enable flag
  - [x] Remove `--redis-enabled/--no-redis` option + `REDIS_ENABLED` envvar (cli.py:137) + the `redis_enabled` parameter (cli.py:240) and its `create_app` passthrough (cli.py:369)
  - [x] Remove the "Redis enabled:" banner line (cli.py:302-303)
  - [x] Keep the "Redis: host:port/db", "Redis key prefix:", and TTL echoes (cli.py:304-309) — always printed now
- [x] 1.6 `src/meshcore_hub/common/config.py`: remove `redis_enabled` from `APISettings` (config.py:458)

## Group 2: Compose & Infrastructure (Phase 2)

- [x] 2.1 `docker-compose.yml` (base)
  - [x] Update the redis service header comment: required dependency, not optional
  - [x] api service: remove `REDIS_ENABLED` env (line 325) and rewrite the "# Redis cache (optional — API works without Redis)" comment above it
  - [x] api service: add `depends_on: redis: {condition: service_healthy, required: false}` alongside the existing migrate/collector dependencies
  - [x] Keep the `all`/`cache` profiles on the redis service unchanged
- [x] 2.2 `docker-compose.dev.yml`: add `redis: profiles: [core]` union block, identical shape to the existing `postgres:` block (lines 44-46); keep the port mapping
- [x] 2.3 `docker-compose.prod.yml`: extend the header NOTE — bundled Redis not in `core`; point `REDIS_*` at the shared/external instance; `--profile cache` opts into the bundled one
- [x] 2.4 `e2e/docker-compose.test.yml`: add Redis to the e2e stack
  - [x] Add a `redis:8-alpine` service with healthcheck
  - [x] api service: add `REDIS_HOST=redis` (mandatory — the e2e api sets no other `REDIS_*` env and the code default `localhost` would fail) + `depends_on` redis
  - [x] Leave the api healthcheck probing basic `/health` (line 182) — the new 503 readiness must not deadlock stack startup
- [x] 2.5 `.env.example`: delete `REDIS_ENABLED`; rewrite the Redis block comments (required dependency; bundled in dev; external for prod; `REDIS_KEY_PREFIX` multi-instance isolation stays)
- [x] 2.6 `README.md`
  - [x] Profile table `core` row: "postgres, redis (dev override only), migrate, collector, api, web" (line 111)
  - [x] Profile table `cache` row: drop "(optional)" — "Bundled Redis, standalone opt-in" mirroring the `postgres` row (line 113)
  - [x] Extend the "Database note" paragraph (~line 121) to cover Redis with the same profile-union / no-shadowing rationale

## Group 3: Test Infrastructure — Real Redis (Phase 3)

- [x] 3.1 `docker-compose.test-db.yml`: add `test-redis` service (redis:8-alpine, published on `127.0.0.1:55433`, tmpfs, healthcheck); update the file header comment
- [x] 3.2 `Makefile`: comment-only updates — mention Redis alongside Postgres in the throwaway-DB comments; NO target changes (`test-db-up` runs `up -d --wait` on the whole file, Makefile:80-81, so `test-redis` starts automatically)
- [x] 3.3 `tests/conftest.py`: session `redis_url` fixture
  - [x] Resolve `TEST_REDIS_URL` (default `redis://localhost:55433/0`)
  - [x] Ping fail-fast mirroring `db_url` (tests/conftest.py:122-144): `pytest.exit(..., returncode=4)` with a `make test-db-up` hint
- [x] 3.4 `tests/test_api/conftest.py`: wire the real backend into the module app fixtures
  - [x] In `_wire_overrides` (line 128): construct a real `RedisCacheBackend` with a per-xdist-worker `key_prefix` mirroring `db_schema` naming (e.g. `hub_test_gw0`)
  - [x] Applies to `app_no_auth` (151), `app_with_auth` (172), `app_spam` (184)
  - [x] Add a function-scoped autouse flush-by-prefix fixture (DB is truncated between tests; cache must be too, or modules see stale HITs)
  - [x] The flush fixture must save/restore `app.state.redis_cache` around each test — tests that swap in `MagicMock`/`_FakeCache` (test_routes.py:441, test_dashboard.py:1347) must not permanently displace the real backend
- [x] 3.5 `.github/workflows/ci.yml`: add a `redis:8` service container (pin comment mirroring `postgres:17` at ci.yml:87-88) + `TEST_REDIS_URL` env on the backend-test job

## Group 4: Test Updates (Phase 4)

- [x] 4.1 `tests/test_api/test_cache.py`: delete `NullCache` coverage
  - [x] Delete `TestNullCache` (lines 102-117) and the `NullCache` import (line 11)
  - [x] Remove `NullCache` wiring at lines 318, 792-808, 1969-1985, 2069-2073 — the "cache_control_ttl emitted even with NullCache" tests become plain backend-present tests
- [x] 4.2 Rewrite `TestLifespanRedis` (lines 1005-1074): always-constructs-from-`app.state` + close-on-shutdown; drop the disabled/`NullCache` cases and `redis_enabled` assignments (lines 1012-1057)
- [x] 4.3 Rewrite `TestHealthReadyRedis` (lines 1101-1148)
  - [x] Delete `test_health_ready_omits_redis_when_disabled` (redis is always reported now)
  - [x] Connected/unreachable tests: drop `redis_enabled` assignments; mock-swap `app.state.redis_cache` instead of deleting it
  - [x] `test_health_ready_reports_unreachable`: flip 200 → 503 + `"status": "not_ready"` (current 200 assertion is exactly the behaviour FR2 removes)
- [x] 4.4 Rewrite `TestCliRedis` (lines 1149-1279)
  - [x] `test_redis_enabled_shows_banner`: drop `--redis-enabled` flag; banner always shows
  - [x] Delete `test_redis_disabled_hides_details`
  - [x] `test_redis_params_passed_to_create_app`: drop `redis_enabled` from expected `create_app()` kwargs (asserted ~line 1224); keep host/port/db/password/prefix/TTL assertions
- [x] 4.5 Add hard-fail tests (FR3): backend raising `RedisError` on GET/SET ⇒ endpoint responds 503
- [x] 4.6 Keep the mocked-`redis.Redis` unit tests in `TestRedisCacheBackend` (line 120) unchanged
- [x] 4.7 `tests/test_api/test_app_factory.py`
  - [x] Remove `"REDIS_ENABLED"` from the `_FACTORY_ENV` cleanup list (line 19)
  - [x] Adjust `test_factory_reads_database_and_redis_from_env` (line 64): drop `REDIS_ENABLED` setenv + assertion (line 73)
  - [x] Drop the false-case assertions (lines 84-90)
  - [x] Delete `test_factory_redis_enabled_accepts_truthy_values` (lines 103-107)

## Group 5: Documentation (Phase 5)

- [x] 5.1 `docs/upgrading.md`: add a `## v0.20.0` section — Redis now required; `REDIS_ENABLED` removed (leftover values ignored); production external-Redis guidance; dev `core` stack now ships Redis
  - [x] Do NOT edit the historical v0.19/v0.12 `REDIS_ENABLED` mentions (lines ~416, 438, 455) — release-history records
- [x] 5.2 `docs/configuration.md`: rewrite the caching section; drop the `REDIS_ENABLED` row (line 57)
- [x] 5.3 `docs/deployment.md`: rewrite all `REDIS_ENABLED` mentions — multi-worker guidance (~line 96), Docker (~106), bare-metal (~113); required-dependency framing; bundled-vs-external guidance; keep the multi-instance `REDIS_KEY_PREFIX` note
- [x] 5.4 `AGENTS.md`: update the cache-invalidation convention ("no-op when Redis is disabled" → mandatory backend, never-raise-after-commit rationale); `core` stack description gains redis; test-db instructions cover Postgres + Redis

## Group 6: Verification (Phase 6)

- [x] 6.1 `make test-db-up` — throwaway stack now starts `test-postgres` + `test-redis`; `--wait` proves the Redis healthcheck
- [x] 6.2 `pytest --no-cov tests/test_api/ 2>&1 | grep -iE "passed|failed" | tail -3` — targeted suite first (real Redis wired)
- [x] 6.3 `pytest -nauto --no-cov 2>&1 | grep -iE "passed|failed" | tail -3` — full backend suite
- [x] 6.4 Leftover sweep: `rg -n "REDIS_ENABLED|redis_enabled|NullCache" --glob '!.venv' --glob '!docs/plans/**'` must only match the historical upgrading.md sections (v0.19/v0.12) — everything else is a miss
- [x] 6.5 `pre-commit run --all-files` (includes ruff, frontend-typecheck hooks)
- [x] 6.6 `npx playwright test --config=e2e/playwright.config.ts --list` — collection check only (user builds/runs the e2e stack)
- [x] 6.7 No image builds, no `make up` — the user builds and runs the stack manually
