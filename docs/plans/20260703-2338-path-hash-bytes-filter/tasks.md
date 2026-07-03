# Tasks: Persist & Filter by Path-Hash Byte Width

> Generated from `plan.md` on 2026-07-03

## 1. Model & Migration (Phase 1)

- [x] 1.1 Add `path_hash_bytes` column to `RawPacket` model
  - [x] 1.1.1 Add `Mapped[Optional[int]] = mapped_column(Integer, nullable=True)` after `path_len` in `src/meshcore_hub/common/models/raw_packet.py`
  - [x] 1.1.2 Verify model test reflects new column (presence + default None)

- [x] 1.2 Generate and customize alembic migration
  - [x] 1.2.1 Run `meshcore-hub db revision --autogenerate -m "add path_hash_bytes to raw_packets"` against migration head `38abdf4651fc`
  - [x] 1.2.2 Verify `down_revision` is `38abdf4651fc` in generated file
  - [x] 1.2.3 Append self-contained Python batched backfill loop (~1000 rows/batch):
    - Read `decoded` via Core `select()` on a `sa.Table` declared with a `sa.JSON`-typed column (routes through SQLAlchemy's JSON type adapter → `dict` on both SQLite and Postgres); do **not** use raw `text("SELECT decoded ...")` (bypasses the adapter → driver-dependent deserialization)
    - Inline frozen dual-path extraction: `decoded["path"]` fallback `decoded.get("payload", {}).get("decoded", {}).get("pathHashes")`
    - Normalize with inline `_normalize_hash_list` logic (split on `","`, strip)
    - Compute `max(len(h) // 2 for h in hashes)` for each row
    - `UPDATE raw_packets SET path_hash_bytes = ? WHERE id = ?`
    - Skip NULL decoded rows (leave NULL)
    - No imports of app code
  - [x] 1.2.4 Verify downgrade drops the column
  - [x] 1.2.5 Test migration with `meshcore-hub db upgrade` on both SQLite and Postgres backends

## 2. Collector Ingest (Phase 2)

- [x] 2.1 Add `_path_hash_byte_width` helper
  - [x] 2.1.1 Add module-level `_path_hash_byte_width(hashes: list[str] | None) -> int | None` in `src/meshcore_hub/collector/handlers/raw_packet.py`
  - [x] 2.1.2 Implement as `max(len(h) // 2 for h in hashes) if hashes else None`

- [x] 2.2 Compute `path_hash_bytes` at ingest
  - [x] 2.2.1 In `store_raw_packet`, after `path_len` block (~line 96), extract path hashes from `decoded_packet`:
    - `LetsMeshNormalizer._normalize_hash_list(decoded_packet.get("path"))`
    - Fallback: `_normalize_hash_list(decoded_packet.get("payload", {}).get("decoded", {}).get("pathHashes"))`
  - [x] 2.2.2 Compute `path_hash_bytes = _path_hash_byte_width(hashes)` (None-safe)
  - [x] 2.2.3 Pass `path_hash_bytes=path_hash_bytes` into `RawPacket(...)` kwargs (~line 122)
  - [x] 2.2.4 Verify null-safe: no path / no decoded → `None`

- [x] 2.3 Add collector unit test
  - [x] 2.3.1 Create test in `tests/test_collector/` (or extend existing `test_store_raw_packet`) covering:
    - `decoded.path` with hashes of mixed widths → correct MAX byte-width persisted
    - Trace fallback `decoded.payload.decoded.pathHashes` → correct width
    - No path present → `None`
    - Verify `path_len` persistence test still passes alongside

## 3. API Route (Phase 3)

- [x] 3.1 Add SQL aggregate to group query
  - [x] 3.1.1 In Phase 1 `group_query` select (`src/meshcore_hub/api/routes/packet_groups.py`), add:
    `func.max(RawPacket.path_hash_bytes).label("path_hash_bytes")`
  - [x] 3.1.2 Add `path_hash_bytes: Optional[int] = Query(None, ge=1, le=3)` parameter to route function
  - [x] 3.1.3 Apply `HAVING` filter: `if path_hash_bytes is not None: group_query = group_query.having(func.max(RawPacket.path_hash_bytes) == path_hash_bytes)`
  - [x] 3.1.4 Verify HAVING works with existing WHERE clauses and `func.count(RawPacket.id)`

- [x] 3.2 Delete Phase 3 Python decode loop
  - [x] 3.2.1 Remove the `decoded_rows` fetch + `width_by_hash` loop (lines 198-216)
  - [x] 3.2.2 Replace with direct read: `path_hash_bytes=(None if is_redacted else grp.path_hash_bytes)`
  - [x] 3.2.3 Remove dead `_path_hash_byte_width` helper (lines 54-59)
  - [x] 3.2.4 Confirm `_extract_path_hashes` (line 36) is kept — still used by detail route at line 311

- [x] 3.3 Update existing tests
  - [x] 3.3.1 In `tests/test_api/test_packet_groups.py::TestPathHashBytes`, update insert fixtures to set `path_hash_bytes=` explicitly on `RawPacket` rows (tests bypass collector)
  - [x] 3.3.2 Keep coverage for 1/2/3/None/redacted paths
  - [x] 3.3.3 Verify all existing tests pass without Phase 3

- [x] 3.4 Add filter tests
  - [x] 3.4.1 `?path_hash_bytes=2` returns only width-2 groups
  - [x] 3.4.2 `?path_hash_bytes=1` and `3` return correct subsets
  - [x] 3.4.3 Missing parameter returns all groups (including null-width)
  - [x] 3.4.4 Redacted group response field is still null despite persisted value
  - [x] 3.4.5 Verify `total` count is correct when filtered vs unfiltered

## 4. Frontend & i18n (Phase 4)

- [x] 4.1 Add filter `<select>` to packets.js
  - [x] 4.1.1 Parse `const path_hash_bytes = query.path_hash_bytes || '';` (~line 57)
  - [x] 4.1.2 Extend `hasActiveFilters` with `|| path_hash_bytes !== ''` (~line 72)
  - [x] 4.1.3 Add to `apiParams`: `if (path_hash_bytes !== '') apiParams.path_hash_bytes = path_hash_bytes;` (~line 111)
  - [x] 4.1.4 Add `path_hash_bytes` to `pagination(...)` params (~line 166)
  - [x] 4.1.5 Add `path_hash_bytes` to `headerParams` (~line 194)
  - [x] 4.1.6 Add 4th entry to `filterFields` array (~line 170):
    `<select name="path_hash_bytes" class="select select-sm" @change=${autoSubmit}>`
    with options: Any (empty value) / 1B / 2B / 3B, mirroring `event_type` select style
  - [x] 4.1.7 Option labels use `packets.path_width_bytes` (`{{count}}B`) and `common.all`

- [x] 4.2 Add i18n keys
  - [x] 4.2.1 Add `"packets.filter_path_width"` to `src/meshcore_hub/web/static/locales/en.json` ("Path width")
  - [x] 4.2.2 Add `"packets.filter_path_width"` to `src/meshcore_hub/web/static/locales/nl.json` ("Padbreedte")

- [x] 4.3 Rebuild SPA bundle
  - [x] 4.3.1 Build via Docker compose pipeline (not local `node build.js` — fontsource asset requires compose context)

## 5. Verification (Phase 5)

- [x] 5.1 Run targeted tests
  - [x] 5.1.1 `pytest --no-cov tests/test_api/test_packet_groups.py`
  - [x] 5.1.2 `pytest --no-cov tests/test_collector/`
  - [x] 5.1.3 `pytest --no-cov tests/test_common/` (model column test)

- [x] 5.2 Run full test suite
  - [x] 5.2.1 `pytest --no-cov 2>&1 | grep -iE "passed|failed" | tail -3`

- [x] 5.3 Run pre-commit
  - [x] 5.3.1 `pre-commit run --all-files`

- [x] 5.4 Manual smoke test on Docker stack
  - [x] 5.4.1 Apply migration: `docker compose run --rm migrate db upgrade`
  - [x] 5.4.2 Rebuild and restart stack
  - [x] 5.4.3 Verify packet list loads with all three width filters (1B/2B/3B)
  - [x] 5.4.4 Verify "Any" filter returns all rows including null-width
  - [x] 5.4.5 Verify filter survives pagination and sort changes via URL query string
  - [x] 5.4.6 Verify redacted groups show `?B` on detail page
