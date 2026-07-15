# Route Health History (7-Day Charts)

## Summary

Add two Chart.js visualizations of route health over the last 7 days, backed by
**compute-on-read** re-evaluation of the existing matching engine against
`packet_path_hops`. The Routes overview page gains a **fleet distribution
chart** — vertical stacked bars per day, each bar showing how many routes were
in each quality band (clear / marginal / failing / no_coverage / disabled).
The per-route detail expand gains a **status strip** — a single horizontal bar
split into 7 day-segments, each colored by that day's quality band (green /
amber / red / grey), like an uptime-monitor status bar.

No new database tables or migrations are required. Health history is
reconstructed on demand by re-running the existing `evaluate_route` matching
logic per calendar day over the retained `packet_path_hops` rows. The history
horizon therefore tracks `effective_raw_packet_retention_days` automatically (default 7)
— bumping that setting widens the chart's available window with no code change.
Both endpoints are Redis-cached behind the same `redis_cache_ttl_dashboard` TTL
used by the dashboard timeseries endpoints, and the entire Chart.js color/date
infrastructure already in `charts.js` is reused.

## Background & Motivation

The Routes feature (`20260705-2306-mesh-link-monitoring`, shipped across commits
`14fbc45` → `ae22dff`) introduced the `Route` entity, the `packet_path_hops`
ingest index, the `evaluate_route` matching engine, the 60-second background
evaluator, and the `/routes` status-board page. **Health is, however, strictly
point-in-time:** the evaluator upserts a single `RouteResult` row per route in
place (`upsert_route_result`, `collector/routes.py:415`), overwriting
`state`/`quality`/`matched_count` every cycle. Past values are lost — the
feature's own Non-Goals listed "historical route-health time series" as future
work.

Operators can see *right now* whether a route is clear/marginal/failing, and
Prometheus exposes the current gauges for external alerting, but **the UI gives
no sense of how a route (or the fleet) has been trending over the week.** A
route that flapped red overnight and recovered shows only green today. This
plan closes that gap.

The key enabler is that **evaluation is a pure, deterministic query over
`packet_path_hops`** (`evaluate_route`, `collector/routes.py:341`), and those
hop rows are retained for 7 days by default (`RAW_PACKET_RETENTION_DAYS=7`,
cascade-deleted with `raw_packets` per `cleanup.py:118-121`). Re-running the
matcher per calendar day reconstructs the daily quality band without storing
anything new. The compute cost is trivial relative to existing load — the
background evaluator already runs N evaluations every 60 s (~1440N/day); a 7-day
on-demand chart is 7N evaluations served behind the Redis cache.

The dashboard packet-breakdown charts (`20260704-1429-packet-breakdown-charts`,
shipped as `createStackedBarChart` in `charts.js:243`) established the exact
patterns this plan mirrors: a cached aggregation endpoint, a `BreakdownBucket`-
style schema, and a stacked-bar Chart.js helper.

## Goals

- Surface 7-day route health **without a migration or new persistence** —
  compute-on-read over the existing `packet_path_hops` index.
- Add a **fleet distribution chart** on the Routes overview: vertical stacked
  bars per day, x-axis = 7 dates, segments = count of routes per quality band.
- Add a **per-route status strip** in the detail expand: a single horizontal
  bar, 7 day-segments, each colored by that day's quality band (the uptime-bar
  idiom).
- Make the history horizon **track `RAW_PACKET_RETENTION_DAYS` automatically**
  so operators who raise retention get a wider window for free.
- Reuse the existing Chart.js v4 vendoring, the `ChartColors`/date infrastructure
  in `charts.js`, and the `@cached` dashboard-cache pattern — no new frontend
  dependencies and no new caching plumbing.

## Non-Goals

- **No `route_result_history` table.** Persisted history is explicitly deferred
  to a future plan. Compute-on-read is capped at the raw-packet retention window
  (default 7 days); if operators later need longer history, the persist-history
  table is the follow-on (the matching engine is already structured to append).
- **No range picker.** The window is fixed at 7 days. A configurable 7/14/30-day
  selector only becomes meaningful once the persist-history table exists (since
  compute-on-read cannot exceed `RAW_PACKET_RETENTION_DAYS`).
- **No changes to the 60-second evaluator hot path.** History is computed by a
  sibling function; `evaluate_route` and `upsert_route_result` are untouched.
