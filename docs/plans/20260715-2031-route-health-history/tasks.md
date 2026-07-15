# Tasks: Route Health History (7-Day Charts)

> Generated from `plan.md` on 2026-07-15

## Phase 1: Day-Bounded Matching Engine

- [x] Extend `fetch_candidate_paths` with optional `until` param
  - [x] Add `until: Optional[datetime] = None` parameter to `fetch_candidate_paths` in `collector/routes.py`
  - [x] Append `PacketPathHop.received_at < until` to the existing `received_at >= since` filter (line ~262) when `until` is provided
  - [x] Verify the composite index `ix_packet_path_hops_node_hash_received_at` covers the bounded range scan
- [x] Extend `_fetch_candidate_paths_maybe_bidirectional` with `until` param
  - [x] Add `until: Optional[datetime] = None` parameter
  - [x] Pass `until` through to `fetch_candidate_paths` in both forward and bidirectional call paths
- [x] Extend `_has_any_hops_in_window` with `until` param
  - [x] Add `until: Optional[datetime] = None` parameter
  - [x] Apply the same `received_at < until` bound to the existence check
- [x] Add `evaluate_route_day(session, route, day_start, day_end)` (TR-1)
  - [x] Implement as a sibling of `evaluate_route` (line ~341), mirroring its logic exactly
  - [x] Call the bounded fetch helpers (`_fetch_candidate_paths_maybe_bidirectional` with both `since=day_start` and `until=day_end`)
  - [x] Reuse `_route_expected_hashes`, `effective_degraded_threshold`, `_match_hops`, `derive_quality` unchanged
  - [x] Return `tuple[str, str, int]` — `(quality, state, matched_count)`
  - [x] Do NOT modify `evaluate_route` or `upsert_route_result` (hot path stays untouched)
- [x] Add `evaluate_route_history(session, route, days, *, include_today=False)` (TR-2)
  - [x] Compute UTC midnight day boundaries for `days` calendar buckets, oldest first
  - [x] When `include_today=True`, add one extra partial-day entry for today
  - [x] Call `evaluate_route_day` per day
  - [x] For a disabled route, return `(date, RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0)` for every day without a DB hit
  - [x] Return `list[tuple[date, str, str, int]]`
- [x] Write unit tests for day-bounded engine (`tests/test_collector/test_routes.py`)
  - [x] `evaluate_route_day` returns correct band for clear / marginal / failing / no_coverage
  - [x] Seed hops inside vs. outside the day window and assert correct classification
  - [x] Day boundaries are strict: hops in adjacent day do not leak across `day_end`
  - [x] `evaluate_route_history` returns `days` entries oldest-first
  - [x] `include_today=True` adds one extra partial-day entry
  - [x] Disabled route returns `unknown`/`no_coverage`/`0` for every day without a DB hit

## Phase 2: Schemas + API Endpoints

- [x] Add Pydantic schemas to `common/schemas/routes.py` (TR-3)
  - [x] `RouteDayQuality` with `date: date`, `quality: str`, `state: str`, `matched_count: int`
  - [x] `RouteHistory` with `route_id: str`, `days: int`, `data: list[RouteDayQuality]`
  - [x] `RouteFleetDayPoint` with `date: date`, `clear: int = 0`, `marginal: int = 0`, `failing: int = 0`, `no_coverage: int = 0`, `disabled: int = 0`
  - [x] `RouteFleetHistory` with `days: int`, `data: list[RouteFleetDayPoint]`
  - [x] Use `datetime.date` (not `datetime`) for `date` fields so payloads serialize as `YYYY-MM-DD`
