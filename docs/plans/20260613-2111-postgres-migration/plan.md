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
extra system dependency for operators); connection config uses **component env vars
assembled into a URL**; and the backend is selected by an **explicit `DATABASE_BACKEND`
switch** (`sqlite` default | `postgres`) that fails fast when set to `postgres` without the
required component vars — rather than silently falling back to SQLite. An explicit
`DATABASE_URL`, if set, still overrides everything (managed/external PG, tests). pgloader is
*not* used — see "Why not pgloader" below.

SQLite remains the **zero-config default**: a deployment with no DB env vars behaves exactly
as today. Postgres is opt-in and requires agreement across **two layers** — the app
(`DATABASE_BACKEND=postgres` + component vars) and the infra (the compose `postgres`
profile must be activated). The explicit switch makes a half-configured state fail loudly at
startup instead of silently using the wrong database.

Two further decisions (detailed in Parts B and C):
- **Multi-instance isolation via Postgres schemas.** Production runs several Hub instances
  (prod, stg, …) against one shared Postgres; each is scoped to its own schema
  (`DATABASE_SCHEMA`, default `meshcorehub`) via `search_path`, with its own
  `alembic_version` for independent migration state. Defaults for database/schema/role are
  all `meshcorehub`.
- **No admin/bootstrap credentials.** The app never holds cluster-admin creds; provisioning
  is automatic on the bundled container (image entrypoint) and out-of-band for managed
  Postgres (IaC/console/DBA). No `POSTGRES_ADMIN_*`.

### Why not pgloader
pgloader would infer the target schema from SQLite's *dynamic* typing and produce wrong
Postgres types: `is_observer` (stored `0/1`) → `bigint` not `boolean`; `decoded` JSON
(stored as `TEXT`) → `text` not `json`; `DateTime(timezone=True)` values (stored as text)
→ no `timestamptz`; `String(64)` length constraints lost; and no `alembic_version`
consistent with our migration history. The ORM copy script reuses the existing models, so
SQLAlchemy performs every type conversion correctly and the schema is created by
`alembic upgrade head`.

---

## Implementation order

Parts map to phases. The throughline: **only Phases 1–2 touch shared code and can regress
SQLite, so each ends in a SQLite gate; Phases 3–5 are additive and Postgres-only.** Reach
"Postgres-ready code + verified SQLite" at the end of Phase 2 before committing to the
heavier container/migration work.

- **Phase 1 — Code compatibility (Part A).** The four dialect-neutral fixes (upsert, async
  URL mapping, generic `JSON`, conditional `render_as_batch`).
  - **Gate 1 (SQLite):** full existing test suite green on SQLite + fresh `db upgrade` from
    scratch on a new SQLite file. These changes are behaviour-neutral, so any breakage is
    isolated to these four edits — easy to bisect.
- **Phase 2 — Backend switch + config (Part B).** `DATABASE_BACKEND`, the `DATABASE_*`
  vars, `search_path` wiring, `version_table_schema`.
  - **Gate 2 (SQLite — the key checkpoint):** re-run full suite; add a test asserting the
    **default no-env path resolves to the exact same SQLite URL/behaviour as before** (no
    schema/search_path logic engaged when `DATABASE_BACKEND` unset). *Milestone: code is
    Postgres-compatible and SQLite is proven untouched.*
- **Phase 3 — Postgres container (Part C).** Service, `DATABASE_* → POSTGRES_*` derivation,
  `initdb.d` schema script, profile, healthcheck. Pure infra; cannot regress SQLite.
  - **Gate 3 (Postgres):** bring container up, `db upgrade` against it (tables land in the
    schema, `alembic_version` stamped), run the existing suite against Postgres. Wire a
    **SQLite + Postgres test matrix** here so both run going forward.
- **Phase 4 — Data migration command (Part D).** New Postgres-only code path; zero SQLite risk.
  - **Gate 4:** round-trip the real dev DB (`data/collector/meshcore.db`) → Postgres,
    reconcile per-table row counts, spot-check a JSON/bool/timestamp value.
- **Phase 5 — Verification + docs (Part E).** End-to-end stack run on the `postgres`
  profile; `docs/upgrading.md` runbook + `search_path`/provisioning docs.

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

- Add a `database_backend` field to **`CommonSettings`** (env `DATABASE_BACKEND`,
  default `"sqlite"`, validated choice `sqlite | postgres`).
