# Tasks: Fix flatlined dashboard charts on Postgres

> Generated from `plan.md` on 2026-06-16

## 1. Postgres UTC Session Configuration

- [x] **1.1** Add unconditional `-ctimezone=UTC` to the sync engine in `create_database_engine()` (`database.py:65-94`)
  - [x] In the Postgres branch (after the SQLite `check_same_thread` guard, near L76), ensure `connect_args["options"]` always includes `-ctimezone=UTC` — even when `resolved_schema` is empty
  - [x] When `resolved_schema` is set, combine both flags: `-csearch_path=<schema> -ctimezone=UTC`
  - [x] When `resolved_schema` is empty/None, set `connect_args["options"] = "-ctimezone=UTC"` alone
  - [x] Gate the entire block on `database_url` being Postgres (not SQLite) — mirror the existing `database_url.startswith("sqlite")` pattern
- [x] **1.2** Add unconditional `"timezone": "UTC"` to the async engine in `DatabaseManager._ensure_async_engine()` (`database.py:188-204`)
  - [x] Ensure `async_connect_args["server_settings"]` always includes `"timezone": "UTC"` for Postgres
  - [x] When `self._schema` is set, merge into one `server_settings` dict: `{"search_path": schema, "timezone": "UTC"}`
  - [x] When `self._schema` is None (Postgres without custom schema), still create `server_settings = {"timezone": "UTC"}`
  - [x] Only apply for Postgres URLs, not SQLite (SQLite async engine has no `server_settings`)
- [x] **1.3** Add unit tests verifying UTC timezone is configured on Postgres engines
  - [x] Test that `create_database_engine()` with a `postgresql://` URL sets `connect_args["options"]` containing `-ctimezone=UTC`
  - [x] Test that `create_database_engine()` with a Postgres URL + schema sets both `-csearch_path=` and `-ctimezone=UTC` in options
  - [x] Test that `create_database_engine()` with a `sqlite://` URL does NOT set timezone options
  - [x] Test that `DatabaseManager` async engine has `server_settings` with `"timezone": "UTC"` for Postgres URLs

## 2. Unified Date-Key Normalization

