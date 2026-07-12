# Tasks: Routes (Route Health Monitoring)

> Generated from `plan.md` on 2026-07-12

## 1. Data Models & Schema Migration (Phase 1)

- [x] Create `src/meshcore_hub/common/models/packet_path_hop.py` — `PacketPathHop` model
  - [x] Columns: `raw_packet_id` (FK `raw_packets.id`, `ondelete=CASCADE`), `position` (int), `node_hash` (String), denormalized `packet_hash` (String), `received_at` (DateTime), `observer_node_id` (String, nullable, FK `nodes.id`)
  - [x] `INDEX (node_hash, received_at)` — drives first-prefix + window range scan in `fetch_candidate_paths`
  - [x] `INDEX (raw_packet_id, position)` — serves per-reception ordered-hop fetch, FK lookup, `ON DELETE CASCADE` (leftmost-prefix covers equality-on-`raw_packet_id`, no separate FK index)
- [x] Create `src/meshcore_hub/common/models/route.py` — `Route` model + `RouteVisibility` enum (mirrors `ChannelVisibility`)
  - [x] `RouteVisibility` enum: `community` / `member` / `operator` / `admin`
  - [x] `Route` columns: `name` (unique), `description` (nullable Text), `visibility` (RouteVisibility, default `community`), `match_width` (int, default 1, range 1..3), `window_hours` (int, default 24, range 1..720), `packet_count_threshold` (int, default 3, range 1..10000), `degraded_threshold` (nullable int, default null), `max_hop_span` (nullable int, default null = unlimited), `enabled` (bool, default true)
  - [x] Relationships: `route_nodes`, `route_observers`, `route_result` (all `cascade="all, delete-orphan"`)
- [x] Create `src/meshcore_hub/common/models/route_node.py` — `RouteNode` model
  - [x] Columns: `route_id` (FK `routes.id`, `ondelete=CASCADE`), `node_id` (FK `nodes.id`), `position` (int, ordered), `expected_hash` (String, derived as `public_key[:2*match_width].upper()` at save time)
- [x] Create `src/meshcore_hub/common/models/route_observer.py` — `RouteObserver` model
  - [x] Columns: `route_id` (FK `routes.id`, `ondelete=CASCADE`), `node_id` (FK `nodes.id`)
- [x] Create `src/meshcore_hub/common/models/route_result.py` — `RouteResult` model
  - [x] `route_id` (FK `routes.id`, `ondelete=CASCADE`, unique — one row per route)
  - [x] `state` (enum `healthy` / `unhealthy` / `no_coverage` — the alerting axis)
  - [x] `quality` (enum `clear` / `marginal` / `failing` / `unknown` — the display axis, denormalized)
  - [x] `matched_count` (int), `threshold` (int, snapshot at eval time), `effective_degraded` (int, snapshot of `effective_degraded_threshold(route)` at eval time), `evaluated_at` (DateTime)
- [x] Export all five new models from `src/meshcore_hub/common/models/__init__.py`
- [x] Author one Alembic revision (batch mode, SQLite-safe) creating the five tables + indexes
- [x] Backfill `packet_path_hops` from `raw_packets.decoded`
  - [x] Keyset-paginated (batch 1000) over `raw_packets`
  - [x] Reuse the frozen dual-path extraction copied from migration `20260703_2250` (`_normalize_hash_list` + `decoded.path` → `payload.decoded.pathHashes` fallback)
  - [x] Enumerate the extracted list (index = `position`), emit one `PacketPathHop` row per `(position, node_hash)` with `packet_hash`/`received_at`/`observer_node_id` denormalized from the source `raw_packet` row
- [x] Verify migration applies cleanly on SQLite and Postgres (batch mode)

## 2. Ingest Pipeline (Phase 2)

- [x] Refactor `src/meshcore_hub/collector/handlers/raw_packet.py::store_raw_packet`
  - [x] Change inline `session.add(RawPacket(...))` (lines 138-155) to `raw_packet = RawPacket(...); session.add(raw_packet); session.flush()` so `raw_packet.id` is materialized
  - [x] After the flush, bulk-insert one `PacketPathHop` per `(position, node_hash)` from the already-computed `path_hashes` (lines 106-111), inside the existing `with db.session_scope()` block (line 118)
  - [x] Denormalize `packet_hash`/`received_at`/`observer_node_id` from the same in-scope values (`observer_node_id` already available as `observer_node.id` at line 140)
  - [x] Zero extra decode; hop extraction gated by existing raw-capture flag (caller `_perhaps_capture_raw_packet` already checks `_raw_packet_capture_enabled`)
- [x] Extend `tests/test_collector/test_handlers/test_raw_packet.py`
  - [x] Assert hops are inserted with correct positions/hashes
  - [x] Assert hops are skipped when path is absent
  - [x] Assert `observer_node_id` denormalized correctly

## 3. Matching Engine (Phase 3)