- [x] Add fleet history endpoint `GET /history` to `api/routes/routes.py` (TR-4)
  - [x] Import `evaluate_route_history` from `collector.routes` and the new schemas
  - [x] Read `settings.effective_raw_packet_retention_days` for the `days` clamp
  - [x] Decorate with `@cached("routes/history", ttl_setting="redis_cache_ttl_dashboard", key_builder=_routes_key_builder)`
  - [x] Load routes visible to caller's role (reuse visibility filter from `get_routes`)
  - [x] Clamp `days = min(days, settings.effective_raw_packet_retention_days)`
  - [x] For each enabled route, call `evaluate_route_history(session, route, days, include_today=False)`
  - [x] Bucket each day's quality into band counters: `quality=unknown` → `no_coverage` (matching `routes.js:51-68`)
  - [x] Disabled routes increment `disabled` for every day
  - [x] Return oldest-day-first
  - [x] **CRITICAL: Declare this endpoint BEFORE the `/{route_id}` routes** so FastAPI does not match `history` as a `route_id` path parameter
- [x] Add per-route history endpoint `GET /{route_id}/history` to `api/routes/routes.py` (TR-5)
  - [x] Decorate with `@cached("routes/{id}/history", ttl_setting="redis_cache_ttl_dashboard", key_builder=_routes_key_builder)`
  - [x] Fetch the route, apply visibility check (mirror `get_route` lines 220–229 — 404 when not found or above caller's level)
  - [x] Clamp `days = min(days, settings.effective_raw_packet_retention_days)`
  - [x] Call `evaluate_route_history(session, route, days, include_today=True)`
  - [x] Return `RouteHistory` with per-day `RouteDayQuality` entries
- [x] Write API tests (`tests/test_api/test_routes.py`)
  - [x] Fleet endpoint: response shape matches `RouteFleetHistory`
  - [x] Fleet endpoint: per-day band counts sum to the visible-route count
  - [x] Fleet endpoint: disabled routes count only to `disabled`
  - [x] Fleet endpoint: visibility filtering — low-role caller does not see admin-only routes
  - [x] Fleet endpoint: `days` clamped to `effective_raw_packet_retention_days`
  - [x] Fleet endpoint: caching is role-keyed (different roles get different results)
  - [x] Per-route endpoint: per-day quality/state/matched_count shape
  - [x] Per-route endpoint: 404 for a hidden route (above caller's level)
  - [x] Per-route endpoint: 404 for an unknown route_id
  - [x] Per-route endpoint: includes today as the final segment
  - [x] Route-ordering guard: `GET /history` is not shadowed by `GET /{route_id}`

## Phase 3: Chart Helpers + Quality Palette

- [x] Add `quality` color map to `ChartColors` in `charts.js` (TR-6)
  - [x] Add as a sibling of the existing `breakdown` palette (lines 56–64)
  - [x] Use hardcoded oklch values (not CSS custom properties — `app.css` has no semantic status colors)
  - [x] Map: `clear` → green oklch, `marginal` → amber oklch, `failing` → red oklch, `no_coverage` → info-blue oklch, `disabled` → neutral grey oklch
- [x] Add `createRouteOverviewChart(canvasId, fleetData)` to `charts.js` (TR-7)
  - [x] `type: 'bar'` (vertical), labels via `formatDateLabels(fleetData.data)` (reuse helper at line 137)
  - [x] One dataset per band in fixed semantic order: clear, marginal, failing, no_coverage, disabled
  - [x] Each dataset: `data` = per-day count, `backgroundColor` = `ChartColors.quality[band]`
  - [x] `scales.x.stacked = true`, `scales.y.stacked = true`, `scales.y.beginAtZero = true`
  - [x] Reuse `createChartOptions(true)` for legend/tooltip theming
  - [x] Override tooltip `label` callback to list non-zero bands per hovered day
  - [x] Return `null` on empty/no-routes data (matching `createLineChart`'s idiom at line 155)
- [x] Add `createRouteDetailStrip(canvasId, routeData)` to `charts.js` (TR-8)
  - [x] `type: 'bar'`, `indexAxis: 'y'`, `labels: ['']` (one row)
  - [x] One dataset per day: `{ label: <date>, data: [1], backgroundColor: ChartColors.quality[day.quality] }`
  - [x] `scales.x.stacked = true`, `scales.y.stacked = true` so seven unit-width datasets render as one bar with seven equal colored segments
  - [x] Hide both axes' ticks
  - [x] Render a date-axis row beneath the canvas via HTML (not Chart.js) so dates align under each segment — fallback: Chart.js category x-axis with `ticks.maxRotation: 0`, `maxTicksLimit: 7`
  - [x] Tooltip per segment: date + quality label + `matched_count`
  - [x] Return `null` when `routeData` is empty
- [ ] Manual check: verify both helpers render correctly from browser console with mock data
  - [ ] `make up`, then call helpers from console with sample payloads
  - [ ] Confirm stacked scales, segment colors, tooltips before SPA wiring

## Phase 4: SPA Wiring + i18n

- [x] Add i18n keys to `en.json` and `nl.json` (TR-11)
  - [x] `routes.history_title` — "Health (last 7 days)" / "Gezondheid (laatste 7 dagen)"
  - [x] `routes.history_detail_title` — "Last 7 days" / "Laatste 7 dagen"
  - [x] `routes.history_today` — "Today" / "Vandaag"
  - [x] Verify existing band labels (`routes.quality_clear`, etc.) are reused for legend/tooltips
- [x] Add fleet overview chart to `spa/pages/routes.js` (TR-9)
  - [x] Add a chart card with `<canvas id="routeOverviewChart">` adjacent to the existing summary strip (`renderSummaryStrip`, line 51)
  - [x] Gate on `features.routes !== false`
  - [x] After routes list loads in `renderPage`, fire `apiGet('/api/v1/routes/history', { days: 7 }, { signal })`
  - [x] Call `createRouteOverviewChart` with the response
  - [x] Create a `chartIds` array and return a cleanup function that destroys each Chart.js instance on page unmount (mirror `dashboard.js:324-333`)
  - [x] Include abort support via `{ signal }` for fetch cancellation on page unmount
- [x] Add detail status strip to `spa/pages/routes.js` (TR-10)
  - [x] Inside the expanded-card detail content (`renderDetailContent`), add a `<canvas>` element
  - [x] Fetch `/api/v1/routes/${route.id}/history?days=7` lazily (only when card is expanded)
  - [x] Call `createRouteDetailStrip` with the response
  - [x] Destroy the strip instance when the card collapses
  - [x] Match the existing lazy-load pattern used for the `detail` payload

## Phase 5: Verification

- [x] Run targeted tests
  - [x] `pytest --no-cov tests/test_collector/test_routes.py`
  - [x] `pytest --no-cov tests/test_api/test_routes.py`
  - [x] `pytest --no-cov tests/test_web/`
- [x] Run quality checks
  - [x] `pre-commit run --all-files`
- [ ] Rebuild and start the stack
  - [ ] `make build` (SPA bundle rebuild via Docker pipeline)
  - [ ] `make up`
- [ ] Visual verification on `/routes` page
  - [ ] Fleet chart renders with 7 stacked bars (one per day)
  - [ ] Tooltips list non-zero bands per day
  - [ ] Legend lists bands in fixed semantic order (clear → marginal → failing → no_coverage → disabled)
  - [ ] Expand a route card: status strip renders 7 colored segments oldest → newest
  - [ ] Today's segment is labeled on the detail strip
  - [ ] Tooltips show date + band label + matched_count
- [ ] Edge case verification
  - [ ] Empty state: no visible routes → blank canvas + "no routes" message
  - [ ] Route with no hops in window → all-grey (no_coverage) strip
  - [ ] Role scoping: log in as a low-role user, confirm fleet counts and per-route 404 reflect visibility
- [ ] Resolve Open Question: "Today" in the overview
  - [ ] Evaluate whether excluding today from fleet chart but including it on detail strip reads awkwardly
  - [ ] If so, include today in both (partial-day bars acceptable for a status board)
- [ ] Resolve Open Question: Status-strip date axis
  - [ ] Confirm HTML date row aligns cleanly under segments
  - [ ] If not, switch to Chart.js category x-axis with `ticks.maxRotation: 0`, `maxTicksLimit: 7`
