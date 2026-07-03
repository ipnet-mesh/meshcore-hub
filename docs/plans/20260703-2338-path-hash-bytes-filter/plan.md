# Persist & Filter by Path-Hash Byte Width

## Summary

The packet list page (`/packets`, served by `GET /api/v1/packet-groups`) shows a
"path-hash byte width" metric per row — the ruler badge (`1B`/`2B`/`3B`/`?B`) we
recently added to the reception widget. That value is currently **derived at
request time** in Python by decoding each group's `decoded` JSON, which makes it
unfilterable at the database level and forces an expensive extra query on every
list load.

This plan **persists `path_hash_bytes` as a real column on `RawPacket`**, computed
once at ingest by the collector and backfilled for historical rows. With the value
persisted, the grouped-list route's Python decode loop collapses into a SQL
`MAX()` aggregate, and we add a clean **discrete-select filter** (Any / 1B / 2B /
3B) to the packet list page via a `HAVING` clause — fully consistent pagination and
counts, with no per-request JSON decoding.

## Background & Motivation

### Current State

- `path_hash_bytes` is **not a column**. It is computed at runtime in
  `api/routes/packet_groups.py:198-216` ("Phase 3"), which fetches the `decoded`
  JSON for every reception of the current page's packet hashes, extracts the path
  arrays, and aggregates the widest byte-width (1/2/3 from 2/4/6 hex chars). The
  aggregation was recently fixed (PR #292, commit `f845830`) to take `MAX`
  across **all** receptions because the decoded `path` is observer-relative — a
  single representative row often misses a multibyte path that other receptions
  carry.
- The packet list widget renders this as `[Dish][oc] × [Path][rc] @ [Ruler][pb]`,
  the most prominent path metric on the list.
- The collector is the **sole writer** of `RawPacket`, through a single chokepoint
  `store_raw_packet` (`collector/handlers/raw_packet.py:122-138`). It already
  computes `path_len` (hop count) there with a two-tier fallback
  (`raw_packet.py:92-96`), and it already has a collector-side mirror of the
  path-hash extraction: `_extract_message_path_hashes`
  (`letsmesh_normalizer.py:826-844`) + the `_normalize_hash_list` staticmethod
  (`:846-867`).
- The raw `/packets` endpoint already supports `min_path_len`/`max_path_len`
  range filters on the real `path_len` column — the closest filtering precedent.

### Problems

- **Unfilterable.** Because the value is computed post-query in Python, it cannot
  be filtered at the SQL level without either persisting a column or pushing
  brittle, backend-specific JSON extraction into SQL (dual-path: `decoded.path`
  and the trace fallback `decoded.payload.decoded.pathHashes`).
- **Pagination inconsistency.** A post-query Python filter (the only no-migration
  hack) would make `total` and page sizes inconsistent — bad UX.
- **Request-time cost.** Every list load performs an extra decoded-JSON fetch +
  per-row Python decode just to render the badge.

### Why Persist a Column (chosen approach)

The user confirmed the metric is **byte width** (the ruler badge) and the
approach is **persisted column (A)**. This is the only solution that is correct,
maintainable, and gives consistent pagination. The collector already extracts
path hashes at ingest, so computing the byte-width there is a trivial addition
covering 100% of new rows; a one-time Python backfill covers historical rows.

## Goals

- Persist `path_hash_bytes` (nullable `Integer`, values 1/2/3 or NULL) on
  `RawPacket`, computed at ingest from the decoded path hashes.
- Backfill the column for all existing `raw_packets` rows from their `decoded`
  JSON, portably across SQLite and Postgres.
- Add a **discrete-select filter** (Any / 1B / 2B / 3B) to the `/packets` list
  page, applied as a SQL `HAVING` on the per-group `MAX(path_hash_bytes)`.
- Simplify the grouped-list route: replace the Python decode loop (Phase 3) with
  a SQL `MAX()` aggregate, removing the per-request JSON fetch.

## Non-Goals

- Filtering the **raw** `/packets` endpoint (not the list page) by byte width.
  The column will exist on the model and DB, but surfacing it on the raw endpoint
  / `RawPacketRead` schema is out of scope (easy follow-up).
- An "Unknown" (`?B` / null) filter option — the user chose **known widths only**
  (1/2/3). Null-width packets are simply never selected by the filter; they
  remain visible under "Any".
- A numeric range (min/max) or multi-select filter shape — the user chose a
  **discrete single-select**.
- Indexing `path_hash_bytes` (mirrors `path_len`, which is also unindexed). Add
  an index later only if query plans show a need.
- Changing the per-reception path extraction in the **detail** route
  (`_extract_path_hashes` stays; only the list-path width computation is removed).

## Requirements

### Functional Requirements

- **FR-1**: A new nullable `Integer` column `path_hash_bytes` on `raw_packets`,
  holding the widest path-hash prefix width (1/2/3) for that reception, or NULL
  when no path hashes are present/decodable.
- **FR-2**: Every newly inserted `RawPacket` row has `path_hash_bytes` computed
  from its `decoded` dict at ingest (collector is the sole writer).
- **FR-3**: Historical `raw_packets` rows are backfilled from their `decoded`
  JSON during migration, using the same dual-path extraction and `max(len//2)`
  semantics as the runtime computation.
- **FR-4**: `GET /api/v1/packet-groups` accepts an optional
  `path_hash_bytes` query parameter (integer 1/2/3). When set, only groups whose
  `MAX(path_hash_bytes)` equals the value are returned. Omitting it returns all
  groups (including null-width ones) — unchanged behavior.
- **FR-5**: The list response still nulls `path_hash_bytes` for redacted groups
  (channel-visibility), exactly as today (`None if is_redacted else ...`).
- **FR-6**: The `/packets` SPA page offers a **discrete `<select>`** filter
  ("Path width": Any / 1B / 2B / 3B) that auto-submits and round-trips through
  the URL query string, surviving pagination and sort changes.

### Technical Requirements

- **TR-1** — Model (`common/models/raw_packet.py`): add
  `path_hash_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)`
  immediately after `path_len`. Unindexed (mirrors `path_len`).
- **TR-2** — Collector (`collector/handlers/raw_packet.py`): in
  `store_raw_packet`, after `path_len` is resolved (~line 96), compute
  `path_hash_bytes` from `decoded_packet` via the two-tier lookup
  (`decoded.path` → `payload.decoded.pathHashes`) using the already-imported
  `LetsMeshNormalizer._normalize_hash_list` staticmethod, then
  `max(len(h) // 2 for h in hashes)`. Add a small module-level
  `_path_hash_byte_width(hashes)` helper (mirrors the API route's helper; the
  API copy is deleted in Phase 3 so no naming collision persists). Pass
  `path_hash_bytes=` into the `RawPacket(...)` kwargs. Must be null-safe (no
  path → `None`).
- **TR-3** — Migration (`alembic/versions/`, `down_revision = "38abdf4651fc"`):
  author via `meshcore-hub db revision --autogenerate -m "add path_hash_bytes to
  raw_packets"` (produces a `batch_alter_table` `add_column`), then **manually
  append a Python batched backfill** (~1000 rows/batch) that reads each row's
  `decoded` JSON, applies the self-contained dual-path extraction +
  `max(len//2)`, and `UPDATE`s the column. Python (not SQL JSON) so it is
  portable across SQLite and Postgres. Migration logic must be a frozen
  self-contained snapshot (no imports of app code that may change). Downgrade
  drops the column. **Read mechanism**: the `decoded` column must be read via a
  Core `select()` on a `sa.Table` declared with a `sa.JSON`-typed column (or
  explicitly `json.loads()` the fetched scalar), **not** raw
  `text("SELECT decoded ...")`. Raw `text()` bypasses SQLAlchemy's JSON type
  adapter, so deserialization becomes driver-dependent (SQLite returns TEXT,
  Postgres/psycopg2 may return a parsed object or string). Core `select()`
  routes through the type adapter and yields a Python `dict` consistently on
  both backends.
- **TR-4** — API route (`api/routes/packet_groups.py`):
  - Phase 1 `group_query` select: add
    `func.max(RawPacket.path_hash_bytes).label("path_hash_bytes")`.
  - New param: `path_hash_bytes: Optional[int] = Query(None, ge=1, le=3,
    description="Filter by path-hash byte width (1/2/3)")`.
  - Apply filter:
    `if path_hash_bytes is not None: group_query = group_query.having(func.max(RawPacket.path_hash_bytes) == path_hash_bytes)`.
  - **Delete Phase 3** (lines 198-216, the `decoded_rows` fetch + `width_by_hash`
    loop). Read `grp.path_hash_bytes` from the group row instead.
  - Build item with
    `path_hash_bytes=(None if is_redacted else grp.path_hash_bytes)`.
  - Remove the now-dead `_path_hash_byte_width` helper (lines 54-59) from this
    file. **Keep** `_extract_path_hashes` — the detail route `get_packet_group`
    still uses it (`:311`).
- **TR-5** — Frontend (`packets.js`):
  - Parse `const path_hash_bytes = query.path_hash_bytes || '';` alongside the
    other filter reads (~line 57).
  - Extend `hasActiveFilters` (~line 72) with `|| path_hash_bytes !== ''`.
  - Add a 4th entry to the `filterFields` array (~line 170): a
    `<select name="path_hash_bytes" class="select select-sm" @change=${autoSubmit}>`
    with options Any / 1B / 2B / 3B, mirroring the `event_type` select style.
    Option labels reuse `packets.path_width_bytes` (`{{count}}B`) and
    `common.all` / a new `packets.filter_path_width` label.
  - Add `if (path_hash_bytes !== '') apiParams.path_hash_bytes = path_hash_bytes;`
    (~line 111).
  - Add `path_hash_bytes` to the `pagination(...)` params (~line 166) and
    `headerParams` (~line 194) so it survives pagination and sort.
- **TR-6** — i18n (`locales/en.json`, `locales/nl.json`): add
  `packets.filter_path_width` ("Path width" / "Padbreedte"). Option labels reuse
  existing `packets.path_width_bytes` and `common.all` — no new keys needed for
  them.
- **TR-7** — `apiGet` (`api.js`) and `createFilterHandler` (`components.js`)
  already skip empty/falsy values, so no changes there.

## Implementation Plan

### Phase 1: Model & Migration

- Add `path_hash_bytes` column to `RawPacket` (TR-1).
- Generate the migration with `--autogenerate` against head `38abdf4651fc`
  (TR-3), producing `batch_alter_table` `add_column`.
- Manually append the Python batched backfill loop (TR-3): read
  `id, decoded WHERE path_hash_bytes IS NULL` in batches (~1000 rows/batch)
  via a Core `select()` on a `sa.Table` with a `sa.JSON`-typed `decoded` column
  (so the type adapter deserializes to a `dict` on both SQLite and Postgres —
  do **not** use raw `text("SELECT decoded ...")`), compute width, `UPDATE`.
  The backfill must include a **self-contained**, frozen copy of the dual-path
  extraction + `max(len//2)` logic — no imports of app code that may change in
  future versions. Rows where `decoded` is `None` are left as `NULL` (the
  column is nullable; `WHERE path_hash_bytes IS NULL` naturally skips
  already-filled rows and leaves truly uncomputable ones alone).
- Verify the model test (column presence/default) and that `db upgrade` applies
  cleanly on both backends.

### Phase 2: Collector Ingest Compute

- Add the module-level `_path_hash_byte_width(hashes)` helper in
  `collector/handlers/raw_packet.py`.
- In `store_raw_packet`, compute `path_hash_bytes` from `decoded_packet` after
  `path_len`, using `LetsMeshNormalizer._normalize_hash_list` + the two-tier
  lookup (TR-2). Pass it into the `RawPacket(...)` kwargs.
- Add a collector test: `store_raw_packet` persists the expected width for a
  decoded packet carrying `decoded.path`, for the trace fallback path, and
  `None` when no path is present (mirror the existing `path_len` test).

### Phase 3: API Route Simplification & Filter

- In `packet_groups.py`, add the `func.max(RawPacket.path_hash_bytes)` aggregate
  to Phase 1 and the new `path_hash_bytes` query param + `HAVING` filter (TR-4).
- Delete Phase 3 (the Python decode loop); read `grp.path_hash_bytes`. Remove the
  now-dead `_path_hash_byte_width` helper. Keep `_extract_path_hashes`.
- Preserve redaction nulling in the item construction (TR-4 / FR-5).
- Update `tests/test_api/test_packet_groups.py::TestPathHashBytes` to set
  `path_hash_bytes=` directly on inserted `RawPacket` rows (tests bypass the
  collector). Keep 1/2/3/None/redacted coverage.
- Add filter tests: `?path_hash_bytes=2` returns only width-2 groups;
  `?path_hash_bytes=1`/`3` likewise; omitted returns all; a redacted group's
  response field is still null.

### Phase 4: Frontend Filter & i18n

- Add the discrete `<select>` filter field to `packets.js` (TR-5).
- Wire the query parse, `hasActiveFilters`, `apiParams`, `pagination` params, and
  `headerParams` (TR-5).
- Add `packets.filter_path_width` to both locale files (TR-6).
- Rebuild the SPA bundle via the Docker build pipeline (local `node build.js`
  fails on a missing fontsource asset — build through compose).

### Phase 5: Verify

- `pytest --no-cov tests/test_api/test_packet_groups.py tests/test_collector/`
- `pre-commit run --all-files`
- Apply the migration on the stack and manually verify the filter on the packet
  list (all three known widths; "Any" returns null-width rows too).

## Open Questions

- None outstanding. Metric (byte width), approach (persisted column), filter
  shape (discrete select), and unknown-option exclusion (known widths only) are
  all resolved.
- **Phase-ordering window** (minor, not blocking): Between migration (Phase 1)
  and collector ingester deploy (Phase 2), new RawPacket rows are inserted with
  `path_hash_bytes = NULL`. The backfill fills historical rows, but a brief gap
  exists for rows ingested during the deploy window. Once Phase 2 is active, new
  rows carry the correct value and Phase 3 reads it. In practice the window is
  seconds in a single `docker compose up -d` rebuild; any rows missed still render
  `?B` (unchanged UX), and the next backfill run would catch them.
- Minor follow-up (not blocking): whether to also surface `path_hash_bytes` on
  the raw `/packets` endpoint's `RawPacketRead` schema, now that the column
  exists.

## References

- `docs/plans/20260612-2014-raw-packets-feature/plan.md` — the Raw Packets
  feature this builds on (model, collector chokepoint, channel-visibility
  redaction, `/packets` SPA page).
- `docs/plans/20260426-1137-improve-snr-path-visibility/plan.md` — prior
  `path_len` (hop-count) column work and the "no backfill for per-observer
  fields" decision (here we *do* backfill, since the value is derivable from the
  already-stored `decoded` JSON).