- Add component fields to **`CommonSettings`** (so both inherit), all defaulting to
  `"meshcorehub"` where named: `database_host`, `database_port` (default `5432`),
  `database_name` (the **database**, default `"meshcorehub"`), `database_schema` (the
  **Postgres schema/namespace**, default `"meshcorehub"`), `database_user`
  (default `"meshcorehub"`), `database_password`.
  - `DATABASE_NAME` and `DATABASE_SCHEMA` are **distinct**: the former is the database, the
    latter is the namespace within it. They differ in the shared-cluster case (see
    "Multi-instance isolation" below); for a single instance both are `meshcorehub`.
- Add a shared resolution helper (method on `CommonSettings`, or module function) used by
  both `effective_database_url` properties, with this precedence:
  1. explicit `database_url` if set → use verbatim (escape hatch: managed/external PG, tests);
  2. else if `database_backend == "postgres"` → require `database_host`, `database_name`,
     `database_user`, `database_password` (raise a clear startup error naming any missing
     var — do **not** fall back to SQLite), then assemble
     `postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}` (URL-encode the password);
  3. else (`database_backend == "sqlite"`) → existing SQLite default under `DATA_HOME`.
- Collapse the duplicated `effective_database_url` into the shared helper.

### Multi-instance isolation via Postgres schemas
Production will run **multiple Hub instances (prod, stg, …) against one shared Postgres**.
Isolate them with **schema-per-instance**, not database-per-instance: a shared database with
each instance scoped to its own schema (`DATABASE_SCHEMA`). This reuses the schema var and is
lighter to provision on a shared/managed cluster than many databases. (Database-per-instance
is the heavier alternative — stronger isolation, but more provisioning; not chosen.)

Mechanics (Postgres only — SQLite ignores all of this):
- **Scope every connection to the schema via `search_path`** rather than hardcoding
  `schema=` on the models/metadata (hardcoding would pin the ORM to one schema and break
  SQLite). Set it in `create_database_engine` for Postgres, e.g. psycopg2
  `connect_args={"options": f"-csearch_path={schema}"}` (and the asyncpg equivalent for the
  async engine — a `SET search_path` on connect via an event listener). Models stay
  schema-agnostic; the active schema is chosen entirely by config.
- **Per-instance migration state**: Alembic must place its bookkeeping in the instance's
  schema — pass `version_table_schema=<schema>` in `alembic/env.py` (Postgres only) so each
  instance has its own `alembic_version` and prod/stg can sit on **different revisions
  independently**. `include_schemas=True` for autogenerate. The `search_path` set on the
  connection means `upgrade` creates the tables in the right schema automatically.
- **Schema must exist first**: the app role needs its schema present. Either pre-provisioned
  out-of-band (managed; see Part C) or `CREATE SCHEMA IF NOT EXISTS` on the bundled
  container. The `db migrate-to-postgres` command inherits the same `search_path`, so it
  loads into the instance's schema with no extra flags.

Update `.env.example` with a `DATABASE_BACKEND` line (default `sqlite`) plus the
`DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` / `DATABASE_SCHEMA` / `DATABASE_USER` /
`DATABASE_PASSWORD` block (defaults `meshcorehub`), documented as "set
`DATABASE_BACKEND=postgres` and fill these in to use Postgres; override `DATABASE_SCHEMA`
per instance (e.g. `prod`, `stg`) when sharing one cluster; leave defaults for SQLite."

---

## Part C — Postgres container

In `docker-compose.yml` (mirror the existing `redis` service style, named volume pattern
at lines ~411-419):

- Add a `postgres` service (`postgres:17-alpine`), a named
  `postgres_data:/var/lib/postgresql/data` volume, and a `pg_isready` healthcheck.
  Put it behind a `postgres` compose profile (SQLite stays the zero-config default; the
  container only runs when the profile is activated, e.g. `docker compose --profile postgres up`).
- **Single source of truth for credentials** — derive the container's init vars from the
  app's `DATABASE_*` rather than maintaining a duplicate set:
  ```yaml
  environment:
    POSTGRES_USER:     ${DATABASE_USER:-meshcorehub}
    POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
    POSTGRES_DB:       ${DATABASE_NAME:-meshcorehub}
  ```
  The image entrypoint auto-creates the role + database from these on first init (empty
  volume only). Add a tiny `/docker-entrypoint-initdb.d/` script to also
  `CREATE SCHEMA IF NOT EXISTS "${DATABASE_SCHEMA}" AUTHORIZATION "${DATABASE_USER}"` so the
  bundled path needs no manual SQL.
- Add `DATABASE_*` (including `DATABASE_BACKEND`) to the env passed to `migrate`,
  `collector`, and `api` services.
