# Plan: Area-tag-based observer filter badges

## Summary

The Adverts and Messages pages currently render one filter badge per observer
node, labelled with the node's `name` tag, advertised `name`, or a truncated
public key. Observer operators in practice choose unhelpful names, so the badge
row is hard to scan. This plan switches the badge row to be **grouped by the
node's `area` tag** (a short area code such as `IP2` or `SE1`): one badge per
unique area code, toggling all observers in that area together. Observers
without an `area` tag are hidden from the filter row entirely.

This is a **frontend-only** change. The `area` tag is already seeded into
`node_tags` (`seed/node_tags.yaml`) and returned by `GET /api/v1/nodes`, but no
code currently reads it. No backend, API, schema, or migration changes are
required.

## Background & Motivation

The observer filter badge UI was introduced in
`docs/plans/20260614-1220-observer-filter-badges/plan.md` as a replacement for a
multi-select dropdown. The current data flow (unchanged by this plan):

1. Frontend calls `GET /api/v1/nodes?observer=true` (returns every node with
   `is_observer=true`, including its `tags` array).
2. `advertisements.js:104-107` and `messages.js:268-271` derive `_displayName`
   per node as `tags[name]` -> `node.name` -> `public_key.slice(0,12)+'...'`.
3. `components.js:652-668` `observerFilterBadges` renders one button per node
   using `_displayName`; `disabledObservers` (a `Set` of public keys) persists
   in `localStorage['meshcore-observers-disabled']`.
4. The page expands the enabled set to public keys and sends them as repeated
   `?observed_by=` params on the data fetch.

The IPNet seed data assigns an `area` tag (e.g. `IP2`, `IP3`, `IP4`, `IP8`) to
every node, but the value is stored and never displayed. Multiple observers
share each area code (e.g. `IP2` has 3 repeaters -- `seed/node_tags.yaml:5,21,37`),
so a naive per-node relabel would produce three identical `IP2` buttons.

Operator-chosen node names being unhelpful is the trigger; the `area` tag is the
natural, already-present signal for a coarser, meaningful grouping.

## Goals

- Badge row shows **one badge per unique area code**, not one per observer node.
- Badge label is the `area` tag value (e.g. `IP2`, `SE1`).
- Toggling an area badge enables/disables **all observers** whose `area` tag
  matches that code, on both the Adverts and Messages pages.
- Observers (`is_observer=true`) **without** a non-empty `area` tag are not
  shown as filter options (their data still appears when no area filter is
  active).
- Selection persists across reloads and is shared between the two pages.

## Non-Goals

- No change to the per-row observer-count badge tooltip (`observerIcons`,
  `components.js:568-573`) -- it keeps showing observer names.
- No change to the filter row label (stays "Observer"; i18n key
  `common.filter_observer_label`).
- No change to the `?observed_by=` API contract -- it still receives public keys.
- No backend, model, schema, or migration changes.
- No server-side filtering by tag (e.g. `?has_tag=area`) -- the observer node
  payload is small enough to filter client-side.
- No new JS unit tests for the grouping logic (the JS layer currently has no
  unit-test harness; adding one is out of scope).

## Requirements

### Functional Requirements

- **FR-1** -- Filter the observer node list to those whose `area` tag exists and
  has a non-empty (non-whitespace) value.
- **FR-2** -- Derive the set of unique area codes from that filtered list; sort
  them case-insensitively ascending.
- **FR-3** -- Render one badge per area code; badge text = the area code.
- **FR-4** -- Badge enabled state is driven by a persisted `Set<string>` of
  **area codes** (not public keys).
- **FR-5** -- Clicking a badge toggles its area code in the persisted set; the
  data fetch expands the enabled area set to the underlying public keys and
  sends them as `?observed_by=`.
- **FR-6** -- Enforce "keep at least one area enabled" -- refuse to disable the
  last enabled area (mirrors the existing per-observer guard).
- **FR-7** -- When the user toggles a badge on a page > 1, reset to page 1
  (existing behaviour; preserved).
- **FR-8** -- Observers without an `area` tag never appear as badges but their
  previously-recorded events are still returned when no area filter is active.
- **FR-9** -- When no observers have an `area` tag, render no badge row and apply
  no `observed_by` filter (show all data).
- **FR-10** -- Stale entries in the persisted set (area codes that no longer
  match any current observer) must not cause the data to be over-filtered.

### Technical Requirements

- **TR-1** -- Frontend-only: changes confined to three files under
  `src/meshcore_hub/web/static/js/spa/`.
- **TR-2** -- Use a **new** localStorage key (`meshcore-observer-areas-disabled`)
  rather than reusing `meshcore-observers-disabled`, so the legacy list of
  public keys cannot be misinterpreted as area codes.
- **TR-3** -- No change to `apiGet`'s array-param encoding
  (`api.js:25-41` -- repeated `?observed_by=` keys).
