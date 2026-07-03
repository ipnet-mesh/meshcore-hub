# Dashboard & Homepage Packets Widget

## Summary

Surface raw-packet volume in the two overview surfaces of the web app. On the
**homepage**, add a fourth stat widget ("Packets") to the existing stats panel,
gated on the `packets` feature flag, and reduce the vertical height of all
homepage stat cards. On the **dashboard** page, remove the top row of summary
stat boxes entirely and instead fold each entity's headline number into the
top-right corner of its own chart card (same font size as the old stat value),
then add a fourth Packets chart so a `packets`-enabled deployment renders a
four-column chart grid.

The raw-packets subsystem already exists end-to-end (model, collector
ingestion, `/packets` + `/packet-groups` API, feature flag, CSS color, icon,
i18n label). The only missing pieces are packet counts in the
`DashboardStats` payload, a daily packet-activity endpoint, and the frontend
wiring.

## Background & Motivation

The Raw Packets feature (`docs/plans/20260612-2014-raw-packets-feature`) shipped
a `raw_packets` table that captures every inbound MeshCore packet as it arrives
over the LetsMesh `packets` feed, plus a dedicated `/packets` browse page. That
data is fully available to operators but is **invisible on the two overview
pages**: the homepage stats panel shows Nodes / Advertisements / Messages, and
the dashboard page shows the same three entities as both stat boxes and charts.
Packet volume — often the highest-volume signal on a busy mesh — has no
presence on either overview.

Concurrently, the dashboard page duplicates information: each entity appears
once as a big number in a stat box and again as a chart immediately below it.
Consolidating the number into the chart card header removes the duplication,
reclaims vertical space, and produces a cleaner, chart-first overview that
naturally extends to a fourth (Packets) column when the feature is enabled.

Recent git history shows sustained UI polish work (panel-accent redesign, mobile
nav, typography adoption in `479c263`, `510612d`, `cb677b3`), so this fits the
current direction of tightening the overview surfaces.

## Goals

- Add a Packets stat widget to the homepage stats panel, gated on
  `features.packets !== false`, showing the last-7-days packet count.
- Reduce the vertical footprint of homepage stat cards.
- Remove the dashboard's top stat-box row and render each entity's headline
  number in the top-right corner of its chart card (matching the old stat-value
  font size).
- Add a Packets chart to the dashboard, producing a 4-column chart grid when
  `packets` is enabled (3 columns otherwise).
- Expose packet counts and daily packet activity from the backend without new
  models, migrations, or config flags.

## Non-Goals

- No changes to the `/packets` browse page, filters, or detail view.
- No new feature flags, config variables, or i18n keys (all required strings and
  the `feature_packets` flag already exist).
- No changes to channel-visibility / role-based redaction for packet payloads
  (the new count/activity endpoints are role-independent volume metrics).
- No alteration of the homepage combined activity chart (adverts + messages).
- No database migrations (reuses the existing `raw_packets` table).

## Requirements

### Functional Requirements

- **FR-1** — When `features.packets !== false`, the homepage stats panel renders
  a fourth widget titled "Packets" (iconPackets, green accent), showing
  `stats.packets_7d` with the description "last 7 days", ordered after Messages.
- **FR-2** — When `features.packets === false`, no Packets widget appears on the
  homepage and no packets data is fetched beyond the single `/stats` call.
- **FR-3** — Homepage stat cards are visibly shorter than today (reduced vertical
  padding and a smaller value font), affecting both the stats panel and the
  members panel equally (global `renderStatCard` change).
- **FR-4** — The dashboard page no longer renders the top row of summary stat
  boxes (Nodes / Advertisements / Messages).
- **FR-5** — Each dashboard chart card displays its headline number in the
  top-right corner of the card, at the same font size as the former
  `.stat-value` (`text-4xl`), colored with the entity accent:
  - Nodes → `stats.total_nodes`
  - Advertisements → `stats.advertisements_7d`
  - Messages → `stats.messages_7d`
  - Packets → `stats.packets_7d`
- **FR-6** — When `features.packets !== false`, the dashboard renders a fourth
  chart card (Packets) with a 7-day daily line chart, producing a 4-column grid
  at the `md` breakpoint and above.
- **FR-7** — `GET /api/v1/dashboard/stats` returns `total_packets` and
  `packets_7d` integers.
- **FR-8** — `GET /api/v1/dashboard/packet-activity?days=N` returns a
  `DailyActivity` payload (reused schema) of per-day raw-packet counts, capped
  at 90 days, excluding today, with zero-filled missing days — identical
  semantics to the existing `/activity` advertisement endpoint.

### Technical Requirements

- **TR-1** — Packet counts in `get_stats` use a single conditional-aggregation
  query mirroring the advertisement block (`func.count()` +
  `func.sum(case((received_at >= seven_days_ago, 1), else_=0))`), not two
  separate queries.
