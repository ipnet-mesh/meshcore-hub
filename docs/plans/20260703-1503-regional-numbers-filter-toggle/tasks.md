# Tasks: Regional number formatting + filter panel redesign

> Generated from `plan.md` on 2026-07-03

## 1. formatNumber helper + stat card numbers

- [x] Create `formatNumber()` helper in `components.js`
  - [x] Add `export function formatNumber(value)` near existing `formatDateTime*` helpers (~line 193)
  - [x] Contract: return `''` for null/undefined/empty, `String(value)` for non-finite, else `Intl.NumberFormat().format(n)`
  - [x] Expose `window.formatNumber = formatNumber` (mirrors `window.t` pattern at `i18n.js:78`)
- [x] Update `renderStatCard` in `components.js:822`
  - [x] Replace `${value}` with `${formatNumber(value)}`
  - [x] Verifies: all 6 home-page stat cards format via `home.js:148,155,162,169,205,211`
- [x] Update dashboard inline stats in `pages/dashboard.js`
  - [x] Add `formatNumber` to the `../components.js` import
  - [x] Wrap `${stats.nodes}` at line 139
  - [x] Wrap `${stats.packets}` at line 160
  - [x] Wrap `${stats.advertisements}` at line 181
  - [x] Wrap `${stats.messages}` at line 202

## 2. total/shown badges + inline counts

- [x] Update list-page total/shown badges
  - [x] `pages/nodes.js:46` — wrap `displayTotal` and `shown` in `t()` badges
  - [x] `pages/packets.js:80` — wrap `displayTotal` and `shown` in `t()` badges
  - [x] `pages/advertisements.js:62` — wrap `displayTotal` and `shown` in `t()` badges
  - [x] `pages/messages.js:227` — wrap `displayTotal` and `shown` in `t()` badges
- [x] Update inline count renderers
  - [x] `pages/packets.js:39` — wrap `${observer_count}` with `formatNumber()` (raw template literal)
  - [x] `pages/packets.js:41` — wrap `${reception_count}` with `formatNumber()` (raw template literal)
- [x] Update map count badges in `pages/map.js`
  - [x] Line 309 — wrap count in `t()` call
  - [x] Line 312 — wrap count in `t()` call
  - [x] Line 313 — wrap count in `t()` call
  - [x] Line 331 — wrap count in `t()` call
- [x] Update members page in `pages/members.js`
  - [x] Line 16 — wrap `${online_count}/${total}` with `formatNumber()`
  - [x] Line 106 — wrap count in `t()` call
- [x] Update packet-group-detail page in `pages/packet-group-detail.js`
  - [x] Line 172 — wrap count in `t()` interpolation
  - [x] Line 304 — wrap `${reception_count}` in raw template literal with `formatNumber()`
  - [x] Line 318 — wrap `${observer_count}` in raw template literal with `formatNumber()`
  - [x] Line 345 — wrap `${g.reception_count}` in raw template literal with `formatNumber()`
  - [x] Line 346 — wrap `${g.observer_count}` in raw template literal with `formatNumber()`
- [x] Update observerIcons badge count in `components.js:558`
  - [x] Wrap `${observers.length}` in raw template literal with `formatNumber()`
- [x] Add `formatNumber` to imports on all updated page files

## 3. Chart.js axis + tooltip formatting

- [x] Add local `formatNumber` function in `charts.js`
  - [x] Define `function formatNumber(v) { return Intl.NumberFormat().format(v); }` at module scope
- [x] Add y-axis tick callback in `createChartOptions()` at `charts.js:86-89`
  - [x] Add `callback: function(value) { return formatNumber(value); }` alongside `precision: 0`
- [x] Add tooltip label callback in `createChartOptions()` at `charts.js:63-71`
  - [x] Add `callbacks` object with `label` function
  - [x] Format `ctx.parsed.y` via `formatNumber()` prefixed by dataset label (preserve Chart.js default label style)

## 4. Filter component refactor

- [x] Add `iconFilter` SVG in `icons.js`
  - [x] Create funnel icon function: `export function iconFilter(cls = 'h-5 w-5')`
  - [x] Follow existing Heroicon-style SVG patterns (24x24 viewBox, stroke, fill="none")
- [x] Create `renderFilterToggle()` in `components.js`
  - [x] Export function accepting `{ open, onChange }`
  - [x] Render label with DaisyUI `toggle toggle-sm toggle-primary` slider switch
  - [x] Include `iconFilter('w-4 h-4')` + `t('common.filters')` text in the label
  - [x] Add `title=${t('common.filters')}` on the label element
  - [x] Bind `?checked=${open}` and `@change=${onChange}` on the `<input type="checkbox" id="filter-toggle">`
  - [x] Add `iconFilter` to the `../icons.js` import
- [x] Create `renderFilterForm()` in `components.js`
  - [x] Export function accepting `{ fields, basePath, navigate, submitLabel, clearLabel }`
  - [x] Return bare `<form>` (fields + submit/clear buttons) — no `<details>`, card, border, or `mb-6`
  - [x] Reuse existing `createFilterHandler` / `autoSubmit` / `submitOnEnter` helpers unchanged
- [x] Remove old `renderFilterCard()` from `components.js:774-806`
  - [x] Confirm no other callers remain (grep for `renderFilterCard`)

## 5. Four shared list pages (nodes, packets, ads, messages)

- [x] Update `pages/nodes.js`
  - [x] Add `renderFilterToggle` and `renderFilterForm` to `../components.js` import
  - [x] Fix `hasActiveFilters` at line 175: add `pubkey_prefix !== ''` to the condition
  - [x] Replace state-read lines 176-177: query `#filter-toggle` checked state instead of `<details>.open`
  - [x] Replace `renderFilterCard({ collapsible: true, ... })` call (lines 179-185) with `renderFilterToggle` + `renderFilterForm`
  - [x] Restructure control row (lines 44-51): toggle right-aligned after auto-refresh
  - [x] Add `function onFilterToggle() { renderPage(lastContent); }` closure
