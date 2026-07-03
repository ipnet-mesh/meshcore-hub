# Regional number formatting + filter panel redesign

## Summary

Two related, independent frontend workstreams that clean up how numbers and the
filter panel are presented across the SPA.

1. **Regional number formatting.** Every numeric count in the UI — home & dashboard
   stat cards, list-page total/shown badges, inline reception/observer counts, and
   chart axis ticks + tooltips — currently renders as a raw integer (e.g. `251234`).
   A single `formatNumber()` helper backed by `Intl.NumberFormat()` (no explicit
   locale) is added so each visitor sees separators matching their browser locale
   (`251,234` in en-GB, `251.234` in de-DE). No backend, schema, or i18n-key changes
   are required; counts are pre-formatted at call sites before being interpolated.

2. **Filter panel redesign.** The list pages (nodes, packets, advertisements,
   messages) and the map page wrap their filter fields in a heavy DaisyUI
   `collapse` card (`bg-base-200 border-2 ... rounded-box mb-6` with a summary row
   and `collapse-content pt-4` padding). This is replaced by a compact DaisyUI
   slider `toggle` + "Filters" label placed on the **right** of the existing
   record-count + auto-refresh control row; when toggled on, the bare filter fields
   (no border, no card, no heavy padding) render directly below the control row.

## Background & Motivation

**Number formatting.** The frontend renders counts entirely raw. The shared stat
card helper `renderStatCard` emits `${value}` verbatim
(`src/meshcore_hub/web/static/js/spa/components.js:822`); the dashboard's four inline
stat numbers do the same (`pages/dashboard.js:139,160,181,202`); total/shown badges
pass raw ints into `t()` which `String()`-ifies them (`i18n.js:63`); and `charts.js`
has **no** `ticks.callback` on the y-axis and **no** `tooltip.callbacks` — so a
y-value of `12000` prints as `12000` and the tooltip shows the bare number. The only
locale-aware formatting in the codebase is for *dates* (`formatDateTime*` in
`components.js`, and `toLocaleDateString` in `charts.js:108`, the latter hard-coded
to `en-GB`). There is no `Intl.NumberFormat` / `toLocaleString` for numbers
anywhere. `__APP_CONFIG__` exposes `datetime_locale` (admin-controlled, default
`en-US`) at `web/app.py:319`, but this is a single admin-chosen locale rather than
each visitor's region; per-visitor regional formatting should decouple from it.

**Filter panel.** The collapsible filter was introduced by
`docs/plans/20260505-0900-improve-filter-options/plan.md`, which wrapped the form in
a DaisyUI `<details class="collapse collapse-arrow ...">` with `collapsible` /
`defaultOpen` options on `renderFilterCard` (`components.js:774-806`). Open-state
survival across auto-refresh re-renders works by reading `details.collapse.open`
from the DOM before each render (all 5 pages). The observer filter was later moved
*out* of the panel into toggle badges below it
(`docs/plans/20260614-1220-observer-filter-badges/plan.md`), leaving the collapse
card as a relatively heavy wrapper for a few selects. The card's `border-2`,
`rounded-box`, `bg-base-200`, `mb-6`, and `collapse-title`/`collapse-content`
padding consume a lot of visual real estate for what is now a compact form.

**Recent direction.** Recent UI work (`479c263` "redesign panel accent system",
`7956532` "normalize spacing", `91a3fcf` keyboard accessibility, `510612d`
self-hosted typography) shows an active push toward a tighter, more consistent UI.
This plan continues that direction. No git history touches number formatting or the
filter toggle style, so this is greenfield UI work.

## Goals

- Every count rendered in the SPA is formatted with locale-appropriate grouping
  separators, driven by the visitor's browser locale (`Intl.NumberFormat()`).
- The filter panel on all five filter-bearing pages (nodes, packets,
  advertisements, messages, map) becomes a right-aligned slider toggle in the
  existing control row, with bare filter fields rendering below when enabled — no
  bordered/padded card.
- Filter open-state continues to survive auto-refresh re-renders and SPA
  navigation exactly as it does today.
