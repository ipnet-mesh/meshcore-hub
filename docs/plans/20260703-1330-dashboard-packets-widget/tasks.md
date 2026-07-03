# Tasks: Dashboard & Homepage Packets Widget

> Generated from `plan.md` on 2026-07-03

## Phase 1: Backend — Packet Counts & Activity Endpoint

- [x] Add `total_packets` and `packets_7d` fields to `DashboardStats` schema
  - [x] In `meshcore_hub/common/schemas/messages.py`, after `total_members` (line 288), add `total_packets: int = Field(default=0)` and `packets_7d: int = Field(default=0)`
- [x] Import `RawPacket` model in dashboard routes
  - [x] In `meshcore_hub/api/routes/dashboard.py`, add `from meshcore_hub.common.models import RawPacket` alongside existing model imports
- [x] Add packet conditional-aggregation query to `get_stats`
  - [x] After the advertisement count block (lines 137–148), add a query mirroring that pattern: `func.count(RawPacket.id).label("total_packets")` + `func.sum(case((RawPacket.received_at >= seven_days_ago, 1), else_=0)).label("packets_7d")`
  - [x] Populate `total_packets` and `packets_7d` in the `DashboardStats(...)` constructor (lines 268–282)
- [x] Add `/packet-activity` daily activity endpoint
  - [x] Mirror `get_activity` (line 285): select `func.date(RawPacket.received_at)` buckets from `RawPacket`, apply `start_date`/`end_date` range excluding today, use `_date_bucket_key()` for SQLite/Postgres parity, zero-fill missing days using the existing loop pattern
  - [x] Return `DailyActivity` response model (reused schema)
  - [x] Decorate with `@cached("dashboard/packet-activity", ttl_setting="redis_cache_ttl_dashboard")` (no role/channel filter; default cache key like `/activity`)

## Phase 2: Frontend — Shared Component & Color Plumbing

- [x] Add `packets` getter to `pageColors`
  - [x] In `meshcore_hub/web/static/js/spa/components.js`, after the `messages` getter (line 190), add `get packets() { return getComputedStyle(document.documentElement).getPropertyValue('--color-packets').trim(); }`
- [x] Shrink `renderStatCard` globally
  - [x] In `meshcore_hub/web/static/js/spa/components.js`, in `renderStatCard` (line 803), add `!py-2` to the root element's `class` attribute
  - [x] Change `<div class="stat-value">` to `<div class="stat-value text-3xl">`
- [x] Add `packets` / `packetsFill` to `ChartColors`
  - [x] In `meshcore_hub/web/static/js/charts.js`, after `messagesFill`, add `packets: getCSSColor('--color-packets', ...)` and `packetsFill: getCSSColor('--color-packets', ...)` (same color for line and fill, matching the green accent)
- [x] Extend `initDashboardCharts` for packet data
  - [x] Add a 4th `packetData` parameter to `initDashboardCharts` (line 203)
  - [x] When `packetData` is truthy, call `createLineChart('packetChart', packetData, t('entities.packets'), ChartColors.packets, ChartColors.packetsFill, true)` after the existing chart calls

## Phase 3: Frontend — Homepage Widget

- [x] Add Packets stat card to `renderStatsPanel`
  - [x] In `meshcore_hub/web/static/js/spa/pages/home.js`, after the Messages card (line 164), append a fourth card gated on `features.packets !== false` showing `stats.packets_7d` with `iconPackets`, `pageColors.packets`, `t('entities.packets')`, and `t('time.last_7_days')`
- [x] Update `showStats` gate to include packets
  - [x] In `home.js` at line 228, append `|| features.packets !== false` to the `showStats` expression

## Phase 4: Frontend — Dashboard Restructure

- [x] Update imports and extend `gridCols`
  - [x] In `meshcore_hub/web/static/js/spa/pages/dashboard.js`, add `iconPackets` to the `icons.js` import (line 8)
  - [x] Remove `renderStatCard` from the `components.js` import (line 5) since the dashboard no longer uses it
  - [x] In `gridCols()` (line 105), add `if (count === 4) return 'md:grid-cols-4';`
- [x] Remove stat-cards grid and dead variables
  - [x] Delete the `topCount` / `topGrid` computation (lines 185–186)
  - [x] Delete the stat-cards grid template block (lines 197–222)
  - [x] Update the render gate (line 197) from `topCount > 0` to `(showNodes || showAdverts || showMessages || showPackets)`
- [x] Restructure chart card headers with corner numbers
  - [x] In `renderChartCards`, add `stats` and `showPackets` parameters
  - [x] For each existing card (Nodes, Advertisements, Messages), replace `<h2 class="card-title text-base">...</h2><p class="text-xs opacity-80">...</p>` with a flex row: `<div class="flex items-start justify-between gap-2"><div><h2 class="card-title text-base">${icon} ${title}</h2><p class="text-xs opacity-80">${subtitle}</p></div><div class="text-4xl font-bold leading-none" style="color: var(...)">${value}</div></div>`
  - [x] Nodes: title `t('entities.nodes')`, subtitle `t('time.over_time_last_7_days')`, value `stats.total_nodes`, color `--color-nodes`
  - [x] Advertisements: title `t('entities.advertisements')`, subtitle `t('time.per_day_last_7_days')`, value `stats.advertisements_7d`, color `--color-adverts`
  - [x] Messages: title `t('entities.messages')`, subtitle `t('time.per_day_last_7_days')`, value `stats.messages_7d`, color `--color-messages`
- [x] Add Packets chart card to `renderChartCards`
  - [x] Append a Packets card (gated on `showPackets`) with `#packetChart`, `--color-packets`, `iconPackets`, title `t('entities.packets')`, subtitle `t('time.per_day_last_7_days')`, value `stats.packets_7d`
  - [x] Include `showPackets` in the `visibleCount` computation
- [x] Wire up packets data fetching, chart init, and cleanup
  - [x] In `render` (line 160), add `const showPackets = features.packets !== false;`
  - [x] Add `/api/v1/dashboard/packet-activity?days=7` to the `Promise.all` call (line 170)
  - [x] Destructure `packetActivity` from the response, pass `stats` and `showPackets` to `renderChartCards`
  - [x] Pass `showPackets ? packetActivity : null` as the 4th argument to `window.initDashboardCharts`
  - [x] Add `'packetChart'` to the `chartIds` cleanup array (line 248)

## Phase 5: Tests & Verification

- [x] Add backend tests for packets in `/stats` response
  - [x] In `tests/test_api/test_dashboard.py`, add a test asserting `total_packets` and `packets_7d` are present in the `/stats` response and have the correct defaults (0 when no packets exist)
- [x] Add backend test for `/packet-activity` endpoint
  - [x] Create a test fixture with an observer `Node` and `RawPacket` rows across two days
  - [x] Request `/packet-activity?days=7`, assert correct per-day counts and zero-fill for days without data
  - [x] Mirror the existing `/activity` test fixture style
- [x] Run targeted backend and web tests
  - [x] `pytest --no-cov tests/test_api/test_dashboard.py tests/test_web/` — expect all passing
- [x] Run full lint pass
  - [x] `pre-commit run --all-files` — expect clean
- [x] Build and visually verify
  - [x] Run `make build` to rebuild the frontend container
  - [x] Verify homepage: 4 shorter stat cards when packets enabled; 3 when disabled
  - [x] Verify dashboard: no stat boxes; numbers in chart card corners; 4-column chart grid when packets enabled, 3 when disabled
