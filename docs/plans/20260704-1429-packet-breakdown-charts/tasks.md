# Tasks: Dashboard Packet Breakdown Charts

> Generated from `plan.md` on 2026-07-04

## 1. Backend — Schemas & Endpoint

- [x] 1.1 Add `BreakdownBucket` and `PacketBreakdown` Pydantic schemas
  - [x] 1.1.1 Add `BreakdownBucket(BaseModel)` with `label: str` and `count: int` in `common/schemas/messages.py`, placed after `DailyActivity`
  - [x] 1.1.2 Add `PacketBreakdown(BaseModel)` with `days: int`, `by_event_type: list[BreakdownBucket]`, `by_path_width: list[BreakdownBucket]`

- [x] 1.2 Add `GET /api/v1/dashboard/packet-breakdown` endpoint
  - [x] 1.2.1 Place `get_packet_breakdown` function after `get_packet_activity` (line ~432) in `api/routes/dashboard.py`
  - [x] 1.2.2 Mirror `get_packet_activity` signature: `RequireRead`, `DbSession`, `request`, `days=7`; decorate with `@cached("dashboard/packet-breakdown", ttl_setting="redis_cache_ttl_dashboard")` and `@router.get` with `response_model=PacketBreakdown`
  - [x] 1.2.3 Reuse date-window math: `days = min(days, 90)`, `end_date = today at 00:00 UTC`, `start_date = end_date - timedelta(days=days)`, filter `received_at >= start_date AND received_at < end_date`

- [x] 1.3 Implement event-type aggregation (FR-1, FR-2, TR-3)
  - [x] 1.3.1 Run `select(event_type, func.count())` grouped by `event_type`, ordered by count descending
  - [x] 1.3.2 Take top 6 rows verbatim; sum remaining rows (including NULL `event_type` group, if present) into `{"label": "other", "count": <sum>}`
  - [x] 1.3.3 Omit the "other" bucket when distinct event types ≤ 6

- [x] 1.4 Implement path-width aggregation (FR-1, FR-3, TR-4)
  - [x] 1.4.1 Run `select(path_hash_bytes, func.count())` with `.where(path_hash_bytes.isnot(None))`, grouped by `path_hash_bytes`
  - [x] 1.4.2 Map rows into fixed `[(1, "1b"), (2, "2b"), (3, "3b")]` order, zero-filling any missing width
  - [x] 1.4.3 Exclude NULL `path_hash_bytes` from both buckets and percentage denominator

## 2. Backend — Tests

- [x] 2.1 Add `TestPacketBreakdown` class in `tests/test_api/test_dashboard.py`
  - [x] 2.1.1 Seed one observer `Node` and `RawPacket` rows spanning the last 7 days with ≥ 8 distinct `event_type` values
  - [x] 2.1.2 Seed rows with `path_hash_bytes` of 1, 2, 3, and NULL
  - [x] 2.1.3 Seed at least one row dated "today" to verify today is excluded

- [x] 2.2 Test event-type breakdown
  - [x] 2.2.1 Assert top 6 buckets are correct, descending by count
  - [x] 2.2.2 Assert 7th-and-beyond values are summed into "other"
  - [x] 2.2.3 Assert "other" is omitted when distinct event types ≤ 6

- [x] 2.3 Test path-width breakdown
  - [x] 2.3.1 Assert exactly three buckets in order: 1b, 2b, 3b
  - [x] 2.3.2 Assert NULL `path_hash_bytes` rows are excluded from all buckets
  - [x] 2.3.3 Assert missing width is zero-filled (e.g. if no 3b rows exist, count is 0)

- [x] 2.4 Test endpoint behavior
  - [x] 2.4.1 Assert `response_model` returns correct `PacketBreakdown` shape
  - [x] 2.4.2 Assert today's rows are excluded from the window
  - [x] 2.4.3 Assert `days` param is capped at 90
  - [x] 2.4.4 Assert endpoint returns empty `by_event_type` and `by_path_width` lists when no packets in window (empty-data path)
  - [x] 2.4.5 Assert role-independent caching behavior (mirror existing `/packet-activity` cache key test)

## 3. Frontend — Chart Helper & Palette

- [x] 3.1 Add `breakdown` color palette to `ChartColors` in `charts.js` (TR-7)
  - [x] 3.1.1 Define a hardcoded ordered array of 7 oklch hues: 6 distinct event-type colors + 1 neutral grey for "other"
  - [x] 3.1.2 Place alongside existing hardcoded colors (`ChartColors.grid`, `ChartColors.text`, etc.)

