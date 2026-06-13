# Plan: Add PostgreSQL support and migrate existing SQLite databases

## Context

`meshcore-hub` currently runs on SQLite (`sqlite:///{DATA_HOME}/collector/meshcore.db`).
SQLite WAL does not work over network filesystems and limits concurrent writers, so it
caps the project at a single host — the README already flags switching to Postgres for
multi-host scaling. The goal is to (1) make the codebase genuinely Postgres-compatible,
(2) add a Postgres container and component-based connection config, and (3) give existing
community operators a one-command path to migrate their live SQLite data into Postgres
(downtime is acceptable).

The stack is already mostly ready: SQLAlchemy 2.0 + Alembic, `asyncpg`/`psycopg2-binary`
declared as the `[postgres]` optional dependency in `pyproject.toml`, and `DATABASE_URL`
threaded through `config.py` and `alembic/env.py`. The work is closing the SQLite-specific
gaps and adding the container + migration tooling.

**Decisions made:** data migration uses a **SQLAlchemy ORM copy script** (type-safe, no
extra system dependency for operators), and connection config uses **component env vars
assembled into a URL** (with explicit `DATABASE_URL` still taking precedence). pgloader is
*not* used — see "Why not pgloader" below.

### Why not pgloader
pgloader would infer the target schema from SQLite's *dynamic* typing and produce wrong
Postgres types: `is_observer` (stored `0/1`) → `bigint` not `boolean`; `decoded` JSON
(stored as `TEXT`) → `text` not `json`; `DateTime(timezone=True)` values (stored as text)
→ no `timestamptz`; `String(64)` length constraints lost; and no `alembic_version`
consistent with our migration history. The ORM copy script reuses the existing models, so
SQLAlchemy performs every type conversion correctly and the schema is created by
`alembic upgrade head`.

---

## Part A — Make the code Postgres-compatible (required regardless of migration tool)

These are real runtime bugs on Postgres, not cosmetics.

1. **Dialect-aware upsert** — `src/meshcore_hub/common/models/event_observer.py:17,125-139`
   `add_event_observer()` is live collector code and currently uses
   `from sqlalchemy.dialects.sqlite import insert as sqlite_insert` +
   `.on_conflict_do_nothing(...)`. On Postgres this emits invalid SQL.
   Fix: pick the insert construct by bind dialect, e.g.
   ```python
   if session.bind.dialect.name == "postgresql":
       from sqlalchemy.dialects.postgresql import insert as pg_insert
       stmt = pg_insert(EventObserver).values(...).on_conflict_do_nothing(
           index_elements=["event_hash", "observer_node_id"])
   else:
       from sqlalchemy.dialects.sqlite import insert as sqlite_insert
       stmt = sqlite_insert(EventObserver).values(...).on_conflict_do_nothing(...)
   ```
   Both dialects expose the same `.on_conflict_do_nothing(index_elements=...)` API, so only
   the import/constructor differs. Grep for other `dialects.sqlite import insert` usages.

2. **Async driver mapping** — `src/meshcore_hub/common/database.py:145`
   `_ensure_async_engine()` only rewrites `sqlite://` → `sqlite+aiosqlite://`. A
   `postgresql://` URL keeps the sync `psycopg2` driver and async API sessions fail.
   Fix: map `postgresql://` / `postgres://` → `postgresql+asyncpg://` (leave an already
   `+driver`-qualified URL untouched). Add a small helper (e.g. `_to_async_url(url)`) used
   here.

3. **Generic JSON type** — 4 models import `from sqlalchemy.dialects.sqlite import JSON`:
   `models/raw_packet.py:7`, `models/telemetry.py`, `models/trace_path.py`,
   `models/event_log.py`. Switch to generic `from sqlalchemy import JSON`. Generic `JSON`
   maps to SQLite JSON and Postgres `JSON` automatically. (Optional: use
   `postgresql.JSONB` via `.with_variant()` for indexability — not required for parity.)

