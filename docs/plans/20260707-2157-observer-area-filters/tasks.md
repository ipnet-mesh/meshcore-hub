# Tasks: Area-tag-based observer filter badges

> Generated from `plan.md` on 2026-07-07

## Phase 1: Shared helpers and badge component (`components.js`)

File: `src/meshcore_hub/web/static/js/spa/components.js` (lines 588-668).

- [x] Rename the localStorage key constant
  - [x] Change `OBSERVER_FILTER_KEY` value from `meshcore-observers-disabled` to `meshcore-observer-areas-disabled` (line ~592)
- [x] Rename `getDisabledObservers` -> `getDisabledObserverAreas` (lines 598-607)
  - [x] Update function name and keep same JSON-parse + safe-empty-on-error logic, reading the new key
- [x] Rename `setDisabledObservers` -> `setDisabledObserverAreas` (lines 613-619)
  - [x] Update function name, persist to new key
- [x] Rename `toggleObserver` -> `toggleObserverArea` (lines 628-641)
  - [x] Change param from `pubkey` to `area` (area-code string)
  - [x] Change param from `totalObserverCount` to `totalAreaCount`
  - [x] Keep the "block last disable" guard: `totalAreaCount - disabled.size <= 1`
  - [x] Call `setDisabledObserverAreas` instead of `setDisabledObservers`
- [x] Reshape `observerFilterBadges` signature (lines 643-668) from `{ nodes, disabled, onToggle, extraClass }` to `{ areas, disabled, onToggle, extraClass }`
  - [x] Accept `areas: string[]` (already sorted by caller) instead of `nodes`
  - [x] Return `nothing` (lit-html) if `areas.length === 0`
  - [x] Per-badge: label = area code string; enabled state = `!disabled.has(area)`
  - [x] Per-badge click handler: `@click=${() => onToggle(area)}`
  - [x] Preserve existing styling (`badge badge-primary` / `badge badge-ghost opacity-50`)
  - [x] Preserve tooltip i18n keys (`filter_observer_enable` / `filter_observer_disable`)
  - [x] Preserve row label (`filter_observer_label`) and `extraClass` responsive-visibility contract
- [x] Confirm `observerIcons` (lines 568-573) is left untouched (per-row tooltip keeps `o.tag_name || o.name`)

## Phase 2: Adverts page wiring (`advertisements.js`)

File: `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`.

- [x] Update imports (line 8)
  - [x] Replace `getDisabledObservers, toggleObserver` with `getDisabledObserverAreas, toggleObserverArea`
  - [x] Keep `observerFilterBadges`, `observerIcons`, `routeTypeBadge` imports
- [x] Update closure init (line 25)
  - [x] Change `disabledObservers` variable to `disabledObserverAreas = getDisabledObserverAreas()`
- [x] Replace per-node map/sort/enabled-keys block (lines 104-114) with area grouping
  - [x] Build `areaMap: Map<string, string[]>` from `allNodes` where key = trimmed `area` tag value, value = array of `public_key`s
  - [x] Skip nodes where `area` tag is missing or empty/whitespace (`if (!area || !area.trim()) continue`)
  - [x] Derive `sortedAreas` = `[...areaMap.keys()].sort(...)` case-insensitive ascending
  - [x] Derive `enabledObserverKeys` = `sortedAreas.filter(a => !disabledObserverAreas.has(a)).flatMap(a => areaMap.get(a))`
  - [x] Derive `observerFilterActive` = `sortedAreas.some(a => disabledObserverAreas.has(a))`
- [x] Update toggle handler (lines 116-127)
  - [x] Rename param `pubkey` -> `area`
  - [x] Call `disabledObserverAreas = toggleObserverArea(area, sortedAreas.length)`
  - [x] Keep navigation/page-reset logic unchanged (reset to page 1 if currently > 1)
- [x] Verify data fetch (lines 130-133) still works
  - [x] `apiParams.observed_by = enabledObserverKeys` when `observerFilterActive` (mechanically unchanged, sourced from new area expansion)
- [x] Update badge factory call (lines 139-141)
  - [x] Pass `areas: sortedAreas` instead of `nodes: sortedNodes`

## Phase 3: Messages page wiring (`messages.js`)

File: `src/meshcore_hub/web/static/js/spa/pages/messages.js`.

Mirror Phase 2 changes at corresponding locations.

- [x] Update imports (line 9)
  - [x] Replace `getDisabledObservers, toggleObserver` with `getDisabledObserverAreas, toggleObserverArea`
  - [x] Keep `observerFilterBadges`, `observerIcons` imports
- [x] Update closure init (line 26)
  - [x] Change `disabledObservers` variable to `disabledObserverAreas = getDisabledObserverAreas()`
- [x] Replace per-node block (lines 268-278) with area grouping
  - [x] Build `areaMap`, `sortedAreas`, `enabledObserverKeys`, `observerFilterActive` (same logic as Phase 2)
- [x] Update toggle handler (lines 280-291)
  - [x] Rename param `pubkey` -> `area`
  - [x] Call `disabledObserverAreas = toggleObserverArea(area, sortedAreas.length)`
  - [x] Keep page-reset logic unchanged
- [x] Verify data fetch (lines 293-297) and `channelLabels` plumbing are unaffected
- [x] Update badge factory call (lines 302-304)
  - [x] Pass `areas: sortedAreas` instead of `nodes: sortedNodes`

## Phase 4: Legacy cleanup (`app.js`)

File: `src/meshcore_hub/web/static/js/spa/app.js`.

- [x] Add idempotent legacy localStorage cleanup at boot (after locale load ~line 256, before router start ~line 265)
  - [x] Add `try { localStorage.removeItem('meshcore-observers-disabled'); } catch {}`
  - [x] Confirm it runs unconditionally on every page load

## Verification

- [x] Rebuild the SPA bundle
  - [x] Run `make build` (Docker image build that bundles `dist/`) — passed
- [ ] Start the stack
  - [ ] Run `make up` — deferred to user (requires running stack for manual checks)
- [x] Run pre-commit
  - [x] Run `pre-commit run --all-files` (no Python changes; hook runs on whole tree) — passed
- [x] Run relevant web tests
  - [x] `pytest --no-cov tests/test_web/test_advertisements.py tests/test_web/test_messages.py` — 24 passed
- [ ] Manual: `/advertisements` and `/messages` show one badge per unique area code (e.g. `IP2`, `IP3`, `IP4`, `IP8`)
- [ ] Manual: observers with `is_observer=true` but no `area` tag do not appear as badges
- [ ] Manual: clicking an area badge greys it out and re-scopes the list to events observed by nodes in still-enabled areas
- [ ] Manual: page resets to 1 when toggling a badge on a page > 1
- [ ] Manual: reload restores selection from `localStorage` before first data fetch (no flash of unfiltered data)
- [ ] Manual: switch between Adverts and Messages -> same area selection applies (shared key)
- [ ] Manual: attempt to disable the last enabled area -> blocked
- [ ] Manual: per-row observer-count badge tooltip still shows observer **names** (unchanged)
- [ ] Manual: filter row label still reads "Observer"
- [ ] Manual: DevTools -> Application -> Local Storage confirms `meshcore-observer-areas-disabled` holds array of area-code strings
- [ ] Manual: DevTools -> Application -> Local Storage confirms old `meshcore-observers-disabled` key is removed by cleanup
- [ ] Edge case: zero observers have `area` tags -> no badge row, no filter, all data shown
- [ ] Edge case: stale area codes in localStorage (area no longer exists) -> no over-filtering
