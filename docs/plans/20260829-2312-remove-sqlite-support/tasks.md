# Tasks: Remove SQLite Support — PostgreSQL-Only from v0.19

> Generated from `plan.md` on 2026-08-30

## Phase 1: Postgres-only test harness (convert suite first)

- [x] Add throwaway test-database stack
  - [x] Create `docker-compose.test-db.yml`: `postgres:17-alpine` published on `127.0.0.1:55432`, `POSTGRES_USER=meshcorehub`, `POSTGRES_PASSWORD=meshcorehub-test`, `POSTGRES_DB=meshcorehub_test`, ephemeral volume, `command: ["postgres", "-c", "max_connections=200"]` (role owns the DB — no superuser/CREATEDB)
- [x] Add Makefile targets for the test DB
  - [x] Add `test-db-up` / `test-db-down`
  - [x] Reference them in the `test` / `test-unit` target comments (reachability enforced by pytest, not shell probing)
- [x] Rewrite `tests/conftest.py` core fixtures
  - [x] Delete `db_engine` (in-memory SQLite), `test_db_path` (temp file), `db_backend`, and the SQLite branch of `db_url`
  - [x] Make `db_url` Postgres-only via `TEST_POSTGRES_URL` (default `postgresql+psycopg2://meshcorehub:meshcorehub-test@localhost:55432/meshcorehub_test`); missing/unreachable DB → `pytest.exit()` with an actionable "run `make test-db-up`" message
  - [x] Worker isolation via schema: derive `schema = f"hub_test_{worker_id}"`, create it with a plain `CREATE SCHEMA IF NOT EXISTS` connection, build the engine via production `create_database_engine(db_url, schema=...)` (search_path + UTC wiring exercised); teardown `DROP SCHEMA "<schema>" CASCADE`
  - [x] Provide Postgres-backed `db_engine`/`db_session` equivalents bound to the worker schema, with the truncate-between-tests pattern
- [x] Clean the component conftests
  - [x] `tests/test_api/conftest.py`: delete `db_backend == "postgres"` branches and SQLite pragma listeners; `api_db_engine` uses the schema-scoped engine unconditionally
  - [x] `tests/test_collector/conftest.py`: same cleanup; rebuild `async_db_session` (in-memory aiosqlite + pragma listener) as an async session from the worker-schema `DatabaseManager` (production `async_session()` path)
- [x] Convert local SQLite fixtures not reached by the shared rewrite
  - [x] `tests/test_api/test_channel_visibility.py:23` — own in-memory `db_session` → shared Postgres fixture
  - [x] `tests/test_common/test_models.py:26` and `tests/test_common/test_channel_model.py:19` — local `db_session` → shared fixture
  - [x] `tests/test_collector/test_cli.py` — `TestChannelCommands::cli_db_url` (line 128, real temp-file SQLite; usages 287, 406, 439, 699) → worker-schema Postgres engine with truncate between tests
  - [x] `tests/test_api/test_metrics.py:89,381` — isolated app instances built from `sqlite:///{test_db_path}` (fixture being deleted) → worker-schema Postgres URL with truncate isolation
  - [x] `tests/test_collector/test_tag_import.py:180` — in-memory `DatabaseManager` → worker-schema `DatabaseManager`
  - [x] `tests/test_collector/test_subscriber.py:1376` — `database_url="sqlite:///:memory:"` factory arg → Postgres test URL
- [x] Reword stale SQLite comments/docstrings in tests (wording only, tests stay)
  - [x] `tests/test_api/test_dashboard.py:30,1366` (`_date_bucket_key` tests stay — helper is dialect-neutral)
  - [x] `tests/test_collector/test_handlers/test_contacts.py:76`
  - [x] `tests/test_api/test_user_profiles.py:103`
  - [x] `tests/test_api/test_routes.py:521` ("the shared SQLite file")
  - [x] `tests/test_collector/test_spam.py:4`
  - [x] `tests/test_collector/test_cli.py:126` (class docstring)
