# Make Redis Mandatory (PostgreSQL-parity)

## Summary

Redis becomes a required infrastructure dependency for MeshCore Hub, mirroring the
pattern used to make PostgreSQL the only database backend in v0.19. Every
conditional caching code path is removed: the `REDIS_ENABLED` flag (settings, CLI,
`create_app` parameter, compose env), the `NullCache` no-op backend, the
`cache is None` short-circuits in the `@cached` decorator, and the `redis_enabled`
branches in the application lifespan and `/health/ready` endpoint.

Operational semantics change to "mandatory": a Redis outage is a hard failure.
`/health/ready` returns 503 `not_ready` when Redis is unreachable (same as the
database check), and cached endpoints translate Redis errors into
`HTTPException(503)` instead of silently degrading to direct database queries.
Production environments that run Redis separately are supported through the same
compose-profile-union trick used for Postgres — the bundled `redis` service joins
the `core` profile only via `docker-compose.dev.yml`, while `docker-compose.prod.yml`
leaves it out so `REDIS_HOST`/`REDIS_PASSWORD` can point at a shared/external
instance without host shadowing.

User-confirmed design decisions (from planning discussion):

1. **Readiness**: Redis unreachable → `/health/ready` returns 503 `not_ready`.
2. **Outage behavior**: hard-fail — cache GET/SET errors propagate out of `@cached`
   as 503 responses ("every cached endpoint fails during a Redis outage"), not
   soft-degrade.
3. **Test strategy**: real Redis in the test infra (full Postgres parity) — a
   throwaway `test-redis` container next to `test-postgres`, a CI service
   container, and per-xdist-worker key prefixes with between-test flushes.
4. **Invalidation semantics**: `invalidate_*` helpers never raise (ERROR log)
   after a committed write; only read/store paths hard-fail (confirmed at plan
   review).

## Background & Motivation

Redis was introduced as an entirely optional response cache
(`docs/plans/20260609-2106-redis-api-cache/plan.md`): `REDIS_ENABLED` defaults to
false, a `NullCache` stands in when disabled, the bundled compose service lives
behind the opt-in `cache` profile, and `RedisCacheBackend` swallows every
operational error (warn-and-degrade). This leaves three parallel code paths
(enabled-real, disabled-null, enabled-but-unreachable-degraded) that every feature
touching the cache must reason about, and it makes "cache invalidation on writes"
(see AGENTS.md → Cache invalidation) best-effort in all deployments.

Since then the project made PostgreSQL the only database backend
(commit `81dcd3d`, plan `docs/plans/20260829-2312-remove-sqlite-support/`) and
kept the bundled container out of the production `core` profile
(commit `5a8794f fix(compose): keep bundled postgres out of the core profile in
production`). That change established the pattern this plan reuses:

- dev: `docker-compose.dev.yml` unions `core` into the base service profiles
  (profiles merge across compose files) so a default dev `compose up` is
  zero-effort;
- prod: `docker-compose.prod.yml` does not, so the bundled container never starts
  to shadow a shared host on the same network — operators point `REDIS_*`
  variables at their external instance;
- wiring: dependent services use
  `depends_on: {condition: service_healthy, required: false}` so the dependency
  is enforced when the bundled service is profile-active and skipped when it is
  not (see `migrate` → `postgres`).

Redis is already an unconditional install dependency
(`redis[hiredis]>=5.0.0` in `pyproject.toml`), so this plan only removes runtime
optionalism.

## Goals

- Remove every conditional caching code path (`REDIS_ENABLED`, `NullCache`,
  `cache is None`, `redis_enabled` branches) — exactly one code path remains.
- Make a Redis outage loud: `/health/ready` → 503 `not_ready`; cached endpoints →
  503 on Redis errors during request handling.
- Support production environments running Redis separately (external/shared
  instances) via the Postgres compose pattern; dev `core` stack starts Redis
  automatically.
- Stand up real Redis for the backend test suite (throwaway container + CI
  service), replacing today's accidental cache bypass (TestClient never runs the
  lifespan, so `app.state.redis_cache` is unset in most tests).
- Update all operator-facing docs (`.env.example`, configuration/deployment/README/
  upgrading/AGENTS.md) to describe Redis as required infrastructure.

## Non-Goals

- No migration to `redis.asyncio` (the sync client stays, matching the sync
  SQLAlchemy session pattern; noted as future work in the original cache plan).
- No changes to cache key layouts, TTL semantics, the `private, no-cache`
  Cache-Control policy, or ETag/If-None-Match handling.