- No backend, API schema, database, or `__APP_CONFIG__` changes. No new i18n keys
  required (reuse existing `common.filters`).

## Non-Goals

- No change to `t()` itself — counts are pre-formatted at call sites so the i18n
  function stays generic (it interpolates arbitrary params, not just counts).
- Pagination page-number indices (`components.js:520,522`) are left raw — formatting
  `1,234` page indices would be wrong.
- Decimal physical values stay on `toFixed()`: SNR (`packet-group-detail.js:186`,
  `packet-detail.js:104`), spam score (`messages.js:144`), GPS coords
  (`map.js:105`), radio-config tiles (`home.js:31`).
- No per-dialect/backend work; `charts.js` consumes the same JSON shape (confirmed
  by `docs/plans/20260616-2023-fix-postgres-charts-flatline/plan.md`).
- No change to the observer toggle badges (`components.js:638-654`) or their
  localStorage plumbing — they already render below the filter and stay in place.
- No new CSS file; DaisyUI `toggle` + existing utilities cover it.
- No CI Postgres matrix; this is frontend-only and the existing `tests/test_web/`
  suite (which asserts `__APP_CONFIG__` presence) is the regression gate.

## Requirements

### Functional Requirements

- Stat numbers on home (`renderStatCard` → 6 cards) and dashboard (4 inline
  numbers) display with locale grouping (e.g. `12,345`).
- List-page total/shown badges and map count badges show grouped counts inside
  their translated strings (e.g. "12,345 total").
- Inline reception/observer counts on packets, packet-detail, and
  packet-group-detail pages, and the observer badge count, are grouped.
- Chart.js y-axis ticks and tooltip body values are grouped.
- On all five filter-bearing pages, a slider toggle labeled "Filters" appears at
  the right end of the control row (after the record-count badge and the
  auto-refresh pause/play control).
- Toggling the switch on reveals the filter fields directly below the control row,
  with no surrounding border, card background, or heavy padding/margin. Toggling
  off hides them.
- Filter visibility persists across auto-refresh ticks and across re-renders
  triggered by navigation/sort/pagination.
- On a fresh page mount (no prior state), the filter defaults open iff active
  filters exist (`hasActiveFilters`), matching current behavior.

### Technical Requirements

- **Locale source:** `new Intl.NumberFormat()` with **no** argument — uses the
  runtime default locale (`navigator.language`). No explicit locale tag is passed,
  so formatting is per-visitor and decoupled from the admin's `datetime_locale`.
- **`formatNumber` contract:** returns `''` for null/undefined/empty, returns the
  original `String(value)` for non-finite numbers, otherwise `Intl.NumberFormat().format(n)`.
  This makes it safe to wrap values that may be missing.
- **State preservation mechanism is unchanged in spirit:** today each page reads
  `container.querySelector('details.collapse').open` before render; the new design
  reads `container.querySelector('#filter-toggle').checked` instead. The native
  checkbox holds the state in the DOM exactly as `<details>.open` did — no extra
  state plumbing, no refetch on toggle (the toggle's `@change` re-runs the existing
  `renderPage(lastContent)` closure).
- **`lit-html` controlled-checkbox safety:** because the value read from the DOM is
  the same value bound back via `?checked=${filterOpen}`, the binding is idempotent
  and does not fight the native toggle.
- **DaisyUI `toggle`** (slider switch) is loaded already (`@plugin "daisyui"` in
  `input.css:2`) but not yet used anywhere in the codebase; this plan introduces it.
  It is a DaisyUI component class, so no Tailwind safelist entry is needed.
- **`charts.js` is a classic (non-module) script** loaded at `spa.html:193`, before
  the SPA module bundle. To avoid load-order/import issues, `charts.js` defines a
  local `formatNumber` (the same `Intl.NumberFormat().format(v)` one-liner) rather
  than importing from the module graph.
- **Map page** uses an inline filter (not `renderFilterCard`) and has no
  auto-refresh; its toggle's `onChange` wires into the map's existing client-side
  `applyFilters`/re-render path (no API refetch needed, since map filters are
  applied client-side).