- **TR-4** -- No change to the two-phase fetch (observer list first, then
  filtered data); only the mapping from "disabled set" -> "enabled public keys"
  changes.
- **TR-5** -- Existing i18n strings reused; no new keys.

## Implementation Plan

### Phase 1: Shared helpers and badge component (`components.js`)

File: `src/meshcore_hub/web/static/js/spa/components.js` (lines 588-668).

- **Rename the localStorage key** (line 592):
  `meshcore-observers-disabled` -> `meshcore-observer-areas-disabled`.
- **Rename + re-scope the helpers**:
  - `getDisabledObservers()` -> `getDisabledObserverAreas()` (lines 598-607) --
    same JSON parse + safe-empty-on-error logic, new key.
  - `setDisabledObservers(set)` -> `setDisabledObserverAreas(set)` (lines
    613-619).
  - `toggleObserver(pubkey, totalObserverCount)` ->
    `toggleObserverArea(area, totalAreaCount)` (lines 628-641) -- same
    "block last disable" guard (`totalAreaCount - disabled.size <= 1`),
    operates on area-code strings.
- **Reshape `observerFilterBadges` signature** (lines 643-668) from
  `{ nodes, disabled, onToggle, extraClass }` to
  `{ areas, disabled, onToggle, extraClass }`:
  - `areas`: `string[]` of area codes (already sorted by the caller).
  - Return `nothing` if `areas.length === 0`.
  - Per-badge: label = area code; enabled state = `!disabled.has(area)`;
    `@click=${() => onToggle(area)}`.
  - Existing styling (`badge badge-primary` / `badge badge-ghost opacity-50`),
    tooltip i18n keys (`filter_observer_enable` / `filter_observer_disable`),
    row label (`filter_observer_label`), and `extraClass` responsive-visibility
    contract all unchanged.
- **Leave `observerIcons` (lines 568-573) untouched** -- per-row tooltip keeps
  using `o.tag_name || o.name`.

### Phase 2: Adverts page wiring (`advertisements.js`)

File: `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`.

- **Imports (line 8)**: replace `getDisabledObservers, toggleObserver` with
  `getDisabledObserverAreas, toggleObserverArea`. Keep `observerFilterBadges`,
  `observerIcons`, `routeTypeBadge`.
- **Closure init (line 25)**:
  `let disabledObserverAreas = getDisabledObserverAreas();`
- **Replace the per-node map/sort/enabled-keys block (lines 104-114)** with
  area grouping:
  ```js
  const areaMap = new Map(); // area -> public_key[]
  for (const n of allNodes) {
      const area = n.tags?.find(tg => tg.key === 'area')?.value;
      if (!area || !area.trim()) continue;
      const key = area.trim();
      if (!areaMap.has(key)) areaMap.set(key, []);
      areaMap.get(key).push(n.public_key);
  }
  const sortedAreas = [...areaMap.keys()]
      .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  const enabledObserverKeys = sortedAreas
      .filter(a => !disabledObserverAreas.has(a))
      .flatMap(a => areaMap.get(a));
  // Only constrain when some current area is actually hidden.
  const observerFilterActive = sortedAreas.some(a => disabledObserverAreas.has(a));
  ```
- **Toggle handler (lines 116-127)**: rename param `pubkey` -> `area`; call
  `disabledObserverAreas = toggleObserverArea(area, sortedAreas.length);`.
  Navigation/page-reset logic unchanged.
- **Data fetch (lines 130-133)**: `apiParams.observed_by = enabledObserverKeys`
  when `observerFilterActive` -- unchanged mechanically, just sourced from the
  new area expansion.
- **Badge factory (lines 139-141)**: pass `areas: sortedAreas` instead of
  `nodes: sortedNodes`.

### Phase 3: Messages page wiring (`messages.js`)

File: `src/meshcore_hub/web/static/js/spa/pages/messages.js`.

Mirror Phase 2 at the corresponding locations:
- Imports (line 9).
- Closure init (line 26).
- Per-node block (lines 268-278).
- Toggle handler (lines 280-291).
- Badge factory (lines 302-304).

The data fetch (lines 293-297) and `channelLabels` plumbing are unaffected.

### Phase 4: Legacy cleanup and build

- **Legacy localStorage cleanup in `app.js`**: at the top of the boot sequence
  (after locale load, before router start), add an idempotent one-time cleanup:
  ```js
  try { localStorage.removeItem('meshcore-observers-disabled'); } catch {}
  ```
  This removes the orphaned key so users don't accumulate stale keys in dev
  tools. Runs unconditionally on every page load — harmless and idempotent.
- Rebuild the SPA bundle (`make build`, which runs the Docker image build that
  bundles `dist/`).
- `make up`, then manually exercise the verification checklist below.
- `pre-commit run --all-files` — no Python changes, but the hook runs on the
  whole tree and will catch any JS lint config if present.