- [x] Create `src/meshcore_hub/collector/routes.py` with fetch-and-check strategy (not N-way self-join)
  - [x] `fetch_candidate_paths(db, first_prefix, since, observer_ids=None, limit=None)` — one statement with subquery to avoid `SQLITE_MAX_VARIABLE_NUMBER` ceiling
  - [x] `is_subsequence(path, expected, max_hop_span=None)` — pure two-pointer prefix match, gaps allowed, span cap
  - [x] `DEGRADED_DEFAULT_MULTIPLIER = 2` module constant
  - [x] `effective_degraded_threshold(route)` — returns `route.degraded_threshold or (route.packet_count_threshold * DEGRADED_DEFAULT_MULTIPLIER)`
  - [x] `derive_quality(state, matched_count, threshold, effective_degraded)` — pure mapping implementing F4's quality axis
  - [x] `evaluate_route(db, route, since)` — fetch candidates, run subsequence, count distinct `packet_hash`, short-circuit at `effective_degraded_threshold`, existence check for `no_coverage` vs `unhealthy`
  - [x] `evaluate_all_routes(db, since)` — iterate only enabled routes, call `evaluate_route`
  - [x] `recent_matches(db, route, limit=3)` — same fetch + subsequence check, returns latest matching paths
  - [x] `preview_route(db, config, since)` — unsaved config with candidate cap (default 5000), returns `{matched_count, quality, contributing_observers, collisions}`
  - [x] Helpers: `derive_expected_hash`, `_hex_prefix_end`, `detect_observed_widths`, `prefix_collision_counts`
- [x] Create `tests/test_collector/test_routes.py`
  - [x] Subsequence: gaps allowed, order enforced, span cap
  - [x] Per-reception isolation (no cross-observer splice — T2 semantics)
  - [x] Multi-observer dedup to distinct packets (`COUNT(DISTINCT packet_hash)`)
  - [x] Observer-scope filter
  - [x] Threshold short-circuit (at `effective_degraded`)
  - [x] `no_coverage` vs `unhealthy` separation
  - [x] Quality-band derivation (clear / marginal / failing / unknown, incl. null ⇒ `2 × threshold` relative default)
  - [x] `recent_matches` ordering/limit
  - [x] Preview truncation at candidate cap

## 4. CRUD API & Schemas (Phase 4)

- [x] Create `src/meshcore_hub/common/schemas/routes.py`
  - [x] `RouteCreate` / `RouteUpdate` / `RouteRead` / `RouteList` / `RouteDetail` / `RoutePreviewRequest` / `RoutePreviewResponse` Pydantic models
  - [x] Validate ≥2 **distinct** `route_nodes` in Pydantic
  - [x] Validate `degraded_threshold` either null or `> packet_count_threshold`
  - [x] `expected_hash` auto-derived (uppercased) from `node_id` when omitted; re-derived for all path nodes when `match_width` changes
- [x] Create `src/meshcore_hub/api/routes/routes.py` (mirror `api/routes/channels.py`)
  - [x] `GET /api/v1/routes` — RequireRead, role-filtered, `@cached`, embeds lightweight `route_result`
  - [x] `POST /api/v1/routes` — RequireAdmin, collection-level
  - [x] `GET /api/v1/routes/{id}` — RequireRead, role-scoped, returns full detail
  - [x] `PUT /api/v1/routes/{id}` — RequireAdmin
  - [x] `DELETE /api/v1/routes/{id}` — RequireAdmin
  - [x] `POST /api/v1/routes/preview` — RequireRead, not cached; delegates to `collector.routes.preview_route`
- [x] Register router in `src/meshcore_hub/api/routes/__init__.py`
- [x] Create `tests/test_api/test_routes.py`
  - [x] CRUD lifecycle, role-scoping, visibility filter
  - [x] Min-2-nodes rejection, distinct-node rejection
  - [x] `degraded_threshold` validation (null ok; `<= threshold` rejected)
  - [x] Result embedding on list (lightweight) and detail (full)
  - [x] Preview endpoint (matched_count, quality, collisions, truncation)
  - [x] `GET /{id}` detail shape (observers + recent paths)

## 5. Background Evaluator (Phase 5)

- [x] Create `src/meshcore_hub/collector/route_evaluator.py` wrapping `collector/routes.py`
- [x] Wire evaluator into `src/meshcore_hub/collector/subscriber.py`
  - [x] Add `_start_route_evaluator_scheduler` / `_stop_route_evaluator_scheduler` methods
  - [x] Start in `start()` (after spam scheduler)
  - [x] Stop in `stop()` (after spam stop)
  - [x] Add thread attribute near line 114
  - [x] Immediate first run on startup, 60s loop, per-iteration error logging
  - [x] Upsert into `route_results` via ORM check-then-update/insert (functionally equivalent to dialect-specific upsert in single-threaded context)
- [x] Create `tests/test_collector/test_route_evaluator.py`
  - [x] Upsert idempotency (same route re-evaluated overwrites its single result row)
  - [x] Disabled routes skipped
  - [x] Correct result values written