4. **Conditional batch migrations** — `alembic/env.py:61,87`
   `render_as_batch=True` is unconditional (it's a SQLite ALTER-TABLE workaround). Make it
   `render_as_batch = get_database_url().startswith("sqlite")` in both
   `run_migrations_offline()` and `run_migrations_online()`. Existing migrations that call
   `op.batch_alter_table(...)` still run correctly on Postgres (Alembic emits direct
   `ALTER` there), and a fresh Postgres DB runs the whole history from scratch.

> The SQLite `PRAGMA` block in `database.py:52-65,150-161` is already guarded by
> `startswith("sqlite")` — no change needed.

**Verification for Part A:** run the existing test suite against Postgres (see Part E).

---

## Part B — Component-based connection config

Centralize config in `src/meshcore_hub/common/config.py`. `CollectorSettings` and
`APISettings` currently each carry `database_url` + a duplicated `effective_database_url`
property (`config.py:72-75,174-182` and the matching block in `APISettings`).

- Add component fields to **`CommonSettings`** (so both inherit): `database_host`,
  `database_port` (default `5432`), `database_name`, `database_user`, `database_password`.
  (`DATABASE_NAME` is the user's "DATABASE_SCHEMA".)
- Add a shared resolution helper (method on `CommonSettings`, or module function) used by
  both `effective_database_url` properties, with this precedence:
  1. explicit `database_url` if set → use verbatim (keeps existing SQLite/`DATABASE_URL`
     deployments working unchanged);
  2. else if `database_host` is set → assemble
     `postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}`
     (URL-encode the password);
  3. else → existing SQLite default under `DATA_HOME`.
- Collapse the duplicated `effective_database_url` into the shared helper.

Update `.env.example` with the new `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` /
`DATABASE_USER` / `DATABASE_PASSWORD` block, documented as "set these for Postgres; leave
unset for default SQLite."

---

## Part C — Postgres container

In `docker-compose.yml` (mirror the existing `redis` service style, named volume pattern
at lines ~411-419):

- Add a `postgres` service (`postgres:17-alpine`), env from `POSTGRES_USER`/
  `POSTGRES_PASSWORD`/`POSTGRES_DB` (sourced from the same `.env` values), a named
  `postgres_data:/var/lib/postgresql/data` volume, and a `pg_isready` healthcheck.
  Put it behind a `postgres` profile (consistent with optional services) or core depending
  on whether Postgres becomes the default — recommend keeping SQLite the zero-config
  default and Postgres opt-in via profile + env.
- Add `DATABASE_*` to the env passed to `migrate`, `collector`, and `api` services.
- Make `migrate` (and therefore `collector`/`api`) `depends_on` postgres `service_healthy`
  when the Postgres profile is active.
- Add the `postgres_data` named volume to the `volumes:` block.
- Mirror into `docker-compose.prod.yml` networking if Postgres should sit on `proxy-net`
  (usually it should stay internal-only — confirm during implementation).

---

## Part D — Data migration command (`meshcore-hub db migrate-to-postgres`)

Add a new Click command in the `db` group in `src/meshcore_hub/__main__.py` (after
`db_upgrade`, ~line 86), backed by a helper module (e.g.
`src/meshcore_hub/common/db_migrate.py`).

Operator flow (downtime acceptable):
1. Stop `collector`/`api` (writers).
2. Bring up the `postgres` container.
3. Run `meshcore-hub db upgrade` with the Postgres `DATABASE_URL` → creates schema +
   stamps `alembic_version`.
4. Run `meshcore-hub db migrate-to-postgres --source sqlite:///...meshcore.db --target <pg url>`.

The command:
- Opens a source `DatabaseManager` (SQLite) and target `DatabaseManager` (Postgres) using
  the existing `create_database_engine` (`database.py:14`).
- Verifies the target schema is at `head` and tables are empty (refuse otherwise unless
  `--truncate`).
- Copies every table in **FK-dependency order** (`nodes` → `node_tags`,
  `user_profiles` → `user_profile_nodes`, `event_observers`, then event tables
  `messages`/`advertisements`/`telemetry`/`trace_paths`/`raw_packets`, `channels`,
  `events_log`). Derive order from `Base.metadata.sorted_tables` to avoid hardcoding.
- Reads source rows via the ORM models / `select()` and bulk-inserts into the target in
  batches (e.g. 1–5k rows), reusing the model classes so SQLAlchemy converts
  bool/JSON/`timestamptz`/UUID-strings correctly. Use a single target transaction per
  table (or per batch) and report per-table counts.
- After load, reconcile Postgres — no sequences to fix (all PKs are app-generated UUID
  strings), but log a row-count comparison source-vs-target per table as a built-in check.
- `--dry-run` prints the per-table row counts without writing.

> Reuse `Base.metadata.sorted_tables` and the existing models in
> `src/meshcore_hub/common/models/` — do not redefine schema in the script.

---

## Part E — Verification

1. **Unit/integration tests on Postgres.** Spin up a throwaway Postgres
   (`docker run --rm -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17-alpine`), export
   the matching `DATABASE_*`, run `meshcore-hub db upgrade`, then the existing test suite
   pointed at Postgres. Confirms Part A (esp. the `event_observer` upsert and async API
   sessions) and the migration chain build cleanly on Postgres.
2. **Round-trip data migration.** Use the real dev DB at
   `data/collector/meshcore.db` (or `backup/meshcore.db`) as source. Run `db upgrade` +
   `db migrate-to-postgres`, then assert per-table row counts match (the command's built-in
   reconciliation), and spot-check a `raw_packets.decoded` JSON value, an `is_observer`
   boolean, and a `received_at` timestamp survived with correct types.
3. **End-to-end app run.** Bring up the stack with the `postgres` profile + `DATABASE_*`
   set, confirm `migrate` completes, `collector` ingests an event (exercises
   `add_event_observer` upsert on Postgres), and the `api`/`web` serve data
   (`meshcore-hub api health`).

---

## Critical files

| File | Change |
|------|--------|
| `src/meshcore_hub/common/models/event_observer.py` | Dialect-aware upsert (A1) |
| `src/meshcore_hub/common/database.py` | Async driver mapping for Postgres (A2) |
| `src/meshcore_hub/common/models/{raw_packet,telemetry,trace_path,event_log}.py` | Generic `JSON` import (A3) |
| `alembic/env.py` | Conditional `render_as_batch` (A4) |
| `src/meshcore_hub/common/config.py` | Component DATABASE_* vars + shared URL assembly (B) |
| `.env.example` | Document new DATABASE_* vars (B) |
| `docker-compose.yml` (+ `.prod.yml`) | `postgres` service, volume, depends_on, env (C) |
| `src/meshcore_hub/__main__.py` + new `common/db_migrate.py` | `db migrate-to-postgres` command (D) |
| `README.md` / `docs/upgrading.md` | Document Postgres setup + migration procedure |

## Out of scope / notes
- Keep SQLite as the zero-config default; Postgres is opt-in. No forced migration.
- No schema redesign — all column types already map cleanly once A1–A4 land.
- Consider gating CI to run the suite against both SQLite and Postgres (follow-up).