- **Document the two-layer requirement explicitly**: enabling Postgres = set
  `DATABASE_BACKEND=postgres` + component vars **and** activate the `postgres` profile.
  Compose can't read the app env var to auto-activate its profile, so these stay two
  switches — but the app's fail-fast validation (Part B) turns a half-configured state into
  a clear startup error rather than a silent SQLite fallback.
- Make `migrate` (and therefore `collector`/`api`) `depends_on` postgres `service_healthy`
  when the Postgres profile is active.
- Add the `postgres_data` named volume to the `volumes:` block.
- Mirror into `docker-compose.prod.yml` networking if Postgres should sit on `proxy-net`
  (usually it should stay internal-only — confirm during implementation).

### Provisioning decision: no admin/bootstrap credentials
The app and tooling **never hold cluster-admin credentials**. The only privileged
operations are the one-time `CREATE ROLE` / `CREATE DATABASE` / `CREATE SCHEMA` / `GRANT`;
everything afterwards (Alembic `db upgrade` DDL, runtime DML, the data-migration command)
runs as the least-privileged app role, which only needs to **own its schema/database**, not
superuser. Provisioning is therefore split by environment, and we do **not** add
`POSTGRES_ADMIN_USER/PASSWORD` (handing the app permanent admin creds for a one-time task is
a security regression and not the production pattern):

| Environment | Provisioning of role/db/schema/grants | App holds |
|-------------|----------------------------------------|-----------|
| **Bundled container** (dev / small prod) | Automatic: image entrypoint creates role+db from `POSTGRES_*` (= `DATABASE_*`), init script creates the schema. No admin creds exist or are needed. | `DATABASE_*` |
| **Managed / shared Postgres** (prod, stg) | **Out-of-band** — Terraform/IaC, cloud console, or a DBA runs the SQL once. The platform's master user stays in the infra layer, never in the app. | `DATABASE_*` only |

Managed/shared-cluster provisioning SQL to document in `docs/` (one schema per instance in a
shared database; role must own its schema so `db upgrade` can create tables; **need not be
superuser** — which is why the migration command's `session_replication_role` step has a
documented fallback, Part D):
```sql
-- once per cluster
CREATE ROLE meshcorehub LOGIN PASSWORD '…';
CREATE DATABASE meshcorehub OWNER meshcorehub;
-- connected to the meshcorehub database, once per Hub instance:
CREATE SCHEMA IF NOT EXISTS prod AUTHORIZATION meshcorehub;   -- and stg, etc.
GRANT ALL ON SCHEMA prod TO meshcorehub;
```
Each instance then sets `DATABASE_SCHEMA=prod` / `stg`. A Terraform example is a nice-to-have
follow-up, not required for v1. (Optional future convenience: a `meshcore-hub db bootstrap`
command that accepts admin creds **only as one-shot CLI flags**, never persisted env — out of
scope for v1.)

---

## Part D — Data migration command (`meshcore-hub db migrate-to-postgres`)

Add a new Click command in the `db` group in `src/meshcore_hub/__main__.py` (after
`db_upgrade`, ~line 86), backed by a helper module (e.g.
`src/meshcore_hub/common/db_migrate.py`).

### Command behaviour
- Opens a source `DatabaseManager` (SQLite) and target `DatabaseManager` (Postgres) using
  the existing `create_database_engine` (`database.py:14`).
- **Sensible defaults make the common case zero-flag:** `--source` defaults to the legacy
  SQLite path under `DATA_HOME` (`sqlite:////data/collector/meshcore.db`) regardless of the
  configured backend; `--target` defaults to the configured `effective_database_url`
  (Postgres). Both can be overridden explicitly.
- Verifies the target schema is at `head` and tables are empty (refuse otherwise unless
  `--truncate`) — guards against accidental double-runs. **Non-destructive to the source.**