- [x] Rewrite SQLite-specific test files
  - [x] `tests/test_common/test_database.py` — drop `test_sqlite_never_has_schema`, `test_async_engine_skips_pool_args_for_memory_sqlite`, pragma assertions; keep/add Postgres `search_path` + timezone assertions
  - [x] `tests/test_common/test_config.py` — replace SQLite-default tests with the new resolution contract (components → URL, missing-var error, `DATABASE_URL` override, `DATABASE_BACKEND=sqlite` rejection, `DATABASE_BACKEND=postgres` no-op)
  - [x] Verify kept tests `tests/test_common/test_db_migrate.py` + `tests/test_main.py` still pass (stdlib sqlite3 only — no aiosqlite import creeps in)
- [x] CI (`.github/workflows/ci.yml`)
  - [x] Add a `postgres:17` service container (pinned to match bundled `postgres:17-alpine`) to the test job
  - [x] Export `TEST_POSTGRES_URL` pointing at it; remove SQLite assumptions from the test step
- [x] **Gate 1**: full backend suite green on Postgres with SQLite still present in the code

## Phase 2: Remove SQLite from application code

- [x] `src/meshcore_hub/common/config.py`
  - [x] Keep `database_backend` as validated-rejection field: `sqlite` raises targeted error ("SQLite support was removed in v0.19 — migrate with `db migrate-to-postgres`, see docs/upgrading.md"); `postgres` accepted as no-op
  - [x] Collapse `effective_database_url` to "explicit `DATABASE_URL` or assembled Postgres URL", failing fast on missing host/name/user/password
  - [x] `effective_database_schema` always returns `database_schema`
- [x] `src/meshcore_hub/common/database.py`
  - [x] Delete SQLite branches: `check_same_thread`, PRAGMA event listeners (sync + async), in-memory pool special-casing, sqlite arm of `_to_async_url`, parent-dir mkdir
  - [x] Make `search_path`/timezone wiring unconditional; reword SQLite-contrast comments (timezone rationale stays)
- [x] `src/meshcore_hub/common/models/event_observer.py` — `add_event_observer()` becomes a plain `sqlalchemy.dialects.postgresql.insert` upsert
- [x] Alembic
  - [x] `alembic/env.py`: drop `render_as_batch` conditional and `None`-schema branch (`version_table_schema`/`include_schemas` always set)
  - [x] `alembic.ini`: remove the `sqlite:///./meshcore.db` placeholder URL (line 40)
- [x] Remove SQLite defaults/help text from CLI/app entry points
  - [x] `src/meshcore_hub/api/app.py:34,75` — app factory requires explicit URL or settings resolution (no file-DB default)
  - [x] `src/meshcore_hub/api/cli.py:33` — default arg + help text
  - [x] `src/meshcore_hub/collector/cli.py:90` — default arg + help text
  - [x] `src/meshcore_hub/collector/subscriber.py:919,1005` — `database_url` defaults
  - [x] `src/meshcore_hub/__main__.py` — keep only the migrate-to-postgres source-URL default (retained command)
- [x] Comment/docstring sweeps in app code
  - [x] `src/meshcore_hub/api/routes/dashboard.py:104,433,451` — update SQLite-contrast comments (keep `func.date()` coercion)
  - [x] `src/meshcore_hub/collector/spam.py:7` — module docstring "Postgres/SQLite" reword
  - [x] `src/meshcore_hub/common/db_migrate.py` — annotate module docstring with v0.20 removal
- [x] Update SQLite-asserting tests
  - [x] Rewrite `tests/test_api/test_app_factory.py:52-79` — Postgres resolution contract instead of `sqlite:////srv/hubdata/...` defaults
  - [x] Sweep `tests/test_api/test_cache.py:1011-1271` mock `sqlite:///` URLs → Postgres URLs
- [x] **Gate 2**: full suite green; grep audit — no `sqlite` (case-insensitive) in `src/` except `db_migrate.py`/`__main__.py` tooling, none in `tests/` except that tooling's tests

## Phase 3: Infra & packaging

- [x] `docker-compose.yml`
  - [x] Move `postgres` into the `core` (and `all`) profile
  - [x] `migrate.depends_on.postgres`: `condition: service_healthy`, `required: true`
  - [x] Drop `DATABASE_BACKEND=${DATABASE_BACKEND:-sqlite}` env lines from `collector`/`api`/`migrate`
  - [x] `POSTGRES_PASSWORD=${DATABASE_PASSWORD:-meshcorehub}` and mirror the same default in app services' `DATABASE_PASSWORD` (zero-config boot); update service header comments
