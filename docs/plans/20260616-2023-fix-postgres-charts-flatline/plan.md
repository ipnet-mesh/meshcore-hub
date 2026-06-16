# Fix flatlined dashboard charts on Postgres

## Summary

After the Postgres migration (`feat/postgres-support`, merged in `1ba3e17`), the activity
charts on the home page and the message-activity and node-count charts on the network page
render as flat zeros. Switching `DATABASE_BACKEND` back to `sqlite` makes them work again,
which pinpoints the regression to a dialect-specific code path rather than missing data.

The three affected endpoints — `GET /api/v1/dashboard/activity`,
`GET /api/v1/dashboard/message-activity`, and `GET /api/v1/dashboard/node-count` — all group
rows with `func.date(<timestamp_column>)` and then look the result up by a `"%Y-%m-%d"`
string. On SQLite `func.date()` returns a Python `str`; on Postgres it returns a
`datetime.date` object. The dict built from the result rows is therefore keyed by a different
type than the string used for lookup, so every `.get(date_str, 0)` returns the `0` default and
the chart flatlines — even though the underlying query returns the correct rows.

The fix is a **single, dialect-neutral code path** that runs unchanged on both SQLite and
Postgres: keep `func.date()` uniformly and coerce the returned key to a canonical string in
Python, then guarantee the Postgres session is UTC so the day boundary matches SQLite's UTC-text
truncation. No `if dialect == ...` branches in the query layer — both backends execute the same
SQL and the same normalization. This is paired with the regression coverage the Postgres
migration plan promised but never delivered: a SQLite + Postgres test matrix that asserts the
dashboard endpoints return identical results on both backends.

## Background & Motivation

The Postgres migration (`docs/plans/20260613-2111-postgres-migration/plan.md`) shipped in
`1ba3e17` and was followed by `a554e09` (revert to Postgres 17) and `8bf4536` (node-list
NULLs-last fix). The migration plan was explicit that **Phase 3, Gate 3** would "wire a SQLite
+ Postgres test matrix here so both run going forward." That matrix was never implemented:
`tests/test_api/conftest.py:56` hard-codes `sqlite:///{test_db_path}`, and every dashboard
test (`tests/test_api/test_dashboard.py`) runs only against SQLite. On SQLite,
`func.date()` returns the expected `"%Y-%m-%d"` string, so the dict lookups succeed and all
tests pass — the bug is invisible to the suite.

The dashboard route file (`src/meshcore_hub/api/routes/dashboard.py`) uses `func.date()` in
three places:

| Line | Endpoint | Chart |
|------|----------|-------|
| 296  | `get_activity`        | Home page advert activity |
| 356  | `get_message_activity`| Network page message activity |
| 428  | `get_node_count_history` | Network page cumulative node count (also `new_by_date` at L435) |

All three follow the identical pattern:

```python
date_expr = func.date(Advertisement.received_at)          # SQLite: str, PG: date obj
...
counts_by_date = {row.date: row.count for row in results} # dict keyed by whatever DB returns
...
date_str = date.strftime("%Y-%m-%d")                      # always str
count = counts_by_date.get(date_str, 0)                   # str lookup vs. date-obj key -> always 0 on PG
```

The query itself is valid on both dialects (Postgres resolves `date(col)` to the timestamp→date
cast function), so there is no error — the rows come back, the cache layer (`@cached(...)` on
each endpoint) happily caches the all-zero response, and the chart renders zeros. This is why
the symptom is "flatlined at 0" rather than a 500.

A secondary, latent concern: on Postgres `func.date(<timestamptz>)` truncates to the *session*
timezone's date. The collector writes UTC (`utc_now()`), so if the connection's `timezone`
setting ever drifts from UTC the bucket boundaries would shift. This plan addresses it as part
of the fix by making the bucket UTC-explicit.

## Goals
- Restore correct chart data on Postgres for `/dashboard/activity`,
  `/dashboard/message-activity`, and `/dashboard/node-count` (home + network pages).
- **Make both backends behave identically**: the dashboard endpoints must return the same
  buckets for the same seed data on SQLite and Postgres, driven by one shared code path with
  no per-dialect branches in the query layer.