- **No Prometheus changes.** The existing `meshcore_route_quality` /
  `meshcore_route_healthy` gauges already expose current state; this plan adds
  no new metrics (history is a UI concern, not an alerting one).
- **No sub-day granularity.** One quality band per day per route. Finer buckets
  (4h/3h) were considered and rejected — they multiply the evaluation cost and
  add visual noise without changing the alerting story.
- **No seeding or config changes** — the feature reads only existing route
  configuration and hop data.

## Requirements

### Functional Requirements

- **FR-1 — Fleet history endpoint.** `GET /api/v1/routes/history?days=7` returns
  a `RouteFleetHistory` payload: one `RouteFleetDayPoint` per calendar day in
  the window, each carrying per-band counts of routes:
  ```json
  {
    "days": 7,
    "data": [
      { "date": "2026-07-09", "clear": 4, "marginal": 1, "failing": 0,
        "no_coverage": 1, "disabled": 2 },
      ...
    ]
  }
  ```
  Each enabled route contributes to exactly one band per day based on its
  `RouteQuality` (clear / marginal / failing / unknown — the `unknown` band is
  labelled "no_coverage" in the chart, matching the existing UI at
  `routes.js:51-68`). Disabled routes contribute to the `disabled` counter for
  every day and are **not** evaluated.

- **FR-2 — Per-route history endpoint.** `GET /api/v1/routes/{route_id}/history
  ?days=7` returns a `RouteHistory` payload — one `RouteDayQuality` per day:
  ```json
  {
    "route_id": "...",
    "days": 7,
    "data": [
      { "date": "2026-07-09", "quality": "clear", "state": "healthy",
        "matched_count": 12 },
      ...
    ]
  }
  ```
  The `quality` value is one of the `RouteQuality` enum values: `clear` /
  `marginal` / `failing` / `unknown`. For a disabled route, every day's
  `state` is `no_coverage` and `quality` is `unknown` (consistent with how the
  list endpoint renders disabled routes).

- **FR-3 — Window semantics.** `days` defaults to 7 and is **clamped to
  `settings.effective_raw_packet_retention_days`** so the endpoint never claims
  a horizon the retained hop data cannot satisfy. The oldest complete day is
  `today - days`; each day-bucket covers `[00:00, next 00:00)` UTC. The fleet
  overview chart **excludes today** (partial day, consistent with dashboard
  daily-activity charts at `dashboard.py:462-467`); the per-route detail strip
  **includes today** as its final segment (route health is a live concern —
  seeing the current partial-day state is the point) labeled with the locale's
  "today".

- **FR-4 — Visibility scoping.** Both endpoints are role-scoped exactly like the
  existing route endpoints (`VISIBILITY_LEVELS` + `get_max_visibility_level`,
  per `api/routes/routes.py:226-229`). The fleet endpoint counts only routes
  the caller may read; the per-route endpoint returns 404 for routes above the
  caller's level (matching `get_route`'s posture). Both are guarded by
  `RequireRead`.

- **FR-5 — Caching.** Both endpoints are Redis-cached under
  `redis_cache_ttl_dashboard` via the existing `@cached` decorator, keyed by the
  existing `_routes_key_builder` (role + sorted query string, at
  `api/routes/routes.py:44`) so the per-role visibility scoping is part of the
  cache key.

- **FR-6 — Fleet chart (overview).** On the `/routes` page, when
  `features.routes !== false`, a chart card renders **vertical stacked bars**:
  x-axis = the 7 day labels, one dataset per band (clear / marginal / failing /
  no_coverage / disabled), `scales.x.stacked = true` and
  `scales.y.stacked = true`, `y.beginAtZero = true`. Legend lists the bands in
  fixed semantic order. Tooltip (index mode) lists the non-zero bands for the
  hovered day with their counts.

- **FR-7 — Status strip (detail).** In the route card expand, a chart renders
  **one horizontal bar divided into 7 equal day-segments**, each segment colored
  by that day's `quality` band (clear=green, marginal=amber, failing=red,
  no_coverage/unknown=grey). The strip has a date axis beneath it (oldest →
  newest, left → right) and today's segment labeled. Tooltip per segment shows
  the date, the quality label, and `matched_count`.