## 6. Prometheus Metrics (Phase 6)

- [x] Modify `src/meshcore_hub/api/metrics.py::collect_metrics` — read `route_results ⋈ routes`, emit for all enabled routes
  - [x] `meshcore_route_healthy{route}` (1 if `quality` ∈ {clear, marginal} else 0)
  - [x] `meshcore_route_quality{route}` (0=clear, 1=marginal, 2=failing, 3=unknown)
  - [x] `meshcore_route_matched_packets{route}` (lower bound when `quality == clear`)
  - [x] `meshcore_route_threshold{route}`
  - [x] `meshcore_route_degraded_threshold{route}` (effective comfort bar; `2 × threshold` when unset)
- [x] Verify in `tests/test_api/test_metrics.py`

## 7. Web UI & i18n (Phase 7)

- [x] Create `src/meshcore_hub/web/static/js/spa/pages/routes.js` (mirror `channels.js` structure)
  - [x] Summary strip at top with live quality counts
  - [x] Cards grouped by visibility, sorted failing/no_coverage/marginal first
  - [x] Five-state quality badge (clear/marginal/failing/no_coverage/disabled)
  - [x] Path chips showing ordered nodes
  - [x] Numbers line (matched / threshold → degraded · window · evaluated time)
  - [x] Admin edit/delete buttons
  - [x] Inline accordion expand (lazy `GET /api/v1/routes/{id}`, cached) with diagnosis, contributing observers, recent matches, config recap
  - [x] Wider (`modal-box-lg`) add/edit modal with name, description, visibility, enabled, segmented `match_width` control, node IDs input, observer IDs input, numeric fields, preview
- [x] Register page in `src/meshcore_hub/web/static/js/spa/app.js`
  - [x] Add `routes: () => import('./pages/routes.js')` to `pages` lazy-load map
  - [x] Add route registration guarded by `features.routes !== false`
  - [x] Add `composePageTitle('entities.routes')` title entry
- [x] Add nav card in `src/meshcore_hub/web/static/js/spa/pages/home.js`
- [x] Add i18n strings to `src/meshcore_hub/web/static/locales/en.json` and `nl.json`
  - [x] `entities.routes` (value "Routes")
  - [x] New top-level `routes.*` block with all page strings incl. quality labels
- [x] Add `--color-routes` CSS variable in `app.css`

## 8. Configuration, Seed Loader & Docs (Phase 8)

- [x] Add config to `src/meshcore_hub/common/config.py`
  - [x] `feature_routes=True` `Field(...)` declaration
  - [x] `route_evaluator_interval_seconds=60` `Field(...)` declaration (in `CollectorSettings`)
  - [x] `"routes": self.feature_routes` entry in `features` property dict
  - [x] `routes_file` property mirroring `channels_file`
- [x] Update `.env.example` with the two new settings
- [x] Create `_import_routes` in `src/meshcore_hub/collector/cli.py`
  - [x] Wire into `_run_seed_import` so `meshcore-hub seed` picks up `routes.yaml` automatically
  - [x] Idempotent upsert by `name`; resolve path/observer nodes by `public_key`
  - [x] Derive `expected_hash` (uppercased); never hand-typed
  - [x] Replace `route_nodes`/`route_observers` wholesale on update
  - [x] Missing **path** node = hard error; missing **observer** = skipped with warning
  - [x] Honor seeded `visibility` (default `community`) and `degraded_threshold` (null ⇒ `2 × threshold`)
  - [x] Return `{created, updated, errors}` shape
- [x] Create `example/seed/routes.yaml` documenting the format
- [ ] Update docs: `SCHEMAS.md`, `README.md`; cross-reference from `docs/seeding.md` and `docs/letsmesh.md` *(deferred — implementation complete, docs follow-up)*
- [ ] Optional: `meshcore-hub routes list|delete` CLI *(deferred)*

## 9. Packet-Detail Consolidation (Phase 9)

- [x] Modify `src/meshcore_hub/api/routes/packet_groups.py::get_packet_group`
  - [x] Replace per-reception `_extract_path_hashes(packet.decoded)` with batched hop-table query
  - [x] Group results into `receptions[i].path_hashes` shape
  - [x] Hash values are normalized (uppercased) from hop table
  - [x] Fall back to empty list for rows lacking hops
- [x] Delete `_extract_path_hashes` — dead third copy of dual-path extraction
- [x] Update `tests/test_api/test_packet_groups.py`
  - [x] Assert detail endpoint returns `path_hashes` per reception from hop table
  - [x] Test missing hops returns None

## 10. Verification

- [x] Run targeted tests per phase — all pass
- [x] Run full suite: `pytest -nauto --no-cov` — **1263 passed, 22 skipped**
- [x] Run `pre-commit run --all-files` — **all hooks pass** (black, flake8, mypy, etc.)
- [ ] Verify migration applies + backfills on a volume DB *(requires Docker stack — deferred to deployment)*
- [ ] Manual smoke test in compose stack *(requires Docker stack — deferred to deployment)*