- [x] **2.1** Add `_date_bucket_key(value) -> str | None` helper in `src/meshcore_hub/api/routes/dashboard.py`
  - [x] Return `value` unchanged if it's already a `str`
  - [x] Return `value.strftime("%Y-%m-%d")` if it's a `datetime.date` or `datetime.datetime`
  - [x] Return `None` unchanged if `value is None` (won't collide with string lookups)
  - [x] Use a single `isinstance` ladder — no dialect check
  - [x] Add module-level `from datetime import date as date_type, datetime as datetime_type` imports if needed (or import `datetime` already present)
- [x] **2.2** Apply `_date_bucket_key` to `get_activity` endpoint (`dashboard.py:313`)
  - [x] Change `{row.date: row.count for row in results}` to `{_date_bucket_key(row.date): row.count for row in results}`
  - [x] Update the comment on L312 from "date is already a string" to reflect the normalization
- [x] **2.3** Apply `_date_bucket_key` to `get_message_activity` endpoint (`dashboard.py:377`)
  - [x] Change `{row.date: row.count for row in results}` to `{_date_bucket_key(row.date): row.count for row in results}`
- [x] **2.4** Apply `_date_bucket_key` to `get_node_count_history` endpoint (`dashboard.py:435-436`)
  - [x] Switch from index access `row[0]: row[1]` to named access: `{_date_bucket_key(row.date): row.count for row in session.execute(per_day_query).all()}`
  - [x] The query already labels columns `.label("date")` and `.label("count")` (L430), so named access works
- [x] **2.5** Add unit tests for `_date_bucket_key` helper
  - [x] Test with a `str` input (e.g. `"2026-06-15"`) — returns unchanged
  - [x] Test with a `datetime.date` input — returns `"%Y-%m-%d"` string
  - [x] Test with a `datetime.datetime` input — returns `"%Y-%m-%d"` string
  - [x] Test with `None` — returns `None`
  - [x] Test that `datetime.date(2026, 1, 5)` produces `"2026-01-05"` (zero-padded)

## 3. Dual-Backend Test Infrastructure

- [x] **3.1** Add backend-selection mechanism to `tests/test_api/conftest.py`
  - [x] Add a `TEST_DATABASE_BACKEND` env var check (or `TEST_POSTGRES_URL`), defaulting to `sqlite` so local `make test` is unchanged
  - [x] Add a session-scoped `db_backend` fixture that reads the env var and returns `"sqlite"` or `"postgres"`
  - [x] Skip Postgres tests if `TEST_DATABASE_BACKEND=postgres` is requested but no Postgres is reachable (use `pytest.fixture` with `pytest.skip()`)
- [x] **3.2** Refactor `api_db_engine` fixture to support both backends (`conftest.py:48-71`)
  - [x] When backend is SQLite: keep existing behavior (temp file, `create_engine`, SQLite pragma)
  - [x] When backend is Postgres: build URL from `TEST_POSTGRES_URL` (or `DATABASE_URL`), use `create_engine` with the same `connect_args` as production (including `-ctimezone=UTC` from `create_database_engine`)
  - [x] Call `Base.metadata.create_all(engine)` in both cases
  - [x] Ensure `Base.metadata.drop_all(engine)` runs on teardown for both backends
- [x] **3.3** Update `mock_db_manager` and app fixtures to use the parameterized engine
  - [x] `mock_db_manager` (`conftest.py:110-132`) — bind `sessionmaker` to whichever engine `api_db_engine` yields
  - [x] `app_no_auth` (`conftest.py:170-186`) — pass the correct `db_url` (SQLite file path or Postgres URL) to `create_app()`
  - [x] `app_with_auth` (`conftest.py:189-199`) — same update
  - [x] `_wire_overrides` (`conftest.py:148-167`) — bind `sessionmaker` to parameterized engine
- [x] **3.4** Ensure `_truncate_all` works on Postgres (`conftest.py:74-78`)
  - [x] Verify `table.delete()` in reversed FK order works on Postgres (it should — same SQLAlchemy construct)
  - [x] If Postgres FK constraints cause issues, consider `TRUNCATE ... CASCADE` as an alternative, but prefer the current approach for backend neutrality
- [x] **3.5** Verify the full existing API test suite passes unchanged on SQLite after refactoring
  - [x] Run `pytest --no-cov tests/test_api/` and confirm no regressions from the fixture changes
  - [x] Confirm `make test` still works identically with no env var set

## 4. Regression & Cross-Backend Tests

- [x] **4.1** Update `tests/test_api/test_dashboard.py` to assert non-zero buckets
  - [x] For `get_activity`: seed advertisements with known UTC dates within the window, assert at least one returned `data[].count >= 1`
  - [x] For `get_message_activity`: seed messages with known UTC dates, assert at least one `count >= 1`
  - [x] For `get_node_count`: seed nodes with `created_at` within the window, assert cumulative count increases (non-zero delta on seeded days)
- [x] **4.2** Add deterministic-date seed fixtures for cross-backend tests
  - [x] Create fixtures that insert rows at explicit UTC timestamps (e.g. `datetime(2026, 6, 10, tzinfo=timezone.utc)`) rather than `datetime.now(timezone.utc)` — so both backends see the same bucket boundaries
  - [x] Ensure seeded timestamps fall within the endpoint's default day window (use `freezegun` or monkeypatch `utc_now` if needed, or seed dates relative to the current date)
- [x] **4.3** Add cross-backend equivalence test for all three dashboard endpoints
  - [x] Create a test that runs against both SQLite and Postgres (via the parameterized fixture)
  - [x] Seed identical data on the active backend
  - [x] Assert the JSON response from each endpoint has the same `data` array (same dates, same counts)
  - [x] This test is the regression guard: if it passes on Postgres, the bug is fixed

## 5. Documentation

- [x] **5.1** Add upgrade note to `docs/upgrading.md` for long-TTL operators
  - [x] Document that the dashboard chart fix takes effect after one `REDIS_CACHE_TTL_DASHBOARD` period (default 30s)
  - [x] For operators with a substantially longer TTL, advise waiting one TTL period or flushing the three dashboard cache key prefixes (`dashboard:activity`, `dashboard:message-activity`, `dashboard:node-count`)

## 6. Verification

- [x] **6.1** Run linting and formatting checks
  - [x] `pre-commit run --all-files`
- [x] **6.2** Run the full test suite on SQLite
  - [x] `pytest -nauto --no-cov` — confirm no regressions (1106 passed, 22 skipped)
- [x] **6.3** Run the full API test suite on Postgres (local, via throwaway container)
  - [x] Spin up `postgres:17-alpine` on port 55432
  - [x] `TEST_DATABASE_BACKEND=postgres TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost:55432/test pytest -nauto --no-cov tests/test_api/`
  - [x] Confirm all tests pass, especially the new dashboard regression tests (458 passed)
- [ ] **6.4** Live verification against the compose stack
  - [ ] Bring the stack up on the Postgres profile with real data (or migrated SQLite data)
  - [ ] Hit `GET /api/v1/dashboard/activity`, `/dashboard/message-activity`, `/dashboard/node-count` — confirm non-zero buckets
  - [ ] Compare against the same endpoints on SQLite — confirm identical results
  - [ ] Spot-check a known-busy day against a raw `SELECT date(...), count(*) ...` query
- [x] **6.5** Verify no `dialect.name` branch was introduced in `dashboard.py`
  - [x] Grep `dashboard.py` for `dialect` — confirm zero hits (the fix is dialect-neutral by construction)