- No Python, HTML structure, or `.env` changes. `tests/test_web/` must still pass
  unmodified (it checks `__APP_CONFIG__` and page scaffolding, not JS internals).

## Implementation Plan

### Phase 1: `formatNumber` helper + stat numbers

- **`components.js`** — add `export function formatNumber(value)` near the existing
  `formatDateTime*` helpers (~line 193). Implement the contract above. Also expose
  `window.formatNumber = formatNumber` (mirrors `window.t = t` at `i18n.js:78`) for
  any non-module callers.
- **`components.js:822`** — in `renderStatCard`, `${value}` → `${formatNumber(value)}`.
  (Cascades to all 6 home-page stat cards: `home.js:148,155,162,169,205,211`.)
- **`dashboard.js:139,160,181,202`** — wrap the four `${stats.*}` numbers with
  `formatNumber(...)`. Add `formatNumber` to the existing `components.js` import.

### Phase 2: total/shown badges + inline counts

Wrap counts with `formatNumber(...)` at each render site. Most pass counts as
`t()` interpolation params but some use raw `${}` template expressions — both
patterns get the same `formatNumber(...)` wrapper:

- `pages/nodes.js:46`
- `pages/packets.js:80`, plus inline `:39` (`observer_count`), `:41`
  (`reception_count`)
- `pages/advertisements.js:62`
- `pages/messages.js:227`
- `pages/map.js:309,312,313,331` (set via `element.textContent = t(...)`, counts
  formatted inside the `t()` call)
- `pages/members.js:16,106`
- `pages/packet-group-detail.js:172` — `t()` interpolation
- `pages/packet-group-detail.js:304,318` — raw `${reception_count}` or `${observer_count}` in template literal
- `pages/packet-group-detail.js:345-346` — raw `${g.reception_count}` and `${g.observer_count}` in template literal
- `components.js:558` (`observerIcons` badge count, raw `${observers.length}`)

e.g. `t('common.total', { count: formatNumber(displayTotal) })` for `t()` call
sites; `${formatNumber(oc)}` for raw template literal sites.

### Phase 3: Chart axis + tooltip formatting