- **TR-2** — The `/packet-activity` endpoint mirrors `/activity` exactly:
  `func.date()` bucketing, `_date_bucket_key()` normalization for SQLite/Postgres
  parity (see plan `20260616-2023-fix-postgres-charts-flatline`), default
  `@cached` key (role-independent), `redis_cache_ttl_dashboard` TTL.
- **TR-3** — No role/channel-visibility filter on packet counts or activity
  (raw packets are observer-level volume metrics; payload redaction stays on the
  `/packets` list/detail endpoints only).
- **TR-4** — Frontend feature gating uses the established
  `features.packets !== false` pattern (enabled by default).
- **TR-5** — `gridCols()` helper extended to return `md:grid-cols-4` for a count
  of 4, so the chart grid scales from 1 → 2 → 3 → 4 columns.
- **TR-6** — `pageColors` gains a `packets` getter reading `--color-packets`
  (which already exists in `app.css` for both light and dark themes).
- **TR-7** — `ChartColors` (charts.js) gains `packets` / `packetsFill` entries
  so the Packets line chart uses the green accent.
- **TR-8** — Chart cleanup teardown in `dashboard.js` includes `'packetChart'`.
- **TR-9** — `renderStatCard` remains the single shared component; after this
  change it is consumed only by `home.js` (dashboard drops its usage), so the
  global shrink effectively only touches the homepage.

## Implementation Plan

### Phase 1: Backend — packet counts & activity endpoint

- **`common/schemas/messages.py`** (`DashboardStats`, after `total_members` at
  line 288): add two fields:
  ```python
  total_packets: int = Field(default=0, description="Total raw packets captured")
  packets_7d: int = Field(default=0, description="Packets captured in last 7 days")
  ```
  Reuse the existing `DailyActivity` schema for the activity endpoint (no new
  schema).

- **`api/routes/dashboard.py`**:
  - Add `RawPacket` to the model imports (it is already exported from
    `common/models`).
  - In `get_stats`, after the advertisement count block (lines 137–148), add a
    packet conditional-aggregation query and populate `total_packets` /
    `packets_7d` in the `DashboardStats(...)` constructor (lines 268–282).
  - Add a new route mirroring `/activity` (line 285):
    ```python
    @router.get("/packet-activity", response_model=DailyActivity)
    @cached("dashboard/packet-activity", ttl_setting="redis_cache_ttl_dashboard")
    def get_packet_activity(_: RequireRead, session: DbSession, request: Request, days: int = 30) -> DailyActivity:
        ...
    ```
    Body identical to `get_activity` but selecting from `RawPacket.received_at`
    with no `_flood_only_filter` and no role/channel filter.

### Phase 2: Frontend — shared component & color plumbing

- **`spa/components.js`**:
  - `pageColors` (line 183): add
    `get packets() { return getComputedStyle(document.documentElement).getPropertyValue('--color-packets').trim(); }`.
  - `renderStatCard` (line 803): global shrink — add `!py-2` to the root
    `class` and change the value wrapper from `stat-value` to
    `stat-value text-3xl` (drops the big number from ~2.5rem to ~1.875rem and
    trims vertical padding).

- **`charts.js`**:
  - Add `packets` and `packetsFill` to `ChartColors` (read `--color-packets`).
  - `initDashboardCharts` (line 203): accept a 4th `packetData` argument and,
    when truthy, call `createLineChart('packetChart', packetData,
    t('entities.packets'), ChartColors.packets, ChartColors.packetsFill, true)`.

### Phase 3: Frontend — homepage widget

- **`spa/pages/home.js`** (`renderStatsPanel`, after the Messages card at
  line 164): append a fourth card gated on `features.packets !== false`:
  ```js
  ${features.packets !== false ? renderStatCard({
      icon: iconPackets('h-8 w-8'),
      color: pageColors.packets,
      title: t('entities.packets'),
      value: stats.packets_7d,
      description: t('time.last_7_days'),
  }) : nothing}
  ```
  `iconPackets` is already imported (line 7). The global `renderStatCard` shrink
  applies automatically (no per-call change needed).

  `showStats` at line 228 must also include `|| features.packets !== false` so
  the stats panel still renders when only packets is enabled (e.g. when a
  deployment disables nodes, adverts, and messages but leaves packets on).

### Phase 4: Frontend — dashboard restructure