- **FR-8 — Empty / no-data handling.** If no routes are visible to the caller,
  the fleet chart card renders with a blank canvas and a "no routes" state
  (mirroring `createLineChart`'s empty-data early return at `charts.js:155`).
  If a single route has no retained hops for the full window (e.g. created
  recently), its strip renders with all segments in the `unknown` band color.

- **FR-9 — Feature gating.** Both the frontend charts and the data fetch are
  gated on `features.routes !== false` (client-side, the same idiom the routes
  page nav/route registration uses in `app.js`). The endpoints themselves carry
  only `RequireRead` (no server-side feature flag) — consistent with how the
  dashboard breakdown endpoint relates to `feature_packets`.

### Technical Requirements

- **TR-1 — Day-bounded evaluation helper.** Add
  `evaluate_route_day(session, route, day_start, day_end) -> tuple[str, str,
  int]` to `collector/routes.py` as a sibling of `evaluate_route`
  (`collector/routes.py:341`). It mirrors `evaluate_route` exactly but bounds
  the candidate fetch to `received_at >= day_start AND received_at < day_end`
  (the current function only takes a `since`). Reuse the existing private
  helpers unchanged: `_route_expected_hashes(route)`,
  `fetch_candidate_paths(...)` (extended with an optional `until` param that
  appends `PacketPathHop.received_at < until` to the subquery at line 262 —
  the composite index `ix_packet_path_hops_node_hash_received_at` covers this
  range scan), `_fetch_candidate_paths_maybe_bidirectional(...)` (extended to
  pass `until` through to `fetch_candidate_paths`), `_match_hops(...)`,
  `effective_degraded_threshold(route)`, `derive_quality(state, matched_count,
  threshold, effective_degraded)` (`routes.py:61`), and
  `_has_any_hops_in_window(...)` (extended with `until`). Implementing it as a
  sibling (not a flag on `evaluate_route`) keeps the 60-second hot path
  untouched and avoids regressions in the shipped evaluator.

- **TR-2 — History batch helper.** Add
  `evaluate_route_history(session, route, days, *, include_today=False) ->
  list[tuple[date, str, str, int]]` to `collector/routes.py`. It computes the
  day boundaries (UTC midnight buckets, oldest first) and calls
  `evaluate_route_day` per day. For a disabled route it returns
  `(date, RouteQuality.UNKNOWN.value, RouteState.NO_COVERAGE.value, 0)`
  for every day without hitting the DB. This is the single function both
  endpoints call.

- **TR-3 — Schemas.** Add to `common/schemas/routes.py` (mirroring the
  `DailyActivity` / `BreakdownBucket` idioms in `common/schemas/messages.py`):
  ```python
  class RouteDayQuality(BaseModel):
      date: date
      quality: str
      state: str
      matched_count: int

  class RouteHistory(BaseModel):
      route_id: str
      days: int
      data: list[RouteDayQuality]

  class RouteFleetDayPoint(BaseModel):
      date: date
      clear: int = 0
      marginal: int = 0
      failing: int = 0
      no_coverage: int = 0
      disabled: int = 0

  class RouteFleetHistory(BaseModel):
      days: int
      data: list[RouteFleetDayPoint]
  ```
  Use `datetime.date` (not `datetime`) for `date` fields so payloads serialize
  as `YYYY-MM-DD` with no time component. The `no_coverage` field aggregates
  all routes whose quality is `unknown` — matching the existing UI's label
  mapping at `routes.js:51-68`.

- **TR-4 — Fleet endpoint.** Add to `api/routes/routes.py` on the existing
  router (already mounted at `/api/v1/routes`):
  ```python
  @router.get("/history", response_model=RouteFleetHistory)
  @cached("routes/history", ttl_setting="redis_cache_ttl_dashboard",
          key_builder=_routes_key_builder)
  def get_route_fleet_history(
      _: RequireRead,
      session: DbSession,
      request: Request,
      days: int = 7,
  ) -> RouteFleetHistory:
  ```
  Load the routes visible to the caller's role (reuse the visibility filter
  from `get_routes`). Clamp `days = min(days, retention_days)` where
  `retention_days` comes from `settings.effective_raw_packet_retention_days`.
  For each enabled route call `evaluate_route_history(session, route, days,
  include_today=False)`; bucket each day's quality into the band counters
  (quality `unknown` → `no_coverage`, matching the existing UI mapping at
  `routes.js:51-68`). Disabled routes add to `disabled` for every day.
  Return oldest-day-first.
  **Route ordering note:** this endpoint must be declared **before** the
  `/{route_id}` path routes so FastAPI does not match `history` as a
  `route_id` path parameter.