- No Redis usage beyond the API response cache (collector and web tiers keep
  their current architecture; the collector does not cache).
- No changes to the metrics in-memory TTL cache (`api/metrics.py`).
- No `fakeredis` dependency — tests use a real Redis container.
- No changes to `REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`/`REDIS_PASSWORD`/
  `REDIS_KEY_PREFIX`/`REDIS_CACHE_TTL*` variable names or defaults.

## Requirements

### Functional Requirements

- FR1: Removing `REDIS_ENABLED` from environment/CLI/`create_app()` has no
  effect — the app always configures a `RedisCacheBackend` from the remaining
  `REDIS_*` settings.
- FR2: `/health/ready` always pings Redis and reports
  `"redis": "connected"` or `"redis": "unreachable"`; unreachable ⇒ overall
  `"status": "not_ready"` ⇒ HTTP 503 (same contract as the database check).
- FR3: A Redis error during cache lookup or store inside `@cached` produces a
  503 response (`HTTPException`, detail e.g. "cache backend unavailable") — not
  a silent cache miss, not a raw 500.
- FR4: Cache invalidation helpers (`invalidate_*`) never raise: they run after
  `session.commit()` succeeded, so raising would report failure for a durable
  write and invite duplicate client retries. Backend errors there log at ERROR.
  (Confirmed at plan review — reads/stores hard-fail, invalidation never
  raises.)
- FR5: `docker compose --profile core up` with the dev override starts Redis and
  the API waits for it to be healthy before starting.
- FR6: Production (`docker-compose.prod.yml`, `core` profile) does not start the
  bundled Redis; pointing `REDIS_HOST` at an external instance is the documented
  production setup. The `cache` profile remains for explicitly starting the
  bundled Redis standalone.
- FR7: The backend test suite runs against a real Redis; the e2e stack includes
  a Redis service and the e2e API container connects to it.

### Technical Requirements

- TR1: `common/redis.py`: delete `NullCache`; remove try/except from
  `get`/`set`/`delete` so `redis.RedisError` propagates; keep `ping() -> bool`
  (swallowing there is correct — it is a health probe interface).
- TR2: `api/cache.py`: both async and sync wrappers read
  `request.app.state.redis_cache` without a None branch; `_lookup`/`_store` lose
  their warn-and-degrade exception handling; Redis errors are caught at the
  wrapper boundary and re-raised as `HTTPException(503)`.
- TR3: `api/app.py`: drop the `redis_enabled` parameter and `app.state` field;
  lifespan always constructs `RedisCacheBackend(host, port, db, password,
  key_prefix)` from `app.state` and pings at startup (log connected / error);
  `create_app_from_env()` stops passing `redis_enabled`; update the
  `health_ready` docstring ("database and optional Redis" → mandatory Redis).
- TR4: `api/cache_invalidation.py`: `_cache()` returns the non-Optional backend;
  remove the "skipped (no backend)" branch; update module/function docstrings
  that describe disabled-mode behaviour.
- TR5: `api/cli.py`: remove `--redis-enabled/--no-redis` and the corresponding
  parameter; startup info output always prints the Redis target.
- TR6: `common/config.py` (`APISettings`): remove the `redis_enabled` field.
- TR7: Compose: `docker-compose.yml` api service drops `REDIS_ENABLED` (and the
  "optional — API works without Redis" env comment) and gains
  `depends_on: redis: {condition: service_healthy, required: false}` alongside
  its existing migrate/collector dependencies;
  `docker-compose.dev.yml` adds `redis: profiles: [core]` (keeping the port
  mapping); `docker-compose.prod.yml` header comment documents external Redis;
  `e2e/docker-compose.test.yml` adds a `redis:8-alpine` service (healthcheck)
  and `REDIS_HOST=redis` + `depends_on` on the api service. The e2e api
  currently sets no `REDIS_*` env at all, so `REDIS_HOST=redis` is mandatory
  there (code default `localhost` would fail). Its healthcheck stays the basic
  `/health` — the 503 readiness change cannot deadlock stack startup.