- **`charts.js`** — add a module-local `function formatNumber(v)` (one-liner).
- In `createChartOptions()` (`charts.js:49-98`):
  - **y-axis ticks** (`:86-89`): add
    `callback: function(value) { return formatNumber(value); }` alongside
    `precision: 0`.
  - **tooltip** (`:63-71`): add a `callbacks` object with a `label` function that
    formats `ctx.parsed.y` via `formatNumber(...)` (prefixed by the dataset label,
    preserving Chart.js's default label style).

### Phase 4: Filter component refactor (`components.js` + `icons.js`)

- **`icons.js`** — add a new `iconFilter` SVG function (funnel icon, consistent
  with existing Heroicon-style patterns in the file). All 40 existing icons follow
  the same signature; match that pattern.
- **Replace** `renderFilterCard()` (`components.js:774-806`) with two exports.
  Add `iconFilter` to the `../icons.js` import in `components.js`.
  - `renderFilterForm({ fields, basePath, navigate, submitLabel, clearLabel })` —
    returns **only** the `<form>` (fields + submit/clear buttons), no `<details>`,
    no card, no border, no `mb-6`. Reuses the existing `createFilterHandler` /
    `autoSubmit` / `submitOnEnter` helpers (`components.js:665-700`) unchanged.
  - `renderFilterToggle({ open, onChange })` — returns the right-side control:
    ```html
    <label class="label cursor-pointer gap-2" title=${t('common.filters')}>
      <span class="text-sm opacity-80 flex items-center gap-1">
        ${iconFilter('w-4 h-4')} ${t('common.filters')}
      </span>
      <input type="checkbox" id="filter-toggle"
             class="toggle toggle-sm toggle-primary"
             ?checked=${open} @change=${onChange}>
    </label>
    ```
- Keep the `createFilterHandler` / `autoSubmit` / `submitOnEnter` helpers as-is.

### Phase 5: Four shared list pages

For each of nodes, packets, advertisements, messages:

- Replace the state-read lines (e.g. `nodes.js:176-177`):
  ```js
  const existingToggle = container.querySelector('#filter-toggle');
  const filterOpen = existingToggle ? existingToggle.checked : hasActiveFilters;
  ```
- **`nodes.js:175`** — fix `hasActiveFilters` to also check `pubkey_prefix`:
  ```js
  const hasActiveFilters = search !== '' || adv_type !== '' || pubkey_prefix !== '' || (config.oidc_enabled && adopted_by !== '');
  ```
  The public-key-prefix text field was historically omitted from the
  hasActiveFilters check (a pre-existing bug); fixing it here ensures the new
  toggle defaults open when it is filled.
- Drop the `renderFilterCard({ collapsible: true, ... })` call (e.g.
  `nodes.js:179-185`).
- Restructure the control row so the toggle sits right (e.g. `nodes.js:44-50`):
  ```html
  <div class="flex items-center gap-2 mb-4">
    ${displayTotal !== null ? html`<span class="badge badge-lg">${t('common.total', { count: formatNumber(displayTotal) })}</span>` : nothing}
    ${error ? warningBadge(error) : nothing}
    <div class="ml-auto flex items-center gap-3">
      <span id="auto-refresh-toggle"></span>
      ${renderFilterToggle({ open: filterOpen, onChange: onFilterToggle })}
    </div>
  </div>
  ${filterOpen ? renderFilterForm({ fields: filterFields, basePath: '/nodes', navigate }) : nothing}
  ```
- Add `function onFilterToggle() { renderPage(lastContent); }` — reuses the page's
  existing `renderPage` closure (calls `litRender`). Because `#filter-toggle.checked`
  is read fresh at the top of each render, the toggle drives visibility with no
  refetch.

**Files & line refs:** `pages/nodes.js` (44-51, 176-185), `pages/packets.js`
(73-86, 176-185), `pages/advertisements.js` (55-68, 250-259), `pages/messages.js`
(220-233, 426-435).

> Note: the advertisements and messages pages render observer toggle badges below
> the filter form (`advertisements.js:269,285`; `messages.js:445,463`). Their
> placement is unchanged; they naturally sit below the new inline form.

### Phase 6: Map page

**File:** `pages/map.js:185-246`.

- State-read `:187-188` → `container.querySelector('#filter-toggle')?.checked ?? false`.
  Unlike list pages, the map has no `hasActiveFilters` check — its selects all
  default to neutral/empty values, so the filter is never "active" on fresh mount.
  This matches current map behavior (the `<details>` was always default-closed).
- Add `renderFilterToggle` into the existing right-side badge group inside the
  header (the `<span id="node-count">` / `<span id="filtered-count">` block at
  `map.js:193-197`). `onChange` calls the map's existing client-side
  re-render/`applyFilters` path (no API refetch — map filters are applied
  client-side).
- Add `renderFilterToggle` to the imports from `../components.js`. Add
  `renderFilterForm` to the same import (the map renders its own field layout,
  so `renderFilterForm` import is only needed if map adopts the shared form;
  otherwise just import `renderFilterToggle`).
- Replace the `<details>…</details>` block (`map.js:200-246`) with a bare
  `<div class="flex gap-4 flex-wrap items-end ${filterOpen ? '' : 'hidden'}">`
  containing the same fieldsets/selects/checkbox/clear button — drop `collapse`,
  `bg-base-200`, `border-2 border-base-content/25`, `rounded-box`,
  `collapse-title`, `collapse-content pt-4`. The `hidden` class toggles visibility.

### Phase 7: Build + verify

- Frontend assets build into the Docker image (no local `npm` step per `AGENTS.md`):
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core build`.
- `pytest --no-cov tests/test_web/` — confirm `__APP_CONFIG__` assertions and page
  scaffolding still pass (no Python/HTML-structure changes, so expected green).
- `pre-commit run --all-files`.

## Verification

1. **Stack up:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml
   --profile core up -d`.
2. **Numbers (en-GB browser):** home & dashboard stat cards, list total badges,
   map count badges, packet reception/observer counts, and chart y-axis + tooltips
   show thousands separators (e.g. `12,345`). In a `de-DE` browser, the same values
   show `12.345`.
3. **Filters (nodes, packets, ads, messages, map):** the slider toggle appears at
   the right of the count + auto-refresh control; toggling on shows the bare fields
   below (no border/padded box); toggling off hides them; open state survives an
   auto-refresh tick (wait one interval on nodes/ads/etc.) and survives a sort/page
   change; on a fresh navigation the panel opens iff filters are active.
4. **Regression:** `pytest --no-cov tests/test_web/` green; `pre-commit run
   --all-files` green.
5. **Sanity:** in devtools, `(1234567).toLocaleString()` returns the expected
   grouped string for the active browser locale.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-03

### Resolutions

- **No filter icon exists in icons.js**: Confirmed — 40 icons, none are filter/funnel.
  Added `iconFilter` SVG creation to Phase 4 (follows existing Heroicon-style patterns).
- **`pubkey_prefix` missing from `nodes.js` `hasActiveFilters`**: Confirmed at
  `nodes.js:175`. This is a pre-existing bug (the filter panel won't open on fresh
  mount when only the public-key-prefix field is filled). Fixed in-scope by adding
  `pubkey_prefix !== ''` to the check in Phase 5.
- **Tooltip vs. label string**: Reuse `common.filters` ("Filters") for both the
  visible label and the toggle's `title` attribute. No new i18n keys required.
- **`packet-group-detail.js` format sites are raw template literals, not `t()`
  calls**: Lines 304, 318, and 345-346 use direct `${}` interpolation rather than
  `t()` params. Phase 2 updated to list them explicitly as raw-template-literal
  format sites (still wrapped with `formatNumber(...)` — just not inside `t()`).
- **Map page has no `hasActiveFilters` check**: Unlike list pages, map defaults to
  `?? false` because its selects all start at neutral/empty values. This matches
  current behavior (the `<details>` was always default-closed on fresh mount).
  Documented in Phase 6.
- **`window.formatNumber` is unused by `charts.js`**: `charts.js` defines its own
  local `formatNumber` (Phase 3) to avoid module-load-order issues.
  `window.formatNumber` (Phase 1) is harmless — it mirrors the `window.t` pattern
  and serves as a debug/console utility — but is not strictly required. Retained
  for consistency with the existing `window.t` convention at `i18n.js:78`.
- **`toggle-primary` color**: Needs visual verification during implementation
  (appearance against current light/dark themes). Fall back to plain `toggle` if
  the primary variant doesn't render well.

### Remaining Action Items

- At implementation time, visually verify `toggle toggle-sm toggle-primary`
  renders acceptably in both light and dark themes. Fall back to `toggle toggle-sm`
  if needed.
- Verify no `id="filter-toggle"` collision — only one page renders at a time in
  the SPA, but confirm no stale checkbox remains after a quick page transition.
- After implementation, spot-check `navigator.language` returns a grouped format
  in each target browser (Chrome, Firefox, Safari).

## References

- `docs/plans/20260505-0900-improve-filter-options/plan.md` — introduced the
  `renderFilterCard` `collapsible`/`defaultOpen` pattern and the `<details>`-based
  collapse + `existingDetails.open` state-preservation mechanism that this plan
  refactors.
- `docs/plans/20260614-1220-observer-filter-badges/plan.md` — moved observer
  filtering out of the panel into toggle badges below it; confirms the badges stay
  in place below the new inline filter form.
- `docs/plans/20260616-2023-fix-postgres-charts-flatline/plan.md` — confirms
  `charts.js` consumes a stable JSON shape and needs no backend-coordinated edits;
  this plan's `charts.js` changes are purely presentational.
- Key source locations: `components.js:774-825` (`renderFilterCard`, `renderStatCard`),
  `components.js:558` (`observerIcons`), `i18n.js:56-78` (`t()`), `auto-refresh.js:20-88`,
  `charts.js:49-98` (`createChartOptions`), `web/app.py:319` (`datetime_locale` in
  `__APP_CONFIG__`).
- Git: `479c263` (panel accent redesign), `7956532` (spacing normalization),
  `91a3fcf` (keyboard accessibility) — recent UI-direction context.