- [x] 3.2 Add `createStackedBarChart` helper in `charts.js` (TR-6)
  - [x] 3.2.1 Accept `(canvasId, buckets, colors)` — no `options` parameter; builds own options internally
  - [x] 3.2.2 Return `null` when `buckets` is empty/null or `total === 0` (matches `createLineChart` empty-data idiom)
  - [x] 3.2.3 Configure chart: `type: 'bar'`, `indexAxis: 'y'`, single y-label, one dataset per bucket with `backgroundColor: colors[i]`, `borderColor: colors[i]`, `borderWidth: 1`
  - [x] 3.2.4 Pre-normalize data to percentages (`count / total * 100`) so stacked total ~100
  - [x] 3.2.5 Build options: `scales.x.max = 100`, `scales.x.stacked = true`, `scales.y.stacked = true`, x-axis tick callback appends `%`, y-axis ticks hidden, `interaction.mode = 'nearest'`
  - [x] 3.2.6 Tooltip `label` callback renders `<label>: <count> (<pct>%)` using `formatNumber` and raw count stashed on dataset (e.g. `dataset.rawCount`)

- [x] 3.3 Extend `initDashboardCharts` in `charts.js` (TR-8)
  - [x] 3.3.1 Add two trailing params: `eventTypeData`, `pathWidthData`
  - [x] 3.3.2 When truthy and non-empty, call `createStackedBarChart('packetEventTypeChart', eventTypeData, ChartColors.breakdown)`
  - [x] 3.3.3 When truthy and non-empty, call `createStackedBarChart('packetPathWidthChart', pathWidthData, ChartColors.breakdown.slice(0, 3))` (reuses first 3 hues)

## 4. Frontend — Dashboard Cards & Data Wiring

- [x] 4.1 Update `renderChartCards` in `spa/pages/dashboard.js` (TR-9)
  - [x] 4.1.1 Accept new `packetBreakdown` parameter
  - [x] 4.1.2 Compute `eventTypeTotal` = `.reduce()` sum of `by_event_type` counts (or 0)
  - [x] 4.1.3 Compute `pathWidthTotal` = `.reduce()` sum of `by_path_width` counts (or 0)
  - [x] 4.1.4 Emit second grid row after existing trend grid closing `</div>`, gated on `showPackets`
  - [x] 4.1.5 Build two cards: "Packet event types" with `eventTypeTotal` headline, `#packetEventTypeChart` canvas; "Path hash width" with `pathWidthTotal` headline, `#packetPathWidthChart` canvas
  - [x] 4.1.6 Reuse `iconPackets`, `--color-packets` accent, and existing header flex-row idiom

- [x] 4.2 Update `render` in `spa/pages/dashboard.js` (TR-10)
  - [x] 4.2.1 Add `apiGet('/api/v1/dashboard/packet-breakdown', { days: 7 }, { signal })` to the `Promise.all` destructuring
  - [x] 4.2.2 Pass `packetBreakdown` to `renderChartCards` for headline computation
  - [x] 4.2.3 Pass `showPackets ? packetBreakdown.by_event_type : null` and `showPackets ? packetBreakdown.by_path_width : null` as trailing args to `window.initDashboardCharts(...)`
  - [x] 4.2.4 Add `'packetEventTypeChart'` and `'packetPathWidthChart'` to chart cleanup `chartIds` array

- [x] 4.3 Add i18n keys (TR-11)
  - [x] 4.3.1 Add `entities.packet_event_types` = "Packet event types" to `en.json`
  - [x] 4.3.2 Add `entities.path_hash_width` = "Path hash width" to `en.json`
  - [x] 4.3.3 Add `packets.breakdown_other` = "Other" to `en.json`
  - [x] 4.3.4 Add Dutch translations to `nl.json`: "Packet gebeurtenistypen", "Pad-hashbreedte", "Overig"

## 5. Verification

- [x] 5.1 Run backend tests
  - [x] 5.1.1 `pytest --no-cov tests/test_api/test_dashboard.py -v` — all `TestPacketBreakdown` tests pass

- [x] 5.2 Run quality checks
  - [x] 5.2.1 `pre-commit run --all-files` — no lint/format errors

- [ ] 5.3 Build and deploy
  - [ ] 5.3.1 `make build` — Docker image rebuilds successfully (SPA bundle included)
  - [ ] 5.3.2 `make up` — stack starts without errors

- [ ] 5.4 Visual verification (`FEATURE_PACKETS=true`)
  - [ ] 5.4.1 Trend grid unchanged (4 cards on large screens)
  - [ ] 5.4.2 New 2-col row below with both stacked bars showing proportional segments
  - [ ] 5.4.3 Tooltips render `<label>: <count> (<pct>%)`
  - [ ] 5.4.4 Card headlines show correct totals — event-type total and path-width total
  - [ ] 5.4.5 Empty-data path: cards show `0` headline, blank canvas (no JS error)

- [ ] 5.5 Visual verification (`FEATURE_PACKETS=false`)
  - [ ] 5.5.1 Neither trend Packets card nor breakdown cards render
  - [ ] 5.5.2 Breakdown endpoint is not requested (confirm in network tab)