- TR8: Test infra: `docker-compose.test-db.yml` gains `test-redis`
  (redis:8-alpine, published on `127.0.0.1:55433`, tmpfs, healthcheck — the
  Makefile's `test-db-up` runs `up -d --wait` on the whole file, so no target
  changes are needed and `--wait` requires the healthcheck);
  `tests/conftest.py` gains a session fixture resolving `TEST_REDIS_URL`
  (default `redis://localhost:55433/0`) with a ping fail-fast hint mirroring
  the Postgres one (`pytest.exit(..., returncode=4)` in `db_url`);
  `tests/test_api/conftest.py` module app fixtures wire a real
  `RedisCacheBackend` with a per-xdist-worker key prefix (mirroring `db_schema`
  naming, e.g. `hub_test_gw0`) plus a function-scoped autouse flush-by-prefix
  fixture (the DB is truncated between tests — the cache must be too, or
  modules see stale HITs). The flush fixture must save/restore
  `app.state.redis_cache` around each test, because some tests swap in their
  own `MagicMock`/`_FakeCache` on the shared module-scoped app
  (`test_routes.py`, `test_dashboard.py`) and must not permanently displace the
  real backend.
- TR9: CI (`.github/workflows/ci.yml`): add a `redis:8` service container and
  `TEST_REDIS_URL` env to the backend-test job (Postgres service-container
  parity; pinned like `postgres:17` is).
- TR10: No changes to `pyproject.toml` dependencies (`redis[hiredis]` already
  mandatory; no `fakeredis`).

## Implementation Plan

### Phase 1: Core code path removal

- `common/redis.py`: delete `NullCache`; unwrap `get`/`set`/`delete` error
  handling (keep `ping()` bool semantics and the SCAN-based delete diagnostics).
- `api/cache.py`: remove `if cache is None: return func(...)` from both wrappers;
  remove the degrade catches in `_lookup`/`_store`; catch
  `redis.exceptions.RedisError` in the wrappers and raise `HTTPException(503)`.
- `api/cache_invalidation.py`: non-Optional `_cache()`, drop the None-skip log
  branch, ERROR-level (not WARNING) logging in `_drop`, docstring updates.
- `api/app.py`: unconditional backend construction in `lifespan` + startup ping
  log; `/health/ready` always includes redis and flips to `not_ready`/503 on
  `ping() == False`; remove `redis_enabled` from `create_app()` signature,
  `app.state`, and `create_app_from_env()`.
- `api/cli.py`: remove the enable flag option/param; always echo Redis target.
- `common/config.py`: remove `redis_enabled` from `APISettings`.

### Phase 2: Compose & infrastructure

- `docker-compose.yml`: update the redis service header comment (required);
  api service — remove `REDIS_ENABLED` env, add the `required: false` healthy
  `depends_on` (migrate→postgres pattern). Keep `all`/`cache` profiles.
- `docker-compose.dev.yml`: `redis: profiles: [core]` union, identical shape to
  the existing `postgres:` block.
- `docker-compose.prod.yml`: extend the header NOTE to cover Redis alongside
  Postgres (bundled service not in `core`; use `REDIS_*` against the shared
  instance; `--profile cache` to opt into the bundled one).
- `e2e/docker-compose.test.yml`: add the redis service; api `depends_on` +
  `REDIS_HOST=redis`.
- `.env.example`: delete `REDIS_ENABLED`; rewrite the Redis block comments
  (required dependency; bundled in dev; external for prod; key-prefix isolation
  for multi-instance stays).