- **`spa/pages/dashboard.js`**:
  - **Imports** (line 7–9): add `iconPackets` to the icons import:
    ```js
    import { iconNodes, iconAdvertisements, iconMessages, iconPackets, iconChannel } from '../icons.js';
    ```
  - `gridCols()` (line 105): add `if (count === 4) return 'md:grid-cols-4';`.
  - **Delete** the stat-cards grid (lines 197–222) AND the `topCount`/`topGrid`
    computation (lines 185–186), which become dead code. The chart grid render
    gate (line 197) switches from `topCount > 0` to checking whether any feature
    is enabled (the `visibleCount` computed inside `renderChartCards` already
    drives the internal grid layout).
  - `renderChartCards` (line 111): add `stats` and `showPackets` params.
    Restructure each card's header into a flex row:
    ```html
    <div class="flex items-start justify-between gap-2">
        <div>
            <h2 class="card-title text-base"> ${icon} ${title} </h2>
            <p class="text-xs opacity-80"> ${subtitle} </p>
        </div>
        <div class="text-4xl font-bold leading-none" style="color: var(--color-<entity>)">
            ${value}
        </div>
    </div>
    ```
    — **Nodes**: title `t('entities.nodes')`, subtitle `t('time.over_time_last_7_days')`, value `stats.total_nodes`, color `--color-nodes`.
    — **Advertisements**: title `t('entities.advertisements')`, subtitle `t('time.per_day_last_7_days')`, value `stats.advertisements_7d`, color `--color-adverts`.
    — **Messages**: title `t('entities.messages')`, subtitle `t('time.per_day_last_7_days')`, value `stats.messages_7d`, color `--color-messages`.
    Add a Packets card (`#packetChart`, color `--color-packets`, `iconPackets`,
    title `t('entities.packets')`, subtitle `t('time.per_day_last_7_days')`,
    value `stats.packets_7d`). Include packets in `visibleCount` for the
    grid-cols calculation.
  - Main `render` (line 160): add `const showPackets = features.packets !== false;`.
    Add `/api/v1/dashboard/packet-activity?days=7` to the `Promise.all` (line
    170). Pass `stats` and `showPackets` to `renderChartCards`. Pass
    `showPackets ? packetActivity : null` as the 4th arg to
    `window.initDashboardCharts`. Add `'packetChart'` to the `chartIds` cleanup
    array (line 248). Remove `renderStatCard` from the imports (line 5) once the
    stat grid is gone.

### Phase 5: Tests & verification

- **`tests/test_api/test_dashboard.py`**:
  - Assert `packets_7d` (and `total_packets`) are present in the `/stats`
    response.
  - Add a test for `/dashboard/packet-activity`: create an observer `Node` +
    `RawPacket` rows across two days, request `?days=7`, assert correct daily
    counts and zero-fill. Mirror the existing advertisement-activity test's
    fixture style.
- Run `pytest --no-cov tests/test_api/test_dashboard.py tests/test_web/`.
- Run `pre-commit run --all-files`.
- `make build` then visually verify `/` (4 shorter stat cards when packets
  enabled; 3 when disabled) and `/dashboard` (no stat boxes; numbers in chart
  corners; 4-column chart grid when packets enabled, 3 when disabled).

## Open Questions

- None remaining. Count window (last 7 days), stat-card height approach (global
  shrink), and dashboard consolidation are all confirmed decisions.

## References

- `docs/plans/20260612-2014-raw-packets-feature/plan.md` — the Raw Packets
  feature this plan builds on (model, collector, `/packets` API, feature flag).
- `docs/plans/20260616-2023-fix-postgres-charts-flatline/plan.md` — the
  `_date_bucket_key()` dialect-neutral date handling that the new
  `/packet-activity` endpoint must reuse.
- `docs/plans/20260506-1330-members-widget/plan.md` — prior homepage stats-panel
  work (operator/member widgets via `renderStatCard`).
- `docs/plans/20260609-2106-redis-api-cache/plan.md` — the `@cached` decorator
  and `redis_cache_ttl_dashboard` TTL used by the new endpoint.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-03

### Resolutions

- **`showStats` missing `features.packets`**: Confirmed absent at
  `home.js:228`. Added explicit instruction to Phase 3 to include
  `|| features.packets !== false`.
- **`iconPackets` missing from dashboard.js imports**: Confirmed absent from
  `dashboard.js:7-9`. Added import instruction to Phase 4.
- **`topCount`/`topGrid` dead code after stat-cards removal**: Confirmed
  variables at `dashboard.js:185-186` would become unreferenced. Added
  explicit removal to Phase 4 and clarified the chart grid render gate should
  use the internal `visibleCount` instead.
- **Line reference approximations fixed**: `DashboardStats` field insertion
  point corrected from ~287 to after `total_members` (line 288). Advert count
  block corrected from ~148 to 137–148.
- **`received_at` index exists**: Confirmed `ix_raw_packets_received_at` at
  `raw_packet.py:104`. No migration needed for `/packet-activity` query
  performance. `TR-1` query with `received_at >= seven_days_ago` will use
  this index.
- **All i18n keys exist**: Confirmed `time.last_7_days` and
  `time.per_day_last_7_days` in both `en.json` (lines 134–135) and `nl.json`
  (lines 124–125). No new i18n keys needed.
- **Chart subtitle for Nodes**: Verified currently uses
  `time.over_time_last_7_days` (different from adverts/messages). Added
  per-card subtitle specifications to Phase 4 to prevent accidental
  homogenization.

### Remaining Action Items

- None. All review findings resolved in-plan.