- **TR-5 — Per-route endpoint.** Add to `api/routes/routes.py`:
  ```python
  @router.get("/{route_id}/history", response_model=RouteHistory)
  @cached("routes/{id}/history", ttl_setting="redis_cache_ttl_dashboard",
          key_builder=_routes_key_builder)
  def get_route_history(
      _: RequireRead,
      session: DbSession,
      route_id: str,
      request: Request,
      days: int = 7,
  ) -> RouteHistory:
  ```
  Fetch the route, apply the visibility check (mirror `get_route` at lines
  220–229 — 404 when not found or above caller's level), clamp `days = min(days,
  settings.effective_raw_packet_retention_days)`, call
  `evaluate_route_history(session, route, days, include_today=True)`.

- **TR-6 — Quality color tokens.** Add a semantic `quality` map to
  `ChartColors` in `charts.js` (alongside the existing `breakdown` palette at
  lines 56–64). Use hardcoded oklch values — the same approach the `breakdown`
  palette uses — rather than CSS custom properties, since `app.css` defines only
  page/section colors (`--color-nodes`, `--color-routes`, etc.) and no
  semantic status colors. The values render consistently in both light and dark
  themes:
  ```js
  quality: {
      clear:       'oklch(0.72 0.17 145)',
      marginal:    'oklch(0.75 0.18 85)',
      failing:     'oklch(0.62 0.24 25)',
      no_coverage: 'oklch(0.65 0.15 250)',   // info-blue
      disabled:    'oklch(0.55 0 0)',        // neutral grey
  }
  ```

- **TR-7 — Fleet chart helper.** Add `createRouteOverviewChart(canvasId,
  fleetData)` to `charts.js`. `type: 'bar'` (vertical), labels =
  `formatDateLabels(fleetData.data)` (reuses the existing helper at
  `charts.js:137`). One dataset per band in fixed semantic order (clear,
  marginal, failing, no_coverage, disabled), each with `data` = per-day count
  and `backgroundColor` = the band's `ChartColors.quality` color.
  `scales.x.stacked = true`, `scales.y.stacked = true`,
  `scales.y.beginAtZero = true`. Reuse `createChartOptions(true)` for legend/
  tooltip theming, overriding the tooltip `label` callback to list non-zero
  bands per hovered day. Return `null` on empty/no-routes data (matching
  `createLineChart`'s idiom).

- **TR-8 — Status strip helper.** Add `createRouteDetailStrip(canvasId,
  routeData)` to `charts.js`. Produces a single horizontal bar of 7 equal
  colored segments:
  - `type: 'bar'`, `indexAxis: 'y'`, `labels: ['']` (one row).
  - One dataset per day: `{ label: <date>, data: [1], backgroundColor:
    ChartColors.quality[day.quality]() }`. With `scales.x.stacked = true` and
    `scales.y.stacked = true`, the seven unit-width datasets render as one bar
    split into seven equal colored segments.
  - Hide both axes' ticks; render a date-axis row beneath the canvas via a
    separate labels element (HTML, not Chart.js) so the dates align under each
    segment without Chart.js category-axis clutter.
  - Tooltip per segment: date + quality label + `matched_count`.
  - Return `null` when `routeData` is empty.

- **TR-9 — Overview wiring.** In `spa/pages/routes.js`, add a chart card
  containing `<canvas id="routeOverviewChart">` adjacent to the existing
  summary strip (`renderSummaryStrip`, `routes.js:51`). After the routes list
  loads in `renderPage`, fire `apiGet('/api/v1/routes/history', { days: 7 },
  { signal })` and call `createRouteOverviewChart`. Manage the Chart.js
  instance lifecycle — create a `chartIds` array and return a cleanup function
  that destroys each instance on page unmount, mirroring the dashboard page's
  chart cleanup pattern at `dashboard.js:324-333`. Include abort support via
  `{ signal }` for fetch cancellation on page unmount.

- **TR-10 — Detail wiring.** In `spa/pages/routes.js`, inside the expanded-card
  detail content (`renderDetailContent`), add a `<canvas>` and fetch
  `/api/v1/routes/${route.id}/history?days=7`, then call
  `createRouteDetailStrip`. Render only when the card is expanded, matching the
  existing lazy-load pattern used for the `detail` payload. Destroy the strip
  instance when the card collapses.

- **TR-11 — i18n.** Add keys under the existing `routes.*` block to both
  `src/meshcore_hub/web/static/locales/en.json` and `nl.json`:
  - `routes.history_title` — "Health (last 7 days)" / "Gezondheid (laatste 7
    dagen)" (fleet chart card title).
  - `routes.history_detail_title` — "Last 7 days" / "Laatste 7 dagen" (strip
    label).
  - `routes.history_today` — "Today" / "Vandaag" (the final partial segment
    label on the detail strip).
  - The band labels (`routes.quality_clear`, `routes.quality_marginal`,
    `routes.quality_failing`, `routes.quality_no_coverage`,
    `routes.quality_unknown`, `routes.disabled`) already exist at
    `routes.js:24-34` and are reused for the legend and tooltips.

- **TR-12 — Backend agnosticism.** All queries use SQLAlchemy Core/ORM with
  Python-computed day boundaries (`datetime` arithmetic, never `NOW() -
  INTERVAL`), consistent with the backend-agnostic convention established by the
  Routes plan (T6). The day-bounded fetch is a simple `received_at >= day_start
  AND received_at < day_end` range — sargable on both SQLite and Postgres.

## Implementation Plan

### Phase 1: Day-bounded matching engine + tests

- **`src/meshcore_hub/collector/routes.py`**:
  - Extend `_fetch_candidate_paths_maybe_bidirectional` and
    `_has_any_hops_in_window` with an optional `until: Optional[datetime]`
    parameter that appends `PacketPathHop.received_at < until` to the existing
    `received_at >= since` filter. The composite index
    `ix_packet_path_hops_node_hash_received_at` covers the bounded range scan.
  - Add `evaluate_route_day(session, route, day_start, day_end)` per TR-1 — a
    line-for-line mirror of `evaluate_route` (`routes.py:341-389`) but calling
    the bounded fetch helpers. Reuses `_route_expected_hashes`,
    `effective_degraded_threshold`, `_match_hops`, `derive_quality` unchanged.
  - Add `evaluate_route_history(session, route, days, *, include_today=False)`
    per TR-2.
- **Tests** — extend `tests/test_collector/test_routes.py`:
  - `evaluate_route_day` returns the correct band for clear / marginal /
    failing / no_coverage (seed hops inside vs. outside the day window).
  - Day boundaries are strict: hops in the adjacent day do not leak across the
    `day_end` bound.
  - `evaluate_route_history` returns `days` entries oldest-first, with the
    correct `include_today` behavior (one extra partial-day entry when true).
  - A disabled route returns `unknown`/`no_coverage`/`0` for every day without
    a DB hit.

### Phase 2: Schemas + API endpoints + tests

- **`src/meshcore_hub/common/schemas/routes.py`**: add `RouteDayQuality`,
  `RouteHistory`, `RouteFleetDayPoint`, `RouteFleetHistory` per TR-3.
- **`src/meshcore_hub/api/routes/routes.py`**:
  - Add `GET /history` (fleet) per TR-4. **Declare it before the `/{route_id}`
    routes** (FastAPI matches path patterns in declaration order; without this,
    `history` would be captured as a `route_id`).
  - Add `GET /{route_id}/history` (per-route) per TR-5.
  - Import `evaluate_route_history` from `collector.routes`; import the new
    schemas; read `raw_packet_retention_days` from settings for the `days` clamp.
  - Visibility filtering reuses `VISIBILITY_LEVELS` / `get_max_visibility_level`
    / `resolve_user_role` already imported at the top of the file.
- **Tests** — `tests/test_api/test_routes.py`:
  - Fleet endpoint: response shape, per-day band counts sum to the visible-route
    count, disabled routes count only to `disabled`, visibility filtering (a
    low-role caller does not see admin-only routes in the counts), `days` clamp
    to `RAW_PACKET_RETENTION_DAYS`, caching (role-keyed).
  - Per-route endpoint: per-day quality/state/matched_count shape, 404 for a
    hidden route, 404 for an unknown route, includes today as the final segment.
  - Route-ordering guard: confirm `GET /history` is not shadowed by
    `GET /{route_id}`.

### Phase 3: Chart helpers + quality palette

- **`src/meshcore_hub/web/static/js/charts.js`**:
  - Add the `quality` color map to `ChartColors` (TR-6), using hardcoded oklch
    values (same approach as the `breakdown` palette at lines 56–64).
  - Add `createRouteOverviewChart(canvasId, fleetData)` (TR-7) — vertical stacked
    bars, one dataset per band.
  - Add `createRouteDetailStrip(canvasId, routeData)` (TR-8) — single horizontal
    bar, one dataset per day.
- **Manual check**: `make up`, then exercise both helpers from the browser
  console with mock data to confirm rendering (stacked scales, segment colors,
  tooltips) before wiring the SPA pages.

### Phase 4: SPA wiring + i18n

- **`src/meshcore_hub/web/static/js/spa/pages/routes.js`**:
  - Add the overview chart card + `apiGet` fetch + `createRouteOverviewChart`
    call + lifecycle management (TR-9). Create a `chartIds` array and return a
    cleanup function that destroys Chart.js instances on page unmount (mirroring
    `dashboard.js:324-333` — the routes page currently has no chart lifecycle).
  - Add the detail strip inside the expand content + lazy fetch +
    `createRouteDetailStrip` + destroy-on-collapse (TR-10).
- **i18n**: add the three new keys (TR-11) to `en.json` and `nl.json`.

### Phase 5: Verify

```bash
pytest --no-cov tests/test_collector/test_routes.py tests/test_api/test_routes.py tests/test_web/
pre-commit run --all-files
make build   # SPA bundle rebuild via Docker pipeline
make up
```
- Visually verify `/routes`: fleet chart renders with 7 stacked bars; tooltips
  list non-zero bands per day; legend in semantic order.
- Expand a route card: status strip renders 7 colored segments oldest→newest,
  today labeled, tooltips show date + band + matched_count.
- Empty-state: no visible routes → blank canvas + "no routes"; a route with no
  hops in window → all-grey strip.
- Role scoping: log in as a low-role user and confirm the fleet counts and the
  per-route 404 reflect visibility.

## Open Questions

- **"Today" in the overview.** The plan excludes today from the fleet overview
  (consistency with dashboard daily-activity charts, which use complete days)
  but includes it on the detail strip (live-health concern). If the inconsistency
  reads awkwardly, the simplest reconciliation is to include today in both
  (partial-day bars are acceptable for a status board whose purpose is
  at-a-glance current state). Decide during implementation review.
- **Status-strip date axis.** TR-8 proposes an HTML date row beneath the canvas
  rather than a Chart.js category axis, to avoid clutter on a single-row chart.
  If that proves fiddly to align, an acceptable fallback is a Chart.js category
  x-axis with `ticks.maxRotation: 0` and `maxTicksLimit: 7`. Pick whichever
  aligns cleanly during the Phase 3 manual check.
- **Cache staleness.** Both history endpoints are cached under
  `redis_cache_ttl_dashboard` (default 30 s). A route config change
  (threshold / window / nodes / enabled) will serve stale daily evaluations for
  up to one TTL window until the cache expires naturally — the same behaviour as
  the dashboard activity endpoints. No explicit invalidation is needed for the
  initial implementation; if the 30 s lag becomes noticeable in practice, a
  simple invalidation call on the route CRUD endpoints (create/update/delete)
  can be added later.

## References

- `docs/plans/20260705-2306-mesh-link-monitoring/plan.md` — the Routes feature
  this extends. Defines `Route`/`RouteResult`/`packet_path_hops`, the
  `evaluate_route` engine, the 60-second evaluator, the quality bands (F4), and
  explicitly lists "historical route-health time series" as a Non-Goal (future
  work) — this plan delivers that future work via compute-on-read.
- `docs/plans/20260704-1429-packet-breakdown-charts/plan.md` — the cached
  aggregation endpoint + `createStackedBarChart` + `BreakdownBucket` schema +
  `ChartColors.breakdown` palette patterns this plan mirrors for the fleet
  chart and color tokens.
- `docs/plans/20260612-2014-raw-packets-feature/plan.md` — the `raw_packets`
  table and `RAW_PACKET_RETENTION_DAYS` retention that bounds the compute-on-read
  horizon and cascade-deletes `packet_path_hops`.
- `src/meshcore_hub/collector/routes.py:341-389` — `evaluate_route`, the pure
  matching function the day-bounded sibling reimplements.
- `src/meshcore_hub/collector/routes.py:415-450` — `upsert_route_result`, the
  in-place overwrite that makes history reconstruction necessary.
- `src/meshcore_hub/common/models/packet_path_hop.py:62-66` — the
  `(node_hash, received_at)` composite index that makes the day-bounded range
  scan cheap.
- `src/meshcore_hub/collector/cleanup.py:118-121` — raw-packet cleanup that
  cascade-deletes hops, confirming `effective_raw_packet_retention_days` is the
  sole horizon bound.
- `src/meshcore_hub/api/routes/dashboard.py:442-510` — `get_packet_breakdown`,
  the cached-aggregation precedent.
- `src/meshcore_hub/web/static/js/charts.js:36-65,137,243-312` — `ChartColors`,
  `formatDateLabels`, and `createStackedBarChart`, the infrastructure reused.
- `src/meshcore_hub/web/static/js/spa/pages/routes.js:51-68` — `renderSummaryStrip`,
  the natural neighbor for the fleet chart card.
- Recent git history (`main`): `14fbc45` route health monitoring, `0e202b3`
  reversible route matching, `1ee01a6` from/to endpoint labels, `ae22dff` test
  determinism — the Routes work this plan builds on.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-15

### Resolutions

- **6-band fleet schema reduced to 5 bands.** The plan originally listed clear /
  marginal / failing / `no_coverage` / `unknown` / disabled (6 bands), but the
  `RouteQuality` enum (`route_result.py:24-30`) only has 4 values: `clear`,
  `marginal`, `failing`, `unknown`. The `no_coverage` is a `RouteState`, not a
  `RouteQuality`. The plan now uses 5 bands (clear / marginal / failing /
  no_coverage / disabled), where `no_coverage` maps to `quality=unknown` —
  matching the existing UI's label scheme at `routes.js:51-68`. The `unknown`
  field was removed from `RouteFleetDayPoint`.

- **Quality colors use hardcoded oklch values.** The original TR-6 attempted to
  read CSS custom properties (`--color-success`, `--color-warning`,
  `--color-error`, `--color-info`) via `getCSSColor()`. Those variables do not
  exist in `app.css :root` (which defines only page/section colors like
  `--color-nodes`, `--color-routes`, etc.). The `ChartColors.quality` map now
  uses hardcoded oklch values — the same approach the existing `breakdown`
  palette uses at `charts.js:56-64`, which renders consistently across light and
  dark themes.

- **Config attribute corrected to `effective_raw_packet_retention_days`.** The
  plan originally referenced `Settings.raw_packet_retention_days` (`Optional[int]`,
  can be `None`). The correct attribute is `settings.effective_raw_packet_retention_days`
  (`config.py:334-339`), the computed `int` property that falls back to
  `data_retention_days` when `raw_packet_retention_days` is `None`.

- **`fetch_candidate_paths` propagation clarified.** TR-1 now explicitly notes
  that the `until` parameter must be added to `fetch_candidate_paths` (where the
  SQL WHERE clause lives at `routes.py:262`), not only to its wrapper
  `_fetch_candidate_paths_maybe_bidirectional`. Both functions need the `until`
  parameter for the bounded day query.

- **Chart lifecycle pattern specified.** The routes page has no existing chart
  cleanup infrastructure. TR-9 and Phase 4 now explicitly instruct creating a
  `chartIds` array and returning a cleanup function that calls
  `Chart.getChart(id).destroy()` on page unmount, mirroring the dashboard page's
  pattern at `dashboard.js:324-333`.

- **Cache staleness risk acknowledged.** Added as an Open Question: history
  endpoints serve stale results for up to `redis_cache_ttl_dashboard` (default
  30 s) after route config changes. Same behaviour as the dashboard activity
  endpoints. Explicit invalidation on route CRUD endpoints is noted as a
  potential follow-up.

- **No plan-plan conflicts.** The observer-area-filters plan
  (`20260707-2157-observer-area-filters`) does not touch `routes.js`; no overlap
  with this plan's changes.

### Remaining Action Items

- Resolve "Today in the overview" question during Phase 4 implementation —
  exclude today (complete days) or include today (partial day) on the fleet
  chart.
- Choose status-strip date axis approach during Phase 3 manual check (HTML row
  vs. Chart.js category axis).