## Edge cases & invariants

- **Observer with `is_observer=true` but no `area` tag** -> filtered out by the
  `if (!area || !area.trim()) continue` guard; never rendered as a badge.
- **Empty / whitespace-only `area` value** -> treated as missing (trimmed check).
- **Multiple observers sharing an area** -> collapse into a single badge; toggle
  affects all of them via the `areaMap` expansion.
- **Zero observers have area tags** -> `sortedAreas=[]`; `observerFilterBadges`
  returns `nothing`; `observerFilterActive=false`; no `observed_by` sent; all
  data shown.
- **Stale area codes in localStorage** (an area that no longer exists) -> never
  matched in `sortedAreas.some(...)`, so `observerFilterActive` stays false and
  no over-filtering occurs. Harmless.
- **"Block last disable"** -> uses `sortedAreas.length` so the rule is now "keep
  >= 1 area enabled", which is the correct invariant for grouped badges.
- **Non-area observers excluded when filter active** -> when at least one area
  badge is toggled off, `observerFilterActive=true` and `enabledObserverKeys`
  contains only keys from enabled areas. Observers without an `area` tag are not
  in that set, so their events are excluded from results alongside the disabled
  areas. This is intentional: area filtering means "show me only events from
  these areas." Non-area observers' events reappear when all areas are re-enabled
  (i.e., no filter active).
- **Legacy `meshcore-observers-disabled` key** -> one-time cleanup on SPA boot
  is included in Phase 4.

## Verification

Manual checklist after `make build && make up`:

- `/advertisements` and `/messages` each show one badge per unique area code
  present among observer nodes (e.g. `IP2`, `IP3`, `IP4`, `IP8`).
- Observers with `is_observer=true` but no `area` tag do **not** appear as
  badges.
- Clicking an area badge greys it out and re-scopes the list to events observed
  by nodes in the still-enabled areas; page resets to 1 if currently > 1.
- Reload the page -> selection restored from `localStorage` before the first
  data fetch (no flash of unfiltered data).
- Switch between Adverts and Messages -> same area selection applies (shared
  key).
- Attempt to disable the last enabled area -> blocked.
- Per-row observer-count badge tooltip still shows observer **names**
  (unchanged).
- Filter row label still reads "Observer".
- DevTools -> Application -> Local Storage: the new
  `meshcore-observer-areas-disabled` key holds an array of area-code strings;
  the old `meshcore-observers-disabled` key is removed by the one-time cleanup in `app.js`.

## Open Questions

All resolved during review.

- **Legacy localStorage cleanup** -> **RESOLVED**: Yes, add `localStorage.removeItem('meshcore-observers-disabled')` in `app.js` boot (Phase 4).
- **Empty-area fallback display** -> **RESOLVED**: Observers without `area` are hidden from badges; their events appear when no area filter is active. The non-area exclusion when filter IS active is documented as an explicit edge case.
- **JS unit tests** -> **RESOLVED (deferred)**: No existing JS test harness; adding one is a worthwhile follow-up but out of scope for this plan.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-07

### Resolutions

- **Legacy localStorage cleanup**: Add `localStorage.removeItem('meshcore-observers-disabled')` in `app.js` at SPA boot (idempotent, harmless).
- **Non-area observer exclusion when filter active**: Documented as intentional edge case — area filtering means "show only events from selected areas," so un-categorized observers are excluded alongside disabled areas.
- **Line number correction**: `advertisements.js` data fetch lines corrected from 129-133 to 130-133.
- **JS unit tests**: Deferred — no harness exists; logic is simple and manually verifiable.

### Remaining Action Items

- Confirm the build produces a correct SPA bundle after changes (Phase 4 verification).

## References

- `docs/plans/20260614-1220-observer-filter-badges/plan.md` -- original design
  spec for the badge UI being modified here (data flow, two-phase fetch,
  localStorage-disabled-set model, "block last disable" guard).
- `docs/plans/2026-06-14-observer-filter-cache-key-collision/plan.md` -- earlier
  fix to the API cache key for repeated `observed_by` values; unaffected by this
  change but referenced for completeness.
- `docs/plans/20260625-2005-observer-ingestion-filters/plan.md` -- unrelated
  collector-side observer allow/deny filter; cited to disambiguate the two
  meanings of "observer filter" in this codebase.
- `seed/node_tags.yaml` -- source of `area` tag values already loaded into
  `node_tags` (e.g. `IP2`, `IP3`, `IP4`, `IP8`).
- `src/meshcore_hub/api/routes/nodes.py:62-64,154-157` -- `?observer=true` filter
  on `Node.is_observer` (unchanged).
- `src/meshcore_hub/api/observer_utils.py:13-37` -- `observed_by_filter_clause`
  joins `event_observers` on `Node.public_key` (unchanged; still receives
  public keys expanded from the enabled area set).
