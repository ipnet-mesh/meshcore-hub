# Remove SQLite Support — PostgreSQL-Only from v0.19

## Summary

v0.19 drops SQLite entirely and makes PostgreSQL the only supported database
backend. The dual-backend machinery introduced in v0.14 (`DATABASE_BACKEND`
switch, SQLite defaults, dialect branches, WAL pragmas, the SQLite test path)
is removed from application code, config, Docker packaging, tests, and docs.
`DATA_HOME` stays (it still holds seed files, health files, and web data), but
the `${DATA_HOME}/collector/meshcore.db` concept disappears.

The test suite is rebuilt on Postgres: backend tests run against a **dedicated
test database within a provided Postgres instance**, and each pytest-xdist
worker isolates itself with its own **schema via `search_path`** (instead of a
temporary SQLite file or per-worker databases). This keeps tests runnable with
a least-privileged role (no `CREATE DATABASE`/superuser needed) and exercises
exactly the same code path as production.

Two items are deliberately **kept for one release** (removed in v0.20): the
read-only `db migrate-to-postgres` escape-hatch command, and the
`database_backend` settings field (which now rejects `sqlite` with a targeted
upgrade error instead of silently selecting anything).

## Background & Motivation

- **v0.14 added Postgres and deprecated SQLite** (plan
  `docs/plans/20260613-2111-postgres-migration/plan.md`; README deprecation
  notice; `docs/database.md`: "SQLite is deprecated in favour of PostgreSQL...
  support will be removed in a future release"). v0.19 is that removal.
- **Dual-backend support is an ongoing tax.** SQLite-specific logic is spread
  across the codebase: WAL/pragma event listeners and in-memory pool
  special-casing in `common/database.py`, the dialect-aware upsert in
  `common/models/event_observer.py`, `render_as_batch` conditionals in
  `alembic/env.py`, the `DatabaseBackend` enum + SQLite default URL in
  `common/config.py`, the `db migrate-to-postgres` tooling, a two-mode test
  harness (`TEST_DATABASE_BACKEND`), and dual-backend documentation in six
  docs files.
- **Recent feature work is already Postgres-first.** The v0.18 route-perf
  migration (`a59611449e2a`) uses a covering index with `INCLUDE` — "SQLite
  does not support INCLUDE; its existing plain index is left untouched (SQLite
  is dev/test-scale only)" (`alembic/versions/20260725_1200_*`). The e2e
  stack has always been Postgres-only (`e2e/docker-compose.test.yml`).
- **SQLite constrains the deployment model** it was meant to simplify: no
  multi-host scaling, file locking unusable on network filesystems, single
  writer. Postgres (bundled container by default) gives the same
  "compose up and it works" experience without those limits.
- Recent git history (v0.16–v0.18 hardening: `e87a002`, `3f9669f`, `b23e7bc`,
  `dca3dcb`) has been correctness/ops work on the Postgres path — the backend
  is mature enough to stand alone.

## Goals

- Remove every SQLite runtime code path, dependency, config knob, and doc
  reference; Postgres is the only backend after v0.19.
- A default `docker compose up` remains zero-effort: the bundled `postgres`
  container becomes part of the `core` profile (no extra profile flag),
  including a working default password so the stack initializes out of the
  box.
- Missing/invalid database configuration fails fast at startup with a clear
  error (no silent fallback, no half-configured state).
- Backend tests (unit + integration, `tests/`) run **only** against Postgres:
  a dedicated test database in a provided Postgres instance, per-worker schema
  isolation via `search_path`.
- CI runs the suite against a Postgres service container.
- Existing SQLite deployments migrate in place on v0.19 via the retained
  `meshcore-hub db migrate-to-postgres` command (read-only SQLite access via
  Python's stdlib `sqlite3` driver — not a runtime backend), with removal of
  that command scheduled for v0.20.

## Non-Goals

- **No schema redesign** and no new Alembic migrations beyond what the removal
  itself requires (none expected).
- **No rewriting of shipped Alembic revisions.** Historical migrations already
  replay cleanly from scratch on Postgres (fresh installs prove this today);
  their SQLite mentions are comments or already-guarded dialect branches.
  Editing them risks needless divergence from deployed revision history.
- **No admin/bootstrap credentials anywhere** (consistent with the
  postgres-migration plan's provisioning decision). Tests must work with a
  least-privileged role that owns its test database — hence schema-per-worker
  instead of database-per-worker.
- No driver migration (keep `psycopg2-binary` + `asyncpg`; psycopg v3 is a
  follow-up at best).
- No frontend changes (the SPA never touches the DB).
- No changes to Redis/MQTT/observer/traefik packaging.
- No removal (yet) of `db migrate-to-postgres`, the `database_backend`
  settings field, or the `[postgres]` extra alias — those get one release of
  deprecation grace and are removed in v0.20 (tracked as follow-ups).

## Requirements

### Functional Requirements

1. The collector, API, web, migrate, and seed components start only against a
   configured PostgreSQL database; startup fails fast with an actionable error
   naming the missing variables when connection config is absent.
2. The `database_backend` settings field is kept for one release as a rejected
   legacy switch: `DATABASE_BACKEND=sqlite` raises a targeted error ("SQLite
   support was removed in v0.19 — migrate with `db migrate-to-postgres`, see
   docs/upgrading.md") instead of being silently discarded by
   `extra="ignore"`; `DATABASE_BACKEND=postgres` is accepted as a no-op. The
   field is deleted in v0.20.
3. An explicit `DATABASE_URL` still overrides the component vars (managed /
   external Postgres escape hatch, tests).
4. Default compose deployment: `postgres` service starts with the `core`
   profile; `migrate` waits for it to be healthy; `collector`/`api` come up
   against it with no extra flags. The bundled container ships a **default
   password** (`meshcorehub`, overridable via `DATABASE_PASSWORD`) so the
   postgres image initializes and the app services can connect with zero
   config; production overrides are documented.
5. `meshcore-hub db migrate-to-postgres` remains available in v0.19 (sync
   SQLAlchemy copy, stdlib sqlite3 driver only) and is documented as the
   upgrade path; its v0.20 removal is announced in `docs/upgrading.md`.
6. `make test` and CI produce a green backend suite with no SQLite anywhere in
   the pipeline.

### Technical Requirements

1. **Dependencies:** drop `aiosqlite`; move `asyncpg` and `psycopg2-binary`
   from the `[postgres]` optional extra into core `dependencies`; keep
   `[postgres]` as an empty alias extra for one release (external install
   instructions may reference it) and remove it in v0.20.
2. **Config (`common/config.py`):** keep `database_backend` as a
   validated-rejection field (Functional Requirement 2); remove the SQLite
   default URL branch so `effective_database_url` is "explicit `DATABASE_URL`
   or assembled Postgres URL", failing fast on missing
   host/name/user/password; `effective_database_schema` always returns
   `database_schema`. `DATA_HOME` remains for seed/health/content paths
   (`collector_data_dir`, `web_data_dir`, `node_tags_file`, ...).
3. **Engine layer (`common/database.py`):** delete the SQLite branches —
   `check_same_thread`, PRAGMA event listeners (sync + async), in-memory pool
   special-casing, the sqlite arm of `_to_async_url`, the parent-dir mkdir.
   `search_path`/timezone wiring becomes unconditional for all connections.
   The existing `schema=` parameter on `create_database_engine` /
   `DatabaseManager` is what the test harness uses for worker isolation.
4. **Models:** `add_event_observer()` in `common/models/event_observer.py`
   becomes a plain `sqlalchemy.dialects.postgresql.insert` upsert.
5. **Alembic:** `alembic/env.py` drops the `render_as_batch` conditional and
   the `None`-schema branch (`version_table_schema`/`include_schemas` always
   set); `alembic.ini` loses its `sqlite:///./meshcore.db` placeholder URL
   (env.py resolves the real URL).
6. **CLI/app defaults:** replace `sqlite:///./meshcore.db` default arguments
   and help text in `api/app.py:34,75`, `api/cli.py:33`,
   `collector/cli.py:90`, `collector/subscriber.py:919,1005`; the app factory
   should require an explicit URL (or resolve it from settings) rather than
   defaulting to a file DB. `__main__.py` keeps only the
   migrate-to-postgres source-URL default (retained command).
7. **Docker:** `docker-compose.yml` moves `postgres` into the `core` (and
   `all`) profile, makes `migrate` `depends_on: postgres: condition:
   service_healthy` (required), drops the `DATABASE_BACKEND` env lines from
   `collector`/`api`/`migrate`, and gives both the `postgres` container and
   the app services a shared default password
   (`${DATABASE_PASSWORD:-meshcorehub}`). `Dockerfile` drops the `sqlite3`
   apt package (the retained migration command only needs Python's stdlib
   driver). The `data` volume stays (seed/health).
8. **Test harness:** Postgres-only fixtures (detail in Phase 1). No temporary
   SQLite files, no `TEST_DATABASE_BACKEND` switch.
9. **Docs:** README (remove deprecation notice → removal notice),
   `docs/database.md` (Postgres-only reference), `docs/configuration.md`,
   `docs/deployment.md`, `docs/seeding.md`, `docs/upgrading.md` (new v0.19
   section with the in-place SQLite→Postgres runbook), `.env.example`, and
   the "Database & Ops" + test sections of `AGENTS.md`.

## Implementation Plan

The ordering is deliberate: **convert the test suite to Postgres first while
SQLite code still exists** (the suite already passes on Postgres via
`TEST_DATABASE_BACKEND=postgres`, so this is low-risk and keeps a green gate),
**then** delete SQLite from the application, then infra/deps/docs. Each phase
ends with the full suite green.

### Phase 1: Postgres-only test harness (suite converts first)

- Add a throwaway test-database stack: `docker-compose.test-db.yml` (new file)
  running `postgres:17-alpine` published on `127.0.0.1:55432`, with
  `POSTGRES_USER=meshcorehub`, a fixed dev-only
  `POSTGRES_PASSWORD=meshcorehub-test`, `POSTGRES_DB=meshcorehub_test`,
  ephemeral volume, and `command: ["postgres", "-c", "max_connections=200"]`
  (see Risks: connection-pool pressure). The app role **owns** the database
  (image entrypoint), which is exactly the privilege schema creation needs —
  no superuser, no `CREATEDB`.
- Makefile: add `test-db-up` / `test-db-down` targets and document them in the
  `test` / `test-unit` comments. Reachability is enforced by pytest itself:
  the session fixture fails fast with an actionable "run `make test-db-up`"
  message (Makefile shell probing of Postgres is not worth the complexity).
- `tests/conftest.py`:
  - Delete `db_engine` (in-memory SQLite), `test_db_path` (temp file), the
    `db_backend` fixture, and the SQLite branch of `db_url`.
  - `db_url` becomes Postgres-only, driven by `TEST_POSTGRES_URL` (default
    `postgresql+psycopg2://meshcorehub:meshcorehub-test@localhost:55432/meshcorehub_test`).
    Missing/unreachable DB → `pytest.exit()` with an actionable message
    (not a skip — Postgres is now mandatory).
  - **Worker isolation via schema, not database:** derive
    `schema = f"hub_test_{worker_id}"` (`hub_test_master`, `hub_test_gw0`, ...)
    from the xdist worker id. The role owns the database, so the fixture
    creates its schema with a plain connection
    (`CREATE SCHEMA IF NOT EXISTS "hub_test_gw0"`) — no admin connection to
    the `postgres` maintenance DB like today's `CREATE DATABASE` dance — then
    builds the engine through the production factory:
    `create_database_engine(db_url, schema=<worker_schema>)`, so tests
    exercise the same `search_path`/`-ctimezone=UTC` wiring as production.
    Teardown: `DROP SCHEMA "<schema>" CASCADE`.
  - Replace the shared `db_engine`/`db_session` fixtures with Postgres-backed
    equivalents bound to the worker schema; keep the truncate-between-tests
    pattern from `tests/test_api/conftest.py::_truncate_all`.
- Convert the **local SQLite fixtures the shared-fixture rewrite doesn't
  reach** (audit, verified during review):
  - `tests/test_api/test_channel_visibility.py` (own in-memory
    `sqlite:///:memory:` `db_session` fixture, line 23) → use the shared
    Postgres-backed fixture.
  - `tests/test_common/test_models.py` (local `db_session`, line 26) and
    `tests/test_common/test_channel_model.py` (line 19) → same.
  - `tests/test_collector/conftest.py::async_db_session` (in-memory
    `sqlite+aiosqlite:///:memory:` + pragma listener) → async session from the
    worker-schema `DatabaseManager` (production `async_session()` path).
  - `tests/test_api/conftest.py` and `tests/test_collector/conftest.py`
    proper: delete the `db_backend == "postgres"` branches and the SQLite
    pragma listeners; `api_db_engine` / `db_manager` use the schema-scoped
    engine unconditionally.
- Rewrite the SQLite-specific test files:
  - `tests/test_common/test_database.py` — drop in-memory/SQLite cases
    (`test_sqlite_never_has_schema`, `test_async_engine_skips_pool_args_for_memory_sqlite`,
    pragma assertions); add/keep Postgres `search_path` + timezone assertions.
  - `tests/test_common/test_config.py` — replace
    `test_default_backend_is_sqlite_unchanged` etc. with the new
    resolution contract (components → URL, missing-var error, `DATABASE_URL`
    override, `DATABASE_BACKEND=sqlite` rejection, `DATABASE_BACKEND=postgres`
    no-op).
  - `tests/test_common/test_db_migrate.py`, `tests/test_main.py` — **kept**
    for the retained migration command (stdlib sqlite3 only; verify no
    aiosqlite import creeps in).
- CI (`.github/workflows/ci.yml`): add a `postgres:17` service container
  (version pinned to match the bundled `postgres:17-alpine`) to the test job
  and export `TEST_POSTGRES_URL` pointing at it. Remove any SQLite assumption
  from the test step.
- **Gate 1:** full backend suite green on Postgres with SQLite still present
  in the code (this is effectively today's `TEST_DATABASE_BACKEND=postgres`
  mode, promoted to the only mode).

### Phase 2: Remove SQLite from application code

- `common/config.py`: keep `database_backend` for one release as the
  rejected-legacy switch (Functional Requirement 2); collapse
  `effective_database_url` to "explicit URL or assembled Postgres URL";
  `effective_database_schema` always returns `database_schema`.
- `common/database.py`: remove all SQLite branches listed in Technical
  Requirement 3; simplify `_to_async_url` to the Postgres mapping; update
  comments that contrast with SQLite behaviour (timezone pinning rationale
  stays, reworded).
- `common/models/event_observer.py`: Postgres-only upsert.
- `alembic/env.py` + `alembic.ini`: Postgres-only (Technical Requirement 5).
- `api/app.py`, `api/cli.py`, `collector/cli.py`, `collector/subscriber.py`:
  remove `sqlite:///...` defaults/help text; require configured connection.
- `api/routes/dashboard.py`: update the SQLite-contrast comments (lines 104,
  433, 451); the `func.date()` str-vs-date coercion stays (it is the
  dialect-neutral fix from plan `20260616-2023-fix-postgres-charts-flatline`).
  `collector/spam.py` has no SQLite references (verified) — no change there.
- `common/db_migrate.py` + the `db migrate-to-postgres` command in
  `__main__.py`: **kept** in v0.19 (decided); annotate the module docstring
  with its v0.20 removal.
- Rewrite `tests/test_api/test_app_factory.py` — it currently asserts the
  SQLite default URL resolution (`sqlite:////srv/hubdata/collector/meshcore.db`,
  lines 52–79); switch those assertions to the Postgres resolution contract.
  Sweep `tests/test_api/test_cache.py` mock URLs (`sqlite:///...` strings,
  lines 1011–1271) to Postgres URLs for cleanliness (they are opaque mock
  values — cosmetic, but the audit grep must come out clean).
- **Gate 2:** full suite green; grep audit: no `sqlite` remains in `src/`
  (case-insensitive) except the intentionally-kept `db_migrate.py` /
  `__main__.py` migration tooling, and none in `tests/` except that tooling's
  tests.

### Phase 3: Infra & packaging

- `docker-compose.yml`: `postgres` gains `core`/`all` profiles (currently
  only `postgres`); `migrate.depends_on.postgres.required: true`; drop
  `DATABASE_BACKEND=${DATABASE_BACKEND:-sqlite}` from `collector`/`api`/
  `migrate` env; keep the `DATABASE_*` block; change
  `POSTGRES_PASSWORD=${DATABASE_PASSWORD:-}` →
  `${DATABASE_PASSWORD:-meshcorehub}` and mirror the same default in the app
  services' `DATABASE_PASSWORD` so the zero-config stack connects (the
  current empty default would make the postgres image refuse to initialize).
  Update the service header comments.
- `Dockerfile`: remove the `sqlite3` apt package (line 90; added by plan
  `20260517-1623-sqlite3-docker-image`). Safe even with the retained
  migration command — it only needs Python's stdlib sqlite3 driver.
- `docker-compose.dev.yml` / `.prod.yml` / `.traefik.yml`: verify no
  SQLite/backend assumptions (current audit: none).
- `e2e/docker-compose.test.yml`: drop the now-meaningless
  `DATABASE_BACKEND=postgres` lines (3 places: lines 53, 129, 172);
  everything else already Postgres-only.
- **Gate 3:** user builds and brings up the stack (assistant does not build
  images per AGENTS.md): `core` profile comes up with bundled Postgres,
  `migrate` completes, collector ingests, API/web serve.

### Phase 4: Dependencies

- `pyproject.toml`: remove `aiosqlite` from `dependencies`; move
  `asyncpg>=0.28.0` and `psycopg2-binary>=2.9.0` into `dependencies`; keep
  `[postgres]` as an empty alias extra for one release (commented
  "deprecated, no-op — drivers are core dependencies since v0.19; removed in
  v0.20"); update the `[dev]` comment about the "dual-backend test suite".
- Refresh `.venv` (`pip install -e ".[dev]"`) and confirm no import references
  `aiosqlite`.
- **Gate 4:** full suite + `pre-commit run --all-files` green.

### Phase 5: Documentation & upgrade story

- `docs/upgrading.md`: new **v0.19** section — breaking-change notice
  ("SQLite support removed"), the in-place runbook using the retained
  `db migrate-to-postgres` command (backup → stop writers → bring up Postgres
  → migrate → restart), the `DATABASE_BACKEND=sqlite` rejection behaviour,
  the new bundled default password (and that production must override it),
  and the v0.20 removal schedule for the migration command, the
  `database_backend` field, and the `[postgres]` extra alias.
- `docs/database.md`: Postgres-only reference — remove the "SQLite (default)"
  and backend-choice sections, keep bundled-container setup, managed/external
  Postgres, schema-per-instance provisioning, and the migration section
  (repositioned as upgrade guidance).
- `docs/configuration.md` (`DATA_HOME` description, `DATABASE_BACKEND` row),
  `docs/deployment.md` (SQLite caveats → removed), `docs/seeding.md`
  (directory tree without `meshcore.db`), `.env.example` (Database section
  rewrite: `DATABASE_*` defaults, no SQLite commentary, `DATA_HOME` comment
  without the db file).
- `README.md`: replace the deprecation notice with a short "PostgreSQL-only"
  statement; update doc-tree descriptions.
- `AGENTS.md`: rewrite "Database & Ops" (default backend is now the bundled
  Postgres; migration authoring runs against a local PG schema instead of a
  copied `./meshcore.db` file) and the test commands (tests require
  `make test-db-up` / `TEST_POSTGRES_URL`).
- **Gate 5:** docs cross-reference sweep (grep for `sqlite`, `DATA_HOME` +
  `meshcore.db`, `DATABASE_BACKEND`) returns only intentional mentions
  (historical plan files, upgrading.md history, retained migration tooling).

### Phase 6: Final verification

- `pytest -nauto --no-cov` (full backend suite on Postgres),
  `npm run test:frontend`, `npx tsc --noEmit`, `pre-commit run --all-files`,
  `npm run typecheck:e2e` + `npx playwright test --list` (collection only).
- Fresh-install proof: against a clean test database, `meshcore-hub db upgrade`
  from revision zero completes on Postgres (exercises the full migration
  history without SQLite).
- User-run: `make build && make up` on the `core` profile; e2e via
  `make e2e-build && make e2e-up && make e2e-test`.

## Risks & Mitigations

- **Connection-pool pressure in tests.** The production factory hardcodes
  `pool_size=20` / `max_overflow=30`; with `pytest -nauto` every xdist worker
  holds its own engine against one shared test database, so worst-case
  connection counts can exceed Postgres' default `max_connections=100`.
  Mitigated by running the test container with `-c max_connections=200`
  (Phase 1) and by the existing per-test engine disposal; revisit pool sizing
  if CI ever shows connection exhaustion.
- **Parallel plan conflict: mesh-link-monitoring.**
  `docs/plans/20260705-2306-mesh-link-monitoring/plan.md` is Approved but not
  yet implemented, and deliberately designs dual-backend code (`sqlite_insert`
  / `pg_insert` branches, Alembic batch-mode DDL, `SQLITE_MAX_VARIABLE_NUMBER`
  avoidance). If it lands before or alongside this plan, those SQLite branches
  become dead weight or conflicts. Coordination rule: **this plan lands
  first**; the link-monitoring implementation then targets Postgres-only
  (drop the `sqlite_insert` arm, keep plain `INSERT ... ON CONFLICT`-style
  upserts). Flag this in the link-monitoring plan when it is taskified.
- **Breaking change for `DATABASE_BACKEND=sqlite` deployments.** Mitigated by
  the retained migration command, the targeted startup error (not a silent
  ignore), and a prominent `docs/upgrading.md` v0.19 section — the same
  fail-loud philosophy the v0.14 plan used for half-configured Postgres.
- **Default password in the bundled container.** `meshcorehub` as the dev
  default is visible in the repo; the postgres container is not published
  outside the compose network, and the upgrade docs require production
  overrides. Accept the risk for zero-config parity with the old SQLite
  default.

## References

- `docs/plans/20260613-2111-postgres-migration/plan.md` — the plan that added
  Postgres, the `DATABASE_*`/schema-per-instance design, the no-admin-creds
  provisioning decision, and the `db migrate-to-postgres` command. This plan
  is its logical conclusion.
- `docs/plans/20260517-1623-sqlite3-docker-image/plan.md` — added the
  `sqlite3` CLI to the runtime image (Dockerfile line 90); removed here.
- `docs/plans/20260616-2023-fix-postgres-charts-flatline/plan.md` — early
  Postgres-semantics fix (timezone/day-boundary); its dialect-neutral
  `func.date()` coercion in `api/routes/dashboard.py` survives this plan.
- `docs/plans/20260705-2306-mesh-link-monitoring/plan.md` — approved,
  unimplemented dual-backend design; must land after this plan (see Risks).
- `docs/upgrading.md` — v0.14 "Optional PostgreSQL Backend" + "Migrating an
  existing SQLite database to Postgres" runbooks (basis for the v0.19 section).
- `README.md:11-12` — current SQLite deprecation notice (to be replaced).
- Key code sites: `src/meshcore_hub/common/config.py:27-129` (backend switch),
  `src/meshcore_hub/common/database.py:19-253` (SQLite branches),
  `src/meshcore_hub/common/models/event_observer.py:143-160` (dialect upsert),
  `alembic/env.py:41-114`, `src/meshcore_hub/__main__.py:88-180`
  (migrate-to-postgres), `tests/conftest.py:108-221` (current dual-backend
  fixtures), `docker-compose.yml:150-178,447-475` (postgres profile, migrate).

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-08-29

### Resolutions

- **Fate of `db migrate-to-postgres`** (was Open Question 1): user chose
  **keep in v0.19, remove in v0.20**. Reflected in Goals, FR5, Phase 2
  ("kept"), Phase 4 (no aiosqlite needed — sync stdlib sqlite3 driver), and
  the v0.19 upgrading.md runbook. Verified `db_migrate.py` uses only sync
  SQLAlchemy, so the aiosqlite dependency and Dockerfile `sqlite3` CLI are
  still removed.
- **`DATABASE_BACKEND` handling** (was Open Question 2): user chose **keep the
  settings field for one release; `sqlite` raises a targeted removal error,
  `postgres` is a no-op**. Reflected in FR2 and Phase 2.
- **Test Postgres source** (was Open Question 3): resolved to the recommended
  dedicated `docker-compose.test-db.yml` on `127.0.0.1:55432` +
  `make test-db-up/down` (isolates tests from dev data; no assistant-driven
  compose against the dev stack).
- **`[postgres]` extra** (was Open Question 4): resolved to the recommended
  empty alias extra for one release, removed in v0.20.
- **Schema naming/teardown** (was Open Question 5): resolved to the
  recommended `hub_test_<worker_id>` schemas with `DROP SCHEMA ... CASCADE`
  teardown; schema creation uses a plain connection (role owns the database),
  no admin/maintenance-DB connection.
- **CI Postgres pin** (was Open Question 6): resolved to `postgres:17`,
  matching the bundled `postgres:17-alpine`.
- **Zero-config password gap (new, found in review):** `docker-compose.yml`
  currently defaults `POSTGRES_PASSWORD`/`DATABASE_PASSWORD` to empty, which
  would break a default `compose up` once postgres joins `core`. Added
  FR4/TR7/Phase 3 resolution: shared default password `meshcorehub`
  (overridable), documented as dev-only; production must override.
- **Missed SQLite test fixtures (new, found in review):** added to Phase 1 —
  `tests/test_api/test_channel_visibility.py:23`,
  `tests/test_common/test_models.py:26`,
  `tests/test_common/test_channel_model.py:19`, and
  `tests/test_collector/conftest.py::async_db_session` (aiosqlite in-memory).
- **Missed SQLite-asserting tests (new, found in review):** added to Phase 2 —
  `tests/test_api/test_app_factory.py:52-79` (asserts SQLite default URL
  resolution) and cosmetic mock-URL sweep in `tests/test_api/test_cache.py`.
- **Factual correction:** Phase 2 originally cited SQLite comments in
  `collector/spam.py`; verified no SQLite references exist there. Removed;
  `api/routes/dashboard.py:104,433,451` confirmed as the real sites.
- **Connection-pool pressure (new, found in review):** added Risk + mitigation
  (`max_connections=200` on the test container).
- **mesh-link-monitoring coordination (new, found in review):** approved but
  unimplemented plan designs dual-backend code; added Risk with ordering rule
  (this plan lands first; link-monitoring implementation drops SQLite arms).

### Remaining Action Items

- Track for **v0.20**: removal of `db migrate-to-postgres` +
  `common/db_migrate.py` + its tests, the `database_backend` settings field,
  and the `[postgres]` extra alias (announce in the v0.19 upgrading.md).
- When taskifying `docs/plans/20260705-2306-mesh-link-monitoring`, add a note
  that its SQLite branches/batch-DDL design items are superseded by this plan.
- After Phase 3, user verifies the zero-config `core` profile boot (bundled
  Postgres + default password) per AGENTS.md build rules.