- Add regression coverage by parameterizing the full API test suite to support **both** SQLite
  and Postgres backends — closing the gap the migration plan's Gate 3 left open — so the two
  backends can be tested manually against the same suite. Postgres testing is run locally, not
  in CI.
- Confirm the cached layer (`@cached`) does not serve stale all-zero responses after the fix
  (verified: the default dashboard TTL is 30 seconds, so stale entries expire before anyone
  notices post-deploy).

## Non-Goals
- Redesigning the dashboard endpoints or their response schemas.
- Introducing a per-dialect query branch (e.g. `func.to_char(...)` on Postgres vs
  `func.date()` on SQLite) — the fix must be one code path on both backends.
- Changing what timezone the *collector* writes (it already writes UTC).
- Revisiting the multi-instance `search_path` / schema work from the migration plan.
- Migrating any other SQLite-specific call sites beyond what the charts need (a separate audit
  can follow; `event_observer.py` already has its dialect-aware upsert).
- Frontend changes — the SPA (`charts.js`) consumes the same JSON shape and needs no edits.
- Adding a CI Postgres test matrix job — Postgres backend testing is manual/local only.

## Requirements

### Functional Requirements
- `/dashboard/activity`, `/dashboard/message-activity`, and `/dashboard/node-count` return the
  same non-zero day buckets on Postgres as they do on SQLite for identical data.
- **Cross-backend equivalence:** for the same seed rows, the three endpoints must return
  byte-for-byte identical JSON on SQLite and Postgres. The fix is unified, not a per-backend
  special case that happens to agree.
- Behavior on SQLite is unchanged (no regression for the default zero-config backend).
- No explicit cache-invalidation step is required for the default 30-second dashboard TTL;
  operators who have configured a substantially longer `REDIS_CACHE_TTL_DASHBOARD` should
  be documented in the upgrade notes as needing to wait one TTL or flush the three
  dashboard key prefixes.

### Technical Requirements
- **One unified code path, not two.** The date-bucketing logic must be identical on SQLite and
  Postgres: a single `func.date(col)` SQL construct and a single Python-side key coercion. No
  `dialect.name == "postgresql"` / `dialect.name == "sqlite"` branch in `dashboard.py` (the
  `event_observer.py:144-152` upsert branch is the *only* dialect fork that should exist, and
  only because there is no truly portable equivalent).
- Date keys must be normalized to a canonical `"%Y-%m-%d"` string **before** being used as dict
  keys, independent of the DB driver's return type. The normalization must handle both `str`
  (SQLite) and `datetime.date`/`datetime.datetime` (Postgres) inputs.
- **Postgres session timezone must be UTC** so `func.date(<timestamptz>)` truncates to the UTC
  day boundary — matching SQLite, which stores UTC text and truncates to the date portion. Set
  this once per connection at the engine level (psycopg2 `connect_args["options"]` +
  `-ctimezone=UTC` for the sync engine, `server_settings={"timezone": "UTC"}` for asyncpg),
  not per-query. This is the single infra-level guarantee that lets the query layer stay
  dialect-agnostic.
- The fix must not change the SQL semantics on SQLite (string-grouping via `func.date()` stays).
- A regression test must assert at least one bucket has `count >= 1` for each endpoint and must
  run against **both** SQLite and Postgres (parameterized fixture / test matrix), asserting the
  two backends return the same buckets for the same seed rows.
- Tests must clear or bypass the Redis cache layer so they assert the query, not the cache.

## Implementation Plan

### Phase 1: Confirm root cause against a live Postgres
- Spin up a throwaway Postgres (`postgres:17-alpine`, port `55432`), `db upgrade`, copy a slice
  of recent `advertisements`/`messages`/`nodes` from `data/collector/meshcore.db` via the
  existing `db migrate-to-postgres` command (or a trimmed manual insert).
- Hit the three endpoints and confirm zeros; run the raw `func.date()` `GROUP BY` query by
  hand and observe that rows come back with `date` objects.
- This step is verification only — it produces no code.

