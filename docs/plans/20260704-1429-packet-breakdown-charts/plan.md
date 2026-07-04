# Dashboard Packet Breakdown Charts

## Summary

Add two new chart cards to the Dashboard page, both gated behind the existing
`packets` feature flag (alongside today's daily "Packets received" line chart),
that visualize the **composition** of raw packet volume over the last 7 days
rather than its day-by-day trend:

1. **Packet Event Type** — a horizontal 100% stacked bar showing the share of each
   `event_type` value (`advertisement`, `channel_msg_recv`, `req`, `ack`, …),
   rendered as the top 6 buckets with the long tail rolled into an "other"
   segment.
2. **Path Hash Width** — a horizontal 100% stacked bar showing the share of the
   three known path-hash byte widths (`1b` / `2b` / `3b`), explicitly **excluding
   unavailable (NULL)** widths.

Both charts are driven by a single new aggregation endpoint,
`GET /api/v1/dashboard/packet-breakdown?days=7`, returning pre-bucketed counts
that the frontend normalizes into percentages and renders via Chart.js v4's
horizontal stacked-bar mode (`type: 'bar'`, `indexAxis: 'y'`, `stacked: true`).

## Background & Motivation

The dashboard's Packets card (shipped in `20260703-1330-dashboard-packets-widget`)
shows only **volume over time** — a 7-day daily line chart and a `packets_7d`
headline number. It tells the operator *how much* traffic is flowing but nothing
about *what kind*. On a busy mesh, raw-packet volume is often the highest-signal
feed, and the two composition questions operators ask most are:

- **What mix of packet types am I seeing?** (advertisements vs. channel messages
  vs. req/ack/control traffic vs. undecryptable noise). The `event_type` column
  on `RawPacket` already encodes this at ingest (see
  `collector/letsmesh_normalizer.py`), but it is surfaced only as a row-level
  field and a list filter on `/packets` — never aggregated.
- **How wide are the path-hash prefixes on air?** The `path_hash_bytes` column
  (persisted in `20260703-2338-path-hash-bytes-filter`) records the widest
  path-hash prefix width (1/2/3 bytes) per reception. Its distribution is a
  direct proxy for the on-air mix of short vs. long mesh routes, but today it is
  only filterable on the `/packets` list page — never summarized.

Both columns are already indexed and queryable; the gap is purely that **no
endpoint returns counts grouped by these dimensions**, and **no dashboard chart
visualizes them**. This plan closes that gap with one endpoint and two charts,
reusing the entire Packets feature-flag scaffolding (flag, color, icon, gating
idiom) that already exists.

Recent git history shows sustained dashboard/UI polish work
(`5dbf069` path popover scroll, `f3a2fe7` mobile landscape grid, `c029eae`
`path_hash_bytes` column, `215690f` packets widget) — this plan continues that
direction by deepening the Packets card from a single trend line into a
three-panel composition view.

## Goals

- Add a `GET /api/v1/dashboard/packet-breakdown` endpoint that returns 7-day
  counts bucketed by `event_type` (top 6 + "other") and by `path_hash_bytes`
  (1b/2b/3b, NULL excluded), cached and gated consistently with the existing
  `/packet-activity` endpoint.
- Add a reusable Chart.js horizontal 100% stacked-bar chart helper to
  `charts.js`, with a percentage axis and raw-count tooltips.
- Render two new dashboard chart cards ("Packet event types" and "Path hash
  width"), visible only when `features.packets !== false`, laid out in a new
  2-column grid row below the existing 4-card trend grid.
- Reuse all existing Packets feature-flag plumbing — no new flags, colors,
  icons, or migrations.

## Non-Goals

- No changes to the `/packets` browse page, `/packet-groups` endpoint, or any
  list/detail payload schema. The new endpoint is read-only aggregation.
- No new database migration, model column, or index — reads only from existing
  `raw_packets.event_type` and `raw_packets.path_hash_bytes` columns.
- No new feature flag or config variable. The `feature_packets` flag (default
  `True`) gates both charts exactly as it gates the daily Packets line chart.
- No role/channel-visibility filtering on the breakdown counts — consistent with
  `/packet-activity` (observer-level volume metric; payload redaction stays on
  list/detail endpoints).
- No per-day / trend version of the breakdowns (single 7-day snapshot only).
- No SCHEMAS.md update (the new endpoint is dashboard-internal; documented via
  its OpenAPI summary, as `/packet-activity` is).

## Requirements

### Functional Requirements

- **FR-1** — `GET /api/v1/dashboard/packet-breakdown?days=7` returns a
  `PacketBreakdown` payload:
  ```json
  {
    "days": 7,
    "by_event_type": [{"label": "advertisement", "count": 1234}, …, {"label": "other", "count": 56}],
    "by_path_width": [{"label": "1b", "count": 100}, {"label": "2b", "count": 200}, {"label": "3b", "count": 50}]
  }
  ```
- **FR-2** — `by_event_type` contains the **top 6** `event_type` values by count
  descending, plus a final `{"label": "other", "count": <sum>}` bucket rolling
  up all remaining values (including any NULL `event_type`). If the distinct
  value count is ≤ 6, no "other" bucket is emitted. Buckets with zero total
  produce an empty `by_event_type` list (and the frontend renders nothing).
- **FR-3** — `by_path_width` always contains exactly three buckets in fixed
  order — `1b`, `2b`, `3b` — zero-filling any width absent in the window. Rows
  with `path_hash_bytes IS NULL` are **excluded** from every bucket and from the
  percentage denominator (honoring the "not unavailable" requirement).
- **FR-4** — The endpoint is Redis-cached under `dashboard/packet-breakdown`
  with `redis_cache_ttl_dashboard`, role-independent (default cache key), and
  guarded by `RequireRead` — identical caching/guard posture to
  `/packet-activity`.
- **FR-5** — `days` defaults to 7 and is capped at 90, and the window **excludes
  today** (the incomplete day), matching `/packet-activity` semantics exactly.
- **FR-6** — When `features.packets !== false`, the dashboard renders two
  additional chart cards below the existing trend grid: "Packet event types"
  (`#packetEventTypeChart`) and "Path hash width" (`#packetPathWidthChart`),
  each in a 2-column grid (`lg:grid-cols-2`, single column on small screens).
- **FR-7** — When `features.packets === false`, neither card is rendered, the
  breakdown endpoint is not fetched, and the existing trend grid layout is
  unchanged.
- **FR-8** — Both new charts render as horizontal 100% stacked bars: segments
  sized proportionally to `count / total * 100`, a `0–100%` x-axis, and
  tooltips showing the raw count (and percentage) for the hovered segment.
- **FR-9** — Each card header follows the existing Packets card idiom: entity
  icon, title, subtitle ("last 7 days"), and a headline number in the entity
  accent color. Headline for event-type card = sum of all `by_event_type`
  counts (total packets in window, excluding NULLs in the "other" bucket but
  including the "other" total); headline for path-width card = sum of all
  `by_path_width` counts (packets with a known width, i.e. the percentage
  denominator). Both totals are computed from the breakdown response and
  passed to `renderChartCards` alongside `stats`.
- **FR-10** — Empty breakdown (zero packets in window) renders gracefully: the
  cards still appear with their headline showing `0`, and the canvas is left
  blank (the chart helper returns `null`, matching `createLineChart`'s
  empty-data early return at `charts.js:144-146`).

### Technical Requirements

- **TR-1** — New Pydantic schemas in `common/schemas/messages.py` (alongside
  `DailyActivity`):
  ```python
  class BreakdownBucket(BaseModel):
      label: str
      count: int

  class PacketBreakdown(BaseModel):
      days: int
      by_event_type: list[BreakdownBucket]
      by_path_width: list[BreakdownBucket]
  ```
- **TR-2** — New endpoint in `api/routes/dashboard.py`, placed immediately after
  `get_packet_activity` (line 432). Signature and decorators mirror
  `get_packet_activity` exactly:
  ```python
  @router.get("/packet-breakdown", response_model=PacketBreakdown)
  @cached("dashboard/packet-breakdown", ttl_setting="redis_cache_ttl_dashboard")
  def get_packet_breakdown(
      _: RequireRead,
      session: DbSession,
      request: Request,
      days: int = 7,
  ) -> PacketBreakdown:
      ...
  ```
  Body reuses the same date-window math (`days = min(days, 90)`,
  `end_date = today at 00:00 UTC`, `start_date = end_date - timedelta(days=days)`,
  `received_at >= start_date AND received_at < end_date`).
- **TR-3** — Event-type query (single statement):
  ```python
  select(RawPacket.event_type, func.count().label("count"))
  .where(received_at in window)
  .group_by(RawPacket.event_type)
  .order_by(func.count().desc())
  ```
  Python then takes the first 6 rows verbatim and sums the remainder (including
  a NULL `event_type` group, if present) into one `{"label": "other", ...}`
  bucket. When the row count is ≤ 6, "other" is omitted.
- **TR-4** — Path-width query (single statement):
  ```python
  select(RawPacket.path_hash_bytes, func.count().label("count"))
  .where(received_at in window)
  .where(RawPacket.path_hash_bytes.isnot(None))
  .group_by(RawPacket.path_hash_bytes)
  ```
  Python maps the returned rows into a fixed `[(1, "1b"), (2, "2b"), (3, "3b")]`
  order, zero-filling any missing width. This guarantees a stable legend/order
  regardless of which widths happen to be present.
- **TR-5** — No new feature gate at the route layer. The endpoint inherits
  `RequireRead` only — consistent with `/packet-activity`, which has no extra
  `feature_packets` guard (the flag is enforced client-side via card visibility
  and via nav/route registration in `app.js`). If a deployment disables
  `feature_packets`, the endpoint remains callable directly but is simply never
  requested by the dashboard.
- **TR-6** — `charts.js` gains a `createStackedBarChart(canvasId, buckets,
  colors)` helper (no `options` parameter — builds its own internally, mirroring
  `createLineChart` which also builds options internally via
  `createChartOptions`):
  - `type: 'bar'`, `indexAxis: 'y'`, single y-label.
  - One dataset per bucket, `backgroundColor: colors[i]`, `borderColor:
    colors[i]`, `borderWidth: 1`.
  - Data values pre-normalized to percentages (`count / total * 100`); the
    chart's own stacking therefore sums to ~100 (floating-point rounding may
    produce 99.9–100.1; Chart.js stacking tolerates this visually).
  - Own options object (NOT reusing `createChartOptions` — that is designed for
    vertical line charts with date-rotated x-axis and `beginAtZero` y-axis):
    `scales.x.max = 100`, `scales.x.stacked = true`, `scales.y.stacked = true`,
    x-axis tick callback appends `%`; y-axis ticks hidden (single bar);
    `interaction.mode = 'nearest'` (since a single stacked bar has one y-tick,
    the user hovers a specific segment, not an x-position).
  - Tooltip `label` callback renders `<label>: <count> (<pct>%)` using
    `formatNumber` (already available at `charts.js:19`) and the raw count
    stashed on each dataset (e.g. `dataset.rawCount`).
  - Returns `null` when `buckets` is empty/`null` or `total === 0` (matches the
    `createLineChart` early-return idiom).
- **TR-7** — `ChartColors` (`charts.js`) gains a `breakdown` palette: a
  hardcoded ordered array of 7 distinct hues (top 6 + "other"; "other"
  rendered `oklch(0.55 0 0)` neutral grey). The path-width chart reuses the
  first three hues of the same palette. Hardcoded oklch colors are
  legible in both light and dark themes without adding CSS custom
  property tokens to `app.css`. The palette lives alongside the existing
  hardcoded colors (`ChartColors.grid`, `ChartColors.text`, etc.) at
  `charts.js:47-51`.
- **TR-8** — `initDashboardCharts` (`charts.js`, line 225) signature is extended
  with two trailing params (`eventTypeData`, `pathWidthData`). When truthy and
  non-empty, it calls `createStackedBarChart('packetEventTypeChart', ...)` and
  `createStackedBarChart('packetPathWidthChart', ...)`. The existing four line
  charts are untouched.
- **TR-9** — `dashboard.js` `renderChartCards()` emits a **second grid** after
  the closing `</div>` of the existing trend grid (line 210), gated on
  `showPackets`. The function signature is extended to accept a
  `packetBreakdown` parameter (containing `{by_event_type, by_path_width}`),
  from which headline totals are computed:
  ```js
  const eventTypeTotal = packetBreakdown?.by_event_type?.reduce((s, b) => s + b.count, 0) ?? 0;
  const pathWidthTotal = packetBreakdown?.by_path_width?.reduce((s, b) => s + b.count, 0) ?? 0;
  ```
  ```js
  ${showPackets ? html`
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-8">
      <div class="card …" style="--panel-color: var(--color-packets)">
          … headline = ${formatNumber(eventTypeTotal)} …
          … #packetEventTypeChart …
      </div>
      <div class="card …" style="--panel-color: var(--color-packets)">
          … headline = ${formatNumber(pathWidthTotal)} …
          … #packetPathWidthChart …
      </div>
  </div>` : nothing}
  ```
  The existing `gridCols(visibleCount)` logic for the trend grid is unchanged
  (it still counts only nodes/adverts/messages/packets). Putting the breakdowns
  in their own 2-col row avoids cramming 6 cards into a 4-col grid and gives
  the composition view its own visual band.
- **TR-10** — `dashboard.js` `render()`:
  - Add `/api/v1/dashboard/packet-breakdown?days=7` to the `Promise.all`
    destructuring (line 224), with `{ signal }` for abort support (same
    pattern as existing apiGet calls).
  - After the Promise.all resolves, compute headline totals from the breakdown
    response and pass `packetBreakdown` to `renderChartCards` so the card
    headlines can display the correct window totals (see TR-9).
  - Pass `showPackets ? packetBreakdown.by_event_type : null` and
    `showPackets ? packetBreakdown.by_path_width : null` as the two new
    trailing args to `window.initDashboardCharts(...)` (line 267).
  - Add `'packetEventTypeChart'` and `'packetPathWidthChart'` to the chart
    cleanup `chartIds` array (line 274–283) so they are destroyed on page
    unmount alongside the existing four.
- **TR-11** — i18n keys added to both
  `src/meshcore_hub/web/static/locales/en.json` and
  `src/meshcore_hub/web/static/locales/nl.json`, under the existing
  `entities` and `packets` namespaces:
  - `entities.packet_event_types` — English: "Packet event types" / Dutch:
    "Packet gebeurtenistypen"
  - `entities.path_hash_width` — English: "Path hash width" / Dutch:
    "Pad-hashbreedte"
  - `packets.breakdown_other` — English: "Other" / Dutch: "Overig" (the
    rolled-up tail bucket label; also used as the dataset label so tooltips
    are localized).
  - The "last 7 days" subtitle uses `time.last_7_days` (exists in both locales
    as "Last 7 days" / "Laatste 7 dagen"), since the breakdown is a single
    7-day snapshot, not a per-day series.

## Implementation Plan

### Phase 1: Backend — breakdown endpoint

- **`common/schemas/messages.py`**: add `BreakdownBucket` and `PacketBreakdown`
  as specified in TR-1, placed immediately after `DailyActivity` / its point
  schema.
- **`api/routes/dashboard.py`**:
  - `RawPacket` is already imported (added by the packets-widget plan).
  - Add `get_packet_breakdown` after `get_packet_activity` (line 432) per TR-2.
  - Implement the two grouped queries (TR-3, TR-4) and the Python
    top-6 + "other" rollup for event types and the fixed-order zero-fill for
    path widths.
  - Reuse the exact date-window math from `get_packet_activity` (TR-2).
- **Tests** — `tests/test_api/test_dashboard.py`: add a `TestPacketBreakdown`
  class (or extend the existing dashboard test module). Fixtures:
  - Seed one observer `Node` and a spread of `RawPacket` rows across the last
    7 days with: (a) ≥ 8 distinct `event_type` values to exercise the top-6 +
    "other" rollup (assert the 7th-and-beyond values sum into "other"); (b)
    rows with `path_hash_bytes` of 1, 2, 3, and NULL (assert NULL is excluded
    and the denominator reflects only 1+2+3); (c) at least one row dated
    "today" to assert today is excluded from the window.
  - Assert response shape, bucket ordering, zero-fill of a missing width, and
    that the `@cached` key is role-independent (mirror the existing
    `/packet-activity` test's caching assertion if one exists).

### Phase 2: Frontend — chart helper & palette

- **`charts.js`**:
  - Add a hardcoded `breakdown` palette to `ChartColors` (TR-7) — an ordered
    array of 7 oklch hues alongside the existing hardcoded colors (grid, text,
    etc.).
  - Add `createStackedBarChart(canvasId, buckets, colors)` per TR-6, building
    its own options object internally (not reusing `createChartOptions`).
  - Extend `initDashboardCharts` with the two trailing params and the two new
    `createStackedBarChart` calls (TR-8).
- **Manual unit check**: instantiate the helper against a hardcoded bucket
  array in the browser console (`make up`, then `window.initDashboardCharts`
  with mock data) to confirm the horizontal stacked bar renders with a 0–100%
  axis and proportional segments before wiring the dashboard.

### Phase 3: Frontend — dashboard cards & data wiring

- **`spa/pages/dashboard.js`**:
  - `renderChartCards`: accept a new `packetBreakdown` parameter; compute
    `eventTypeTotal` and `pathWidthTotal` from it; add the second grid + two
    cards per TR-9. Both cards reuse `iconPackets`, the `--color-packets`
    accent, and the established header flex-row idiom.
  - `render`: extend `Promise.all` destructuring with
    `apiGet('/api/v1/dashboard/packet-breakdown', { days: 7 }, { signal })`
    (TR-10); pass `packetBreakdown` to `renderChartCards` for headline
    computation; pass the two breakdown arrays into `initDashboardCharts`;
    extend the cleanup array.
- **i18n**: add the three new keys (TR-11) to
  `src/meshcore_hub/web/static/locales/en.json` and
  `src/meshcore_hub/web/static/locales/nl.json`.

### Phase 4: Verify

- `pytest --no-cov tests/test_api/test_dashboard.py tests/test_web/`
- `pre-commit run --all-files`
- `make build` (SPA bundle rebuild — must go through the Docker build pipeline;
  local `node build.js` fails on a missing fontsource asset, per the prior
  plan's note).
- `make up`, then visually verify `/dashboard` with `FEATURE_PACKETS=true`:
  - Trend grid unchanged (4 cards on large screens).
  - New 2-col row below shows both stacked bars with proportional segments.
  - Tooltips show raw counts and percentages.
  - Empty-data path (no packets in window) shows the cards with `0` headline
    and a blank canvas.
  - With `FEATURE_PACKETS=false`: neither the trend Packets card nor the new
    breakdown cards render; the breakdown endpoint is not requested
    (confirm in the network tab).

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-04

### Resolutions

- **Headline data source**: `renderChartCards` accepts a `packetBreakdown`
  parameter so card headlines can display accurate window totals computed from
  the breakdown response (sum of all `by_event_type` counts for the event-type
  card; sum of all `by_path_width` counts for the path-width card).
- **Color palette**: Hardcoded 7-hue qualitative palette in `ChartColors`
  within `charts.js` — no new CSS custom property tokens in `app.css`.
  Hardcoded oklch colors are legible in both light and dark themes.
- **Locale coverage**: Full translations for both `en.json` and `nl.json`
  (three new keys each). Dutch values: "Packet gebeurtenistypen",
  "Pad-hashbreedte", "Overig".
- **`createStackedBarChart` options**: The helper builds its own options object
  internally (no `options` parameter) — does NOT reuse the vertical line-chart
  `createChartOptions` helper. Interaction mode `'nearest'` since the single
  stacked bar has one y-tick.
- **i18n file path**: Corrected from `…/js/spa/i18n/locales/` to
  `src/meshcore_hub/web/static/locales/` (matching `docs/i18n.md`).
- **Subtitle key**: Uses `time.last_7_days` ("Last 7 days") — the breakdown is
  a single snapshot, not a per-day series.
- **Headline number choice**: Count-based (total packets and known-width
  packets) — consistent with the existing card numeric headline idiom.
- **Event-type bucket count**: Locked at top 6 + "other" (confirmed in prior
  Q&A; one-line constant to tune later if needed).
- **Fetch abort support**: Breakdown apiGet call includes `{ signal }` for
  request cancellation on page unmount.

### Remaining Action Items

- None — all open questions resolved during review.

## References

- `docs/plans/20260703-1330-dashboard-packets-widget/plan.md` — the dashboard
  Packets chart this plan extends (trend grid, `initDashboardCharts` signature,
  `ChartColors.packets`, `renderChartCards` structure, `/packet-activity`
  endpoint pattern, feature-flag gating idiom).
- `docs/plans/20260703-2338-path-hash-bytes-filter/plan.md` — persists the
  `path_hash_bytes` column (1/2/3, NULL when unavailable) that the path-width
  chart aggregates over; confirms the collector chokepoint and value domain.
- `docs/plans/20260612-2014-raw-packets-feature/plan.md` — the foundational
  Raw Packets feature (`RawPacket` model, `event_type` classification,
  `feature_packets` flag, observer-level volume semantics).
- `docs/plans/20260616-2023-fix-postgres-charts-flatline/plan.md` —
  `_date_bucket_key()` dialect-neutral date handling; relevant precedent if the
  breakdown queries ever need cross-backend date normalization (they currently
  only filter by `received_at`, not group by date, so this is reference-only).
- `docs/plans/20260609-2106-redis-api-cache/plan.md` — the `@cached` decorator
  and `redis_cache_ttl_dashboard` TTL reused by the new endpoint.
- `src/meshcore_hub/api/routes/dashboard.py:387-432` — `get_packet_activity`,
  the endpoint whose structure (deps, caching, date window, today-exclusion)
  the new endpoint mirrors.
- `src/meshcore_hub/collector/letsmesh_normalizer.py:569-583` —
  `_FALLBACK_EVENT_TYPES` map documenting the full `event_type` value space
  (justifies the top-N + "other" rollup).
- `src/meshcore_hub/web/static/js/charts.js:140-163,225-268` — `createLineChart`
  and `initDashboardCharts`, the helpers the new chart function sits alongside.
- `src/meshcore_hub/web/static/js/spa/pages/dashboard.js:114-211,224-283` —
  `gridCols`, `renderChartCards`, and the `render` data-fetch/init/cleanup flow
  the plan modifies.
- Recent commits: `c029eae` (persist `path_hash_bytes`), `215690f` (dashboard
  packets widget), `f3a2fe7` (mobile landscape chart grid), `5dbf069` (path
  popover scroll) — the dashboard/UI work this plan continues.