- `src/meshcore_hub/api/routes/packet_groups.py:54-59,198-216,240` — current
  runtime `_path_hash_byte_width` + Phase 3 aggregation + redaction nulling
  (to be replaced/deleted).
- `src/meshcore_hub/collector/handlers/raw_packet.py:92-96,122-138` — `path_len`
  precedent and the single `RawPacket(...)` construction site.
- `src/meshcore_hub/collector/letsmesh_normalizer.py:826-867` —
  `_extract_message_path_hashes` + `_normalize_hash_list` (staticmethod) to reuse.
- `src/meshcore_hub/api/routes/raw_packets.py:165-172` — `min_snr`/`max_snr` and
  `min_path_len`/`max_path_len` range-filter precedent.
- `alembic/versions/20260622_2243_38abdf4651fc_add_spam_scoring_columns_to_messages.py`
  — `batch_alter_table` add-column + index precedent (current migration head).
- `alembic/versions/20260421_0001_normalize_public_key_case.py` — Python data
  backfill precedent (`op.get_bind()`, dialect-aware raw SQL).
- Recent commits: `f845830` (JSON tree / path flow / chart polish, PR #292),
  `2c25a9c` (locale-aware numbers + filter panel redesign, PR #291) — the
  reception-widget + filter-panel work this plan extends.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-03

### Resolutions

- **Factual correction — aggregation fix is committed, not uncommitted**: The
  Phase 3 MAX-across-all-receptions fix described as "uncommitted" was committed
  in PR #292 (`f845830`). Updated to "recently committed (PR #292)".

- **Gap — self-contained migration backfill**: Clarified that the backfill loop
  must include a frozen, inline copy of the dual-path extraction +
  `max(len//2)` logic. Rows with `decoded = NULL` are left as NULL (the
  `WHERE path_hash_bytes IS NULL` clause naturally skips them).

- **Gap — collector / API helper naming collision**: Noted that the collector's
  `_path_hash_byte_width` helper mirrors the API route's (deleted in Phase 3),
  so no persistent naming conflict exists.

- **Risk — rows ingested between migration and collector deploy**: Added a brief
  note under Open Questions that the Phase 1→2 deploy window can leave
  `path_hash_bytes = NULL` for new rows, but the window is seconds in a compose
  rebuild, and the UX is unchanged (`?B` label) for any rows missed.

- **Postgres JSON type & backfill read mechanism**: Confirmed the `decoded`
  column is SQLAlchemy `JSON` (not `JSONB`). The Python backfill reads decoded
  as a Python `dict` via a Core `select()` on a `sa.Table` with a `sa.JSON`-typed
  column — this routes through SQLAlchemy's JSON type adapter, which deserializes
  consistently across SQLite (TEXT storage) and Postgres. Raw
  `text("SELECT decoded ...")` must **not** be used: it bypasses the type adapter,
  making deserialization driver-dependent (SQLite returns TEXT; Postgres/psycopg2
  may return a parsed object or string). No SQL JSON operators are needed —
  consistent with TR-3.

### Remaining Action Items

- **Migration down_revision**: Before generating the migration, confirm that
  `38abdf4651fc` is still the head revision (new migrations may land between
  plan approval and implementation). The `meshcore-hub db revision` command
  auto-resolves this — just verify the `down_revision` value in the generated
  file.

- **Phase 2 collector test**: The existing `test_store_raw_packet` test in
  `tests/test_collector/` does not appear to cover `path_len` persistence;
  verify whether a collector test for the new column can sit alongside or
  replace the `path_len` test, and whether the test fixture accepts
  `decoded_packet=` with path hashes.

- **Frontend bundle rebuild**: Must be built via Docker compose (local
  `node build.js` fails on the fontsource asset). The plan notes this in
  Phase 4.