- [x] `Dockerfile` — remove the `sqlite3` apt package (line 90; stdlib driver suffices for the retained migration command)
- [x] Verify `docker-compose.dev.yml` / `.prod.yml` / `.traefik.yml` have no SQLite/backend assumptions
- [x] `e2e/docker-compose.test.yml` — drop the three `DATABASE_BACKEND=postgres` lines (53, 129, 172)
- [ ] **Gate 3** (user-run per AGENTS.md): user builds and brings up the `core` profile — bundled Postgres healthy, `migrate` completes, collector ingests, API/web serve

## Phase 4: Dependencies

- [x] `pyproject.toml`
  - [x] Remove `aiosqlite` from `dependencies`
  - [x] Move `asyncpg>=0.28.0` and `psycopg2-binary>=2.9.0` into `dependencies`
  - [x] Keep `[postgres]` as an empty alias extra with deprecation comment ("no-op — drivers are core since v0.19; removed in v0.20")
  - [x] Update the `[dev]` comment about the "dual-backend test suite"
- [x] Refresh `.venv` (`pip install -e ".[dev]"`) and confirm nothing imports `aiosqlite`
- [x] **Gate 4**: full suite + `pre-commit run --all-files` green

## Phase 5: Documentation & upgrade story

- [x] `docs/upgrading.md` — new v0.19 section: breaking-change notice, in-place runbook (backup → stop writers → bring up Postgres → `db migrate-to-postgres` → restart), `DATABASE_BACKEND=sqlite` rejection behaviour, bundled default password (production must override), v0.20 removal schedule (migration command, `database_backend` field, `[postgres]` extra)
- [x] `docs/database.md` — Postgres-only reference: remove "SQLite (default)" and backend-choice sections; keep bundled-container setup, managed/external Postgres, schema-per-instance provisioning, migration section repositioned as upgrade guidance
- [x] `docs/configuration.md` — `DATA_HOME` description, `DATABASE_BACKEND` row
- [x] `docs/deployment.md` — remove SQLite caveats
- [x] `docs/seeding.md` — directory tree without `meshcore.db`
- [x] `.env.example` — rewrite Database section: `DATABASE_*` defaults, no SQLite commentary, `DATA_HOME` comment without the db file
- [x] `README.md` — replace deprecation notice with "PostgreSQL-only" statement; update doc-tree descriptions
- [x] `AGENTS.md` — rewrite "Database & Ops" (bundled Postgres default; migration authoring against a local PG schema instead of `./meshcore.db`) and test commands (`make test-db-up` / `TEST_POSTGRES_URL` required)
- [x] **Gate 5**: docs sweep — grep `sqlite`, `DATA_HOME` + `meshcore.db`, `DATABASE_BACKEND` returns only intentional mentions (historical plans, upgrading.md history, retained tooling)

## Phase 6: Final Verification

- [x] Backend: `pytest -nauto --no-cov` (full suite on Postgres)
- [x] Frontend: `npm run test:frontend`, `npx tsc --noEmit`
- [x] `pre-commit run --all-files`
- [x] E2E toolchain: `npm run typecheck:e2e` + `npx playwright test --config=e2e/playwright.config.ts --list` (collection only)
- [x] Fresh-install proof: against a clean test database, `meshcore-hub db upgrade` from revision zero completes on Postgres
- [ ] User-run: `make build && make up` on the `core` profile; e2e via `make e2e-build && make e2e-up && make e2e-test`

## Follow-ups & Coordination (not part of this implementation)

- [x] Track for v0.20: remove `db migrate-to-postgres` + `common/db_migrate.py` + its tests, the `database_backend` settings field, and the `[postgres]` extra alias (announced in the v0.19 `docs/upgrading.md`)
- [ ] When taskifying `docs/plans/20260705-2306-mesh-link-monitoring` (future session): note its SQLite branches (`sqlite_insert` arm, batch-mode DDL, `SQLITE_MAX_VARIABLE_NUMBER` avoidance) are superseded by this plan — implementation targets Postgres-only