- [x] Update `pages/packets.js`
  - [x] Add `renderFilterToggle` and `renderFilterForm` to `../components.js` import
  - [x] Replace state-read lines 176-177: query `#filter-toggle` checked state
  - [x] Replace `renderFilterCard({ collapsible: true, ... })` call (lines 176-185) with `renderFilterToggle` + `renderFilterForm`
  - [x] Restructure control row (lines 73-86): toggle right-aligned after auto-refresh
  - [x] Add `function onFilterToggle() { renderPage(lastContent); }` closure
- [x] Update `pages/advertisements.js`
  - [x] Add `renderFilterToggle` and `renderFilterForm` to `../components.js` import
  - [x] Replace state-read lines 250-251: query `#filter-toggle` checked state
  - [x] Replace `renderFilterCard({ collapsible: true, ... })` call (lines 250-259) with `renderFilterToggle` + `renderFilterForm`
  - [x] Restructure control row (lines 55-68): toggle right-aligned after auto-refresh
  - [x] Add `function onFilterToggle() { renderPage(lastContent); }` closure
  - [x] Confirm observer toggle badges (lines 269, 285) render below the new inline form unchanged
- [x] Update `pages/messages.js`
  - [x] Add `renderFilterToggle` and `renderFilterForm` to `../components.js` import
  - [x] Replace state-read lines 426-427: query `#filter-toggle` checked state
  - [x] Replace `renderFilterCard({ collapsible: true, ... })` call (lines 426-435) with `renderFilterToggle` + `renderFilterForm`
  - [x] Restructure control row (lines 220-233): toggle right-aligned after auto-refresh
  - [x] Add `function onFilterToggle() { renderPage(lastContent); }` closure
  - [x] Confirm observer toggle badges (lines 445, 463) render below the new inline form unchanged

## 6. Map page

- [x] Update `pages/map.js`
  - [x] Add `renderFilterToggle` to `../components.js` import
  - [x] Replace `<details>` open check (lines 187-188): query `#filter-toggle?.checked ?? false`
  - [x] Place `renderFilterToggle` in the right-side badge group inside header (lines 193-197)
  - [x] Wire `onChange` to map's existing `applyFilters`/re-render path (no API refetch)
  - [x] Replace `<details>…</details>` block (lines 200-246) with bare `<div>` using `hidden` class for visibility toggle
  - [x] Drop all collapse card classes: `collapse`, `bg-base-200`, `border-2`, `border-base-content/25`, `rounded-box`, `collapse-title`, `collapse-content pt-4`
  - [x] Preserve all existing fieldsets, selects, checkbox, and clear button inside the bare `<div>`

## 7. Build + regression

- [x] Build the Docker image
  - [x] `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all build`
  - [x] Confirm no build errors (JS syntax, module imports, Tailwind compilation)
- [x] Run web test suite
  - [x] `pytest --no-cov tests/test_web/` — confirm green (no Python/HTML changes expected)
- [x] Run pre-commit
  - [x] `pre-commit run --all-files`

## 8. Verification

- [ ] Stack up and smoke test
  - [ ] `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core up -d`
- [ ] Verify regional number formatting
  - [ ] Home page stat cards show locale-grouped numbers (e.g. `12,345` in en-GB, `12.345` in de-DE)
  - [ ] Dashboard inline stats show locale-grouped numbers
  - [ ] List-page total/shown badges show locale-grouped numbers
  - [ ] Map count badges show locale-grouped numbers
  - [ ] Packet reception/observer inline counts show locale-grouped numbers
  - [ ] Chart y-axis ticks show locale-grouped numbers
  - [ ] Chart tooltip values show locale-grouped numbers
  - [ ] Members page counts show locale-grouped numbers
  - [ ] Packet-group-detail inline counts show locale-grouped numbers
- [ ] Verify filter toggle on all 5 pages
  - [ ] Nodes: toggle appears right of control row; toggling reveals/hides bare fields; survives auto-refresh and sort/nav
  - [ ] Packets: same as nodes
  - [ ] Advertisements: same as nodes; observer badges render below filter form unchanged
  - [ ] Messages: same as nodes; observer badges render below filter form unchanged
  - [ ] Map: toggle appears in header badge group; toggling reveals/hides client-side filter fields
- [ ] Verify filter open-state behavior
  - [ ] Fresh navigation with active filters → toggle defaults on
  - [ ] Fresh navigation with no active filters → toggle defaults off
  - [ ] `pubkey_prefix` field on nodes page correctly triggers active-on-mount (Phase 5 fix)
  - [ ] Record count badge stays visible when toggling filter (onFilterToggle preserves lastTotal)
- [ ] Visual verification
  - [ ] `toggle toggle-sm toggle-primary` renders acceptably in light theme
  - [ ] `toggle toggle-sm toggle-primary` renders acceptably in dark theme
  - [ ] If `toggle-primary` looks off in either theme, fall back to plain `toggle toggle-sm`
- [ ] Cross-browser sanity check
  - [ ] `navigator.language` grouping works in Chrome (devtools: `(1234567).toLocaleString()`)
  - [ ] `navigator.language` grouping works in Firefox
  - [ ] `navigator.language` grouping works in Safari
- [ ] Verify no `#filter-toggle` collision on rapid SPA page transitions
  - [ ] Navigate quickly between pages and confirm no stale checkbox remains in DOM
- [x] Run final regression
  - [x] `pytest --no-cov tests/test_web/` green (236 passed)
  - [x] `pre-commit run --all-files` green