- `README.md`: profile table — `core` row gains redis: "postgres, redis (dev
  override only), migrate, collector, api, web"; `cache` row loses
  "(optional)" wording (mirror the `postgres` row: "Bundled Redis, standalone
  opt-in"); extend the "Database note" paragraph (~README.md:121) to cover
  Redis with the same profile-union / no-shadowing rationale.

### Phase 3: Test infrastructure (real Redis)

- `docker-compose.test-db.yml`: add `test-redis` (see TR8); update file header.
- `Makefile`: no target changes (same compose file drives `test-db-up`/`down`);
  update comments mentioning the throwaway DB to mention Redis.
- `tests/conftest.py`: `TEST_REDIS_URL` resolution + ping fail-fast
  (mirror the `TEST_POSTGRES_URL` hint).
- `tests/test_api/conftest.py`: real `RedisCacheBackend` wired in
  `app_no_auth`/`app_with_auth`/`app_spam` (via `_wire_overrides`) with
  worker-unique `key_prefix`; autouse per-test flush-by-prefix fixture.
- `.github/workflows/ci.yml`: redis service container + `TEST_REDIS_URL`.

### Phase 4: Test updates

- `tests/test_api/test_cache.py`:
  - delete `TestNullCache` and all `NullCache` wiring (~lines 102–117, 318,
    792–808, 1969–1985, 2069–2073 — the "cache_control_ttl emitted even with
    NullCache" tests become plain backend-present tests);
  - rewrite `TestLifespanRedis`: always-constructs-from-app.state + close-on-
    shutdown (drop the disabled/NullCache case);
  - rewrite `TestCliRedis` (~lines 1149–1279): `test_redis_enabled_shows_banner`
    drops the `--redis-enabled` flag (banner always shows);
    `test_redis_disabled_hides_details` is deleted;
    `test_redis_params_passed_to_create_app` drops `redis_enabled` from the
    expected `create_app()` kwargs (asserted at ~line 1224);
  - add hard-fail tests: backend raising `RedisError` on GET/SET ⇒ endpoint
    responds 503;
  - keep the mocked-`redis.Redis` unit tests in `TestRedisCacheBackend`.
- `tests/test_api/test_app_factory.py`: drop `redis_enabled` assertions; delete
  `test_factory_redis_enabled_accepts_truthy_values`; adjust
  `test_factory_reads_database_and_redis_from_env`; remove `"REDIS_ENABLED"`
  from the `_FACTORY_ENV` cleanup list (line 19).
- Rewrite the existing `TestHealthReadyRedis` (test_cache.py:1101–1148):
  `test_health_ready_omits_redis_when_disabled` is deleted (redis is always
  reported now); the connected/unreachable tests drop their
  `redis_enabled` assignments and mock-swap instead of delete
  `app.state.redis_cache`; **`test_health_ready_reports_unreachable` flips
  from asserting 200 to asserting 503 + `"status": "not_ready"`** — the
  current 200 assertion is exactly the behaviour FR2 removes.
- Tests that already assign `MagicMock()`/`_FakeCache` to
  `app.state.redis_cache` (`test_routes.py`, `test_dashboard.py`) continue to
  work unchanged.

### Phase 5: Documentation

- `docs/upgrading.md`: new `## v0.20.0` section (v0.19.0 is already tagged and
  shipped — `git tag --contains 81dcd3d` = v0.19.0): Redis now required,
  `REDIS_ENABLED` removed (a leftover value is ignored), production
  external-Redis guidance, dev stack now ships Redis in `core`. Do NOT edit the
  historical v0.19/v0.12 sections that mention `REDIS_ENABLED` (lines ~416,
  438, 455) — those are release-history records of past behaviour.
- `docs/configuration.md` + `docs/deployment.md`: caching sections rewritten —
  required dependency; drop `REDIS_ENABLED` row; bundled-vs-external guidance;
  multi-instance `REDIS_KEY_PREFIX` note stays. The deployment.md sweep covers
  **all** `REDIS_ENABLED` mentions, including the one outside the caching
  section in the multi-worker guidance (~line 96), plus the Docker/bare-metal
  ones (~lines 106, 113).
- `AGENTS.md`: update the cache-invalidation convention line ("helper is a no-op
  when Redis is disabled" → mandatory backend, never-raise-after-commit
  rationale); `core` stack description gains redis; test-db instructions now
  cover Postgres + Redis.
- `docs/plans/20260830-2057-mandatory-redis/` (this plan; add `tasks.md`
  alongside if the workflow calls for it).

### Phase 6: Verification

- `make test-db-up && pytest -nauto --no-cov 2>&1 | grep -iE "passed|failed" | tail -3`
- `pre-commit run --all-files`
- `npx playwright test --config=e2e/playwright.config.ts --list` (collection
  check only; the user builds/runs the e2e stack)
- No image builds / `make up` — the user builds and runs the stack manually.

## References

- `docs/plans/20260609-2106-redis-api-cache/plan.md` — original (optional) Redis
  cache implementation; source of the `NullCache`/`REDIS_ENABLED` pattern being
  removed.
- `docs/plans/20260829-2312-remove-sqlite-support/plan.md` — PostgreSQL-mandatory
  precedent whose compose profile-union pattern this plan mirrors.
- `docs/plans/20260613-2111-postgres-migration/plan.md` — earlier PostgreSQL
  migration background.
- Commit `81dcd3d` — "Remove SQLite support; PostgreSQL is now the only database
  backend" (scope model for config/CLI/tests/docs sweep).
- Commit `5a8794f` — "fix(compose): keep bundled postgres out of the core profile
  in production" (the dev-union/prod-exclusion mechanism reused here).
- AGENTS.md → "Cache invalidation on writes" (convention text requiring update).
- `docs/deployment.md` → "Redis Caching", `docs/configuration.md` → "Caching",
  `.env.example` Redis block (operator docs requiring rewrite).

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-08-30

### Resolutions

- **FR4 invalidation semantics (open question)**: confirmed by user —
  `invalidate_*` never raises after a committed write (ERROR log); only
  read/store paths hard-fail with 503. FR4 text updated to record the
  confirmation.
- **Version heading (open question)**: resolved to `## v0.20.0` — evidence:
  `git tag --contains 81dcd3d` = `v0.19.0` and `git describe --tags` =
  `v0.19.0`, so v0.19 (the SQLite-removal release) is already tagged/shipped;
  the Redis change lands in the next release.
- **CI Redis pinning (open question)**: resolved to `redis:8` — evidence:
  ci.yml pins the Postgres service to `postgres:17` with the comment "Pinned
  to match the bundled postgres:17-alpine" (ci.yml:87-88); the bundled Redis is
  `redis:8-alpine` (docker-compose.yml:135), so `redis:8` follows the same
  convention.
- **`cache` compose profile (open question)**: resolved — keep it, mirroring
  the retained `postgres` standalone profile; README `cache` row reworded to
  "Bundled Redis, standalone opt-in".
- **Gap found: `TestCliRedis`** (test_cache.py:1149–1279) exercises the
  `--redis-enabled` flag and asserts "Redis enabled: True/False" banners —
  missing from the original Phase 4. Rewrite/delete instructions added.
- **Gap found (re-verification): `TestHealthReadyRedis`**
  (test_cache.py:1101–1148) — an existing class the plan only said to
  "add" tests for. Its `test_health_ready_reports_unreachable` asserts
  **200** today; under FR2 it must assert **503 `not_ready`**, and
  `test_health_ready_omits_redis_when_disabled` must be deleted. Rewrite
  instructions added to Phase 4.
- **Gap found (re-verification): deployment.md sweep scope.** A
  `REDIS_ENABLED=true` recommendation sits in the multi-worker guidance
  (docs/deployment.md:96), outside the caching section (~106, ~113) — Phase 5
  now covers all mentions explicitly.
- **Gap found: `_FACTORY_ENV`** (test_app_factory.py:19) lists `REDIS_ENABLED`
  in its env-cleanup list — removal added to Phase 4.
- **Gap found: `health_ready` docstring** reads "database and optional Redis"
  (app.py:300) — docstring update added to TR3.
- **Gap found: compose env comment** "# Redis cache (optional — API works
  without Redis)" on the api service — rewrite added to TR7.
- **Risk found: mock-swapping tests.** Some tests assign a
  `MagicMock`/`_FakeCache` to `app.state.redis_cache` on the shared
  module-scoped app (test_routes.py:441, test_dashboard.py:1347); with a real
  default backend that would permanently displace it. TR8's flush fixture now
  saves/restores `app.state.redis_cache` around each test.
- **Verified no conflict: e2e startup.** The e2e api healthcheck probes the
  basic `/health` (e2e/docker-compose.test.yml:182), not `/health/ready`, so
  the new 503 readiness cannot deadlock stack startup. The e2e api sets no
  `REDIS_*` env at all, so `REDIS_HOST=redis` is mandatory there (added to
  TR7).
- **Verified: no Makefile target changes.** `test-db-up` runs
  `$(TEST_DB_COMPOSE) up -d --wait` on the whole file (Makefile:80-81), so a
  new `test-redis` service starts automatically; `--wait` requires its
  healthcheck (already in TR8).
- **Verified: fail-fast pattern.** The `db_url` fixture exits via
  `pytest.exit(..., returncode=4)` with a `make test-db-up` hint
  (tests/conftest.py:122-144); TR8 mirrors it for Redis.
- **Verified no plan conflict.** The remove-sqlite plan schedules the
  `database_backend` field / `migrate-to-postgres` removals for v0.20 — the
  same release hosts this change; the upgrading.md sections are additive, no
  overlap.

### Remaining Action Items

- Implement Phases 1–6 (not started); run the Phase 6 verification commands.
- During Phase 5, leave the historical `REDIS_ENABLED` mentions in the
  v0.19/v0.12 upgrading.md sections untouched (release-history records).
- When rewriting `TestCliRedis`, note the CLI keeps its
  "Redis: host:port/db", "Redis key prefix:", and TTL echoes (cli.py:304-309)
  — only the enabled/disabled banner and the flag disappear.