### Phase 2: Unified date-key fix (single code path for both backends)
- Add a small helper in `src/meshcore_hub/api/routes/dashboard.py` (module-private, e.g.
  `_date_bucket_key(value) -> str`) that coerces any DB-returned value to a
  `"%Y-%m-%d"` string: pass through `str` unchanged, call `.strftime("%Y-%m-%d")` on
  `date`/`datetime`, return `None` unchanged (shouldn't happen for the types the DB
  drivers return, but the companion `None` key won't collide with any `date_str` lookup),
  and leave everything else alone. (One-line isinstance ladder.)
- Apply it when building `counts_by_date` / `new_by_date` in all three endpoints
  (`dashboard.py:313`, `:377`, `:435`): `{_date_bucket_key(row.date): row.count ...}`.
  At L435 (the `node-count` `per_day_query`), the existing code uses `row[0]: row[1]` index
  access; switch it to `row.date: row.count` (the query already labels the columns
  `.label("date")` / `.label("count")`) so all three endpoints follow the same named-access
  pattern. The lookup side (`counts_by_date.get(date_str, 0)` / `new_by_date.get(date_str, 0)`)
  is already string-based and needs no change.
- **Keep `func.date(col)` uniformly on both dialects** — do not introduce a Postgres
  `func.to_char(...)` branch. The two backends emit slightly different SQL for `func.date()`
  (SQLite's scalar function vs. Postgres' timestamp→date cast), but SQLAlchemy's `func.date()`
  compiles correctly on both, and the result-row normalization above makes the Python-side key
  identical either way. This is the "both backends work the same" guarantee: one query
  construct, one coercion, no branch.
- **Pin the Postgres session timezone to UTC** at engine creation in
  `src/meshcore_hub/common/database.py` (alongside the existing SQLite `PRAGMA` block, which is
  already dialect-guarded). For the sync engine (psycopg2): append `-ctimezone=UTC` to the
  `connect_args["options"]` string (alongside the existing `search_path` `-c` flag; the
  timezone flag must be set unconditionally for all Postgres connections, not gated on
  `resolved_schema` — a test Postgres engine without a custom schema still needs UTC). For the
  async engine (asyncpg): add `"timezone": "UTC"` to the `server_settings` dict (the same
  mechanism already used for `search_path` at `database.py:201`; similarly set it
  unconditionally, not only when a schema is present). SQLite needs nothing — it has
  no session timezone and already stores UTC text. This single connection-level guarantee makes
  `func.date(<timestamptz>)` truncate on the UTC day boundary exactly as SQLite does, so the
  two backends bucket identically.
- No schema migration, no model change, no Alembic revision.

> **Why not a dialect branch (rejected):** `func.to_char(col.op('AT TIME ZONE')('UTC'),
> 'YYYY-MM-DD')` on Postgres would return a string directly and sidestep the coercion, but it
> requires a `dialect.name` fork in `dashboard.py` and diverges the two code paths. The
> requirement is that both backends *work the same*, so the unified `func.date()` + Python
> coercion + UTC-session approach is preferred; the helper is kept as a defensive guard for any
> future driver that returns a non-string.

### Phase 3: Regression tests + the missing SQLite/Postgres matrix
- Parameterize the full API test suite (`tests/test_api/`) to run against both SQLite and
  Postgres. Scope: every API endpoint, not just the dashboard — any endpoint calling
  `func.date()` or similar SQLAlchemy constructs could have a latent dialect type mismatch.
- Factor the database engine fixture in `tests/test_api/conftest.py` so the backend is
  selected by a fixture param (or an env var such as `TEST_DATABASE_BACKEND`), defaulting to
  SQLite so the local `make test` loop is unchanged. When Postgres is requested, build the URL
  from the same `DATABASE_*` env vars used in production (or a dedicated `TEST_POSTGRES_URL`).
  Postgres runs are manual (spin up a local `postgres:17-alpine`, set the env var, run pytest);
  no CI job is added.
- Ensure the dashboard-specific tests assert the two backends return the same buckets for the
  same seed rows (cross-backend equivalence check).
- The test suite already bypasses Redis: the `@cached` decorator checks
  `request.app.state.redis_cache` which is `None` in the test `create_app()` (no Redis
  configured), falling through to the raw handler. No action needed.

### Phase 4: Live verification

- Bring the stack up on the `postgres` profile against a real dataset and confirm the three
  charts render non-zero buckets matching the SQLite baseline.
- No cache-invalidation step is required: the default `REDIS_CACHE_TTL_DASHBOARD` is 30
  seconds (`config.py:314` → `app.py:93`), so stale all-zero cached responses expire before
  anyone views the dashboard post-deploy. If the operator has set a substantially longer TTL,
  document the one-TTL wait in the upgrade notes.
- Spot-check a known-busy day against a raw `SELECT date(...), count(*) ...` to confirm the
  rendered value matches.

## Open Questions

- **UTC-session application:** set `timezone=UTC` on all engines — API, collector, migrate,
  and the `db migrate-to-postgres` one-shots — via the shared `create_database_engine()` and
  `DatabaseManager.__init__()` so there is one place that could be wrong. This gives the
  migration copy a consistent day boundary with the runtime queries. Resolved: apply
  everywhere.

## References
- `docs/plans/20260613-2111-postgres-migration/plan.md` — the migration that introduced the
  regression; its Phase 3 Gate 3 promised the SQLite+Postgres test matrix this plan delivers.
- `src/meshcore_hub/api/routes/dashboard.py:296,356,428,435` — the `func.date()` call sites and
  dict-key mismatch.
- `tests/test_api/conftest.py:56` — SQLite-only test engine that hid the bug.
- `tests/test_api/test_dashboard.py` — existing dashboard tests (all SQLite-only today).
- `src/meshcore_hub/common/models/event_observer.py:144-152` — the existing dialect-aware
  upsert pattern; noted as the *only* dialect fork that should exist in the codebase (no truly
  portable SQL equivalent), and explicitly not mirrored by this fix.
- Git: `1ba3e17` (merge of `feat/postgres-support`), `a554e09` (revert to PG 17),
  `34410de` (Postgres 18 → 17 revert merge).

## Review

**Status**: Approved

**Reviewed**: 2026-06-16

### Resolutions

- **Test matrix scope** — Parameterize the **full API test suite** to support both SQLite and
  Postgres backends, not just the dashboard tests. Any endpoint using SQLAlchemy constructs could
  have a latent dialect type mismatch; surfacing it all at once is cheaper than chasing
  one-by-one regression bugs. Postgres testing is run manually (local container), not in CI.

- **Cache invalidation** — No explicit cache flush needed. The default dashboard TTL is 30
  seconds (`config.py:314`, `app.py:93`); stale all-zero cached responses expire before a
  user loads the dashboard post-deploy. For operators with a substantially longer
  `REDIS_CACHE_TTL_DASHBOARD`, document the one-TTL wait in the upgrade notes.

- **UTC-session application** — Apply `timezone=UTC` on **all** engines (API, collector,
  migrate, `db migrate-to-postgres`) via the shared `create_database_engine()` and
  `DatabaseManager.__init__()` helpers, so there is a single point of control.

- **_date_bucket_key type coverage** — Handle `None` by returning it unchanged (no
  collision with string lookups). Clarified in the plan.

- **asyncpg timezone mechanism** — Use `server_settings={"timezone": "UTC"}` in asyncpg's
  `connect_args`, matching the existing `search_path` pattern at `database.py:201`, rather
  than a separate connect-event listener.

- **Postgres timezone not gated on schema** — The `-ctimezone=UTC` flag must be set
  unconditionally for all Postgres connections in `create_database_engine()`, not gated on
  `resolved_schema` being non-empty (a Postgres test engine without a custom schema still
  needs UTC).

- **node-count endpoint row access** — L435 (`dashboard.py`) uses `row[0]` index access
  while L313/L377 use `row.date` named access. The fix will switch L435 to named access
  (`row.date`, `row.count`) for consistency across all three endpoints.

### Remaining Action Items

- For deployments with a non-default (long) `REDIS_CACHE_TTL_DASHBOARD`, add a one-TTL
  wait note to `docs/upgrading.md`.