- **Copies at the SQLAlchemy Core level, table-by-table** — *not* through ORM objects.
  Iterate `Base.metadata.sorted_tables` and for each `Table`, `select(table)` from SQLite
  and `insert(table)` into Postgres reusing the same `Table` object. Type conversion is a
  free side-effect of the dialects' type processors: reading applies the SQLite *result
  processor* per column (`0/1`→`bool`, JSON `TEXT`→`dict`, ISO string→`datetime`), writing
  applies the Postgres *bind processor* (`bool`→`boolean`, `dict`→`json`,
  `datetime`→`timestamptz`, UUID-string→`varchar`). No per-model code, works generically
  for every table. (Core, not ORM, because instances can't be shared across two sessions.)
- `Base.metadata.sorted_tables` gives a **parent-first FK order** (`nodes` → `node_tags`,
  `user_profiles` → `user_profile_nodes`, `event_observers`, event tables, `channels`,
  `events_log`) and naturally **excludes `alembic_version`** (not a mapped model — it was
  already created/stamped by `db upgrade`, so we must not touch it).
- **Streams large tables**: `select(...).execution_options(stream_results=True)` +
  `result.partitions(batch_size)` (~2k) so `raw_packets` doesn't materialize in memory;
  inserts go out via the executemany path.
- **Timezone normalization (the one explicit conversion):** SQLite doesn't persist tz, so
  `DateTime(timezone=True)` values read back as *naive* datetimes; inserting naive values
  into Postgres `timestamptz` would assume the session tz. Since the app always writes UTC
  (`utc_now()`), a small normalize step attaches `tzinfo=UTC` to naive datetimes for
  tz-aware columns before insert.
- **Single target transaction** wrapping the whole copy → all-or-nothing; any failure
  leaves Postgres empty and the operator re-runs. Acceptable given the downtime window.
- **FK enforcement during load** — `sorted_tables` order is normally sufficient (the schema
  has no FK cycles). For robustness the load issues `SET session_replication_role = replica`
  to disable FK triggers, then restores `DEFAULT`. **Caveat: this requires DB-superuser
  privilege**, which the bundled compose `postgres` container has but a *managed* Postgres
  (RDS / Cloud SQL) may not grant. Fallback for managed targets: skip the
  `session_replication_role` toggle and rely solely on `sorted_tables` order (safe here as
  there are no FK cycles). The command should detect the missing privilege and fall back
  gracefully (or expose a `--no-replication-role` flag), and the docs should call this out.
- After load, reconcile — no sequences to fix (all PKs are app-generated UUID strings), but
  log a **per-table source-vs-target row-count comparison** as a built-in check.
- `--dry-run` prints the per-table row counts without writing.

> Reuse `Base.metadata.sorted_tables` and the existing models in
> `src/meshcore_hub/common/models/` — do not redefine schema in the script.

> **Why run it inside the `migrate` service:** the command needs both databases reachable
> at once — the `migrate` service mounts the `data` volume (SQLite source) *and* sits on the
> compose network with `postgres` (target). Hence `docker compose run --rm migrate ...`
> rather than a bare host invocation.

### Operator runbook (docker-compose deployment, downtime acceptable)

Starting state: running on SQLite, data in the `data` volume at `/data/collector/meshcore.db`.

1. **Back up the SQLite database** — this is the rollback path:
   ```bash
   docker compose cp collector:/data/collector/meshcore.db ./meshcore-backup-$(date +%F).db
   ```
2. **Stop the writers** (downtime starts; quiesces the SQLite file):
   ```bash
   docker compose stop collector api web
   ```
3. **Configure Postgres in `.env`** — only the `DATABASE_*` block (the bundled container's
   `POSTGRES_*` init vars derive from these, see Part C):
   ```ini
   DATABASE_BACKEND=postgres
   DATABASE_HOST=postgres
   DATABASE_PORT=5432
   DATABASE_NAME=meshcorehub
   DATABASE_SCHEMA=meshcorehub   # override per instance (prod/stg) on a shared cluster
   DATABASE_USER=meshcorehub
   DATABASE_PASSWORD=<strong-password>   # e.g. openssl rand -base64 32
   ```
4. **Start the Postgres container** and wait for its `pg_isready` healthcheck:
   ```bash
   docker compose --profile postgres up -d postgres
   ```
5. **Create the schema in Postgres** (builds correctly-typed tables + stamps `alembic_version`):
   ```bash
   docker compose --profile postgres run --rm migrate meshcore-hub db upgrade
   ```
6. **Copy the data across** (zero-flag common case; optionally `--dry-run` first):
   ```bash
   docker compose --profile postgres run --rm migrate \
     meshcore-hub db migrate-to-postgres
   ```
   Confirm the per-table reconciliation counts all match.
7. **Bring the stack up against Postgres and verify**:
   ```bash
   docker compose --profile postgres up -d
   docker compose run --rm api meshcore-hub api health
   ```
   Spot-check the web dashboard shows nodes/events. Downtime ends here.
8. **Decommission SQLite (later)** — once confident (a few days), remove the old
   `meshcore.db` from the `data` volume; keep the step-1 backup archived.

**Rollback:** stop the stack, set `DATABASE_BACKEND=sqlite` (or remove it) in `.env`, and
`docker compose up -d` without the `postgres` profile. You're back on the untouched SQLite
file — the migration never mutates the source.

> The implementation should mirror this runbook into `docs/upgrading.md` (Part D
> deliverable).

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
