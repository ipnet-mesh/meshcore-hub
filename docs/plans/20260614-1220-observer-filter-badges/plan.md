# Plan: Observer filter as toggle badges (Adverts & Messages)

## Goal
Replace the multi-select Observer dropdown (currently buried in the Filter panel) with a
row of clickable observer **badges** rendered between the filter panel and the data list.
Selection persists in `localStorage` (shared across both pages), defaults to all-enabled,
and is applied to the first API call on load.

## Motivation
The Observer filter on the Advert and Message pages is hard to reach (inside the collapsed
filter panel, as a multi-select `<select>`). Many users only care about a single observer or
a specific set, and re-opening the filter panel each visit is a chore. Badges give one-click
toggling, visible state, and remembered preferences across sessions.

## Confirmed decisions
- **Shared selection** across Adverts + Messages (single localStorage key).
- **Block the last toggle-off** — always keep >= 1 observer enabled.
- **Reset to page 1 on toggle** — toggling re-scopes the data, so navigate to the base path
  (dropping `page`) and re-fetch.

## Core model
Persist the **disabled** set, not the enabled set. Storing deselected pubkeys means any
newly-discovered observer node defaults to enabled automatically (matches "by default all
observers enabled").

- localStorage key: `meshcore-observers-disabled` -> JSON array of pubkeys.
- Effective filter = all observer nodes minus the disabled set.
- If disabled set is empty -> send **no** `observed_by` param (show all).
- If some disabled -> send `observed_by` = enabled pubkeys.
- **Implementation note (deviation):** the adverts/messages API filters observers by
  *inclusion only* (`observed_by` is an include-list; there is no exclude param). So the data
  fetch genuinely depends on the full observer node list to translate the stored disabled set
  into an include-list. Implemented as a **two-phase fetch**: phase 1 fetches the observer
  nodes (plus channels/profiles), phase 2 fetches the data with the resolved `observed_by`.
  This is fully correct (always uses the fresh node list) and produces no flash of unfiltered
  data, at the cost of the main data call waiting on the (small) nodes call. The original
  "derive synchronously from localStorage, fetch in parallel" idea is not achievable without a
  client-side cache of observer pubkeys; two-phase was chosen as the simpler, always-correct
  option.
- `observerFilterActive` is gated on `enabledKeys.length < sortedNodes.length`, so a stale
  disabled key that no longer matches any current node does not accidentally filter everything.

## Source-of-truth change
Today `observed_by` lives in the **URL query string** and is threaded through pagination/sort
links and the filter form. Moving to localStorage means:
- Remove `observed_by` from the filter panel, from `headerParams`, and from `pagination(...)`
  params on both pages.
- Toggling a badge updates localStorage and re-scopes the data (reset to page 1). Page/sort/
  search stay in the URL; observer selection does not.

### Why pagination is not broken
- Pagination is driven by the `page` param, which stays in the URL. `observed_by` was only
  carried along so the filter survived a page click.
- Every navigation re-invokes the page's `render()`, which re-reads `getDisabledObservers()`
  at the top, so the same filter is applied on every page. localStorage is stable across
  navigations, so total count / page count stay consistent while paging.
- Toggling a badge can make the current page number out of range, so the toggle handler resets
  to page 1 (navigates to the base path without `page`, then re-fetches).

## Files to change

### 1. `src/meshcore_hub/web/static/js/spa/components.js` — add helpers + component
- localStorage helpers (mirroring the theme pattern in `spa.html`):
  - `getDisabledObservers()` -> `Set<string>` (safe JSON parse, returns empty set on error).
  - `setDisabledObservers(set)` -> persists JSON array.
  - `toggleObserver(pubkey, totalObserverCount)` -> updates the set, enforcing the
    "keep >= 1 enabled" guard (refuse to disable the last enabled observer); returns the new set.
- `observerFilterBadges({ nodes, disabled, onToggle, extraClass })` component:
  - Returns `nothing` if `nodes.length === 0`.
  - Small label (`common.filter_observer_label`) + one badge per observer (using `n._displayName`).
  - **Enabled** badge: `badge badge-primary` (filled). **Disabled** badge: `badge badge-ghost`
    + `opacity-50` (muted/outlined). Each `cursor-pointer`, `@click=${() => onToggle(n.public_key)}`,
    with a `title` tooltip (enable/disable).
  - Optional "All" / "None" quick-toggle chips at the start of the row (nice-to-have; "None"
    still respects the keep->=1 guard).
  - `extraClass` lets the caller apply responsive visibility (`hidden lg:flex` vs `lg:hidden`).

### 2. `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`
- Remove `observed_by` read from `query`; instead keep a closure variable
  `disabledObservers = getDisabledObservers()`.
- In `fetchAndRenderData`: compute `enabled = sortedNodes.filter(n => !disabledObservers.has(n.public_key))`;
  set `apiParams.observed_by = enabled.map(n => n.public_key)` only when `disabledObservers.size > 0`.
- Remove the `nodesFilter` `<select>` from `filterFields`; drop `observed_by` from
  `headerParams`, `pagination`, and `hasActiveFilters`.
- Add `onToggle(pubkey)` handler:
  1. Apply `toggleObserver` guard + persist.
  2. Update closure `disabledObservers`.
  3. Reset to page 1: `navigate('/advertisements?...')` rebuilt from current search/sort/order/limit
     **without** `page` (or navigate to base path when no other params). This re-runs `render()`,
     which re-reads localStorage and re-fetches.
- Render two badge blocks:
  - **Desktop**: `observerFilterBadges({ ..., extraClass: 'hidden lg:flex mb-4' })` immediately
    after `filterCard`.
  - **Mobile**: `observerFilterBadges({ ..., extraClass: 'lg:hidden mb-4' })` between
    `mobileSortSelect(...)` and the mobile cards `<div>`.

### 3. `src/meshcore_hub/web/static/js/spa/pages/messages.js`
- Identical changes: remove the `observerFilter` `<select>` + URL threading, add closure
  `disabledObservers`, add `onToggle` (reset to page 1 via `/messages?...`), add the two badge
  blocks (mobile block after `mobileSortSelect`, before mobile cards).

### 4. Locales `locales/en.json` + `locales/nl.json`
- Add under `common`: badge tooltip key (e.g. `filter_observer_toggle`) and, if quick-toggles
  are added, `filter_observer_all` / `filter_observer_none`. Reuse existing
  `filter_observer_label` for the row label.

### 5. Build
- Run `npm run build` (esbuild bundles `dist/`; `spa.html` loads the hashed bundle). Required
  for the change to appear.

## Cross-link audit (confirmed safe to remove from URL)
- `?observer_id` is **not** a frontend navigation param at all — it only exists in the Python
  API as a SQL column label / internal variable (`raw_packets.py`, `messages.py`,
  `advertisements.py`, `packet_groups.py`).
- `observed_by` in the frontend is only ever: (a) a **data field** on records used to build
  `/nodes/<pubkey>` links (`packet-detail.js`, `packet-group-detail.js`, `node-detail.js`) —
  not a query string; or (b) **internal to the Adverts/Messages pages** (the filter `<select>`
  + their own pagination/sort link threading).
- **No other page** links to `/advertisements?observed_by=` or `/messages?observed_by=`. The
  only cross-link into these routes carrying a query is `channels.js -> /messages?channel_idx=`,
  which uses `channel_idx` (untouched; the messages page keeps reading it from the URL).
- Therefore removing `observed_by` from URL threading breaks nothing in site navigation. Only a
  hand-crafted/bookmarked external link would be affected -> covered by optional add-on (b).

## Notes / trade-offs
- **No URL backward-compat**: existing `?observed_by=` links stop filtering. Acceptable given
  the redesign and the cross-link audit above. Optional add-on: a one-time URL->localStorage
  migration on load so old links keep working.
- **Empty-selection guard**: keep-at-least-one-enabled avoids a confusing empty list and an
  ambiguous "all disabled == all enabled" API call.
- Styling uses existing DaisyUI badge classes — no `app.css` changes expected.
- Auto-refresh keeps working unchanged (it calls `fetchAndRenderData`, which reads current
  localStorage state).

## Optional add-ons (opt-in)
- (a) "All" / "None" quick-toggle chips on the badge row.
- (b) URL->localStorage migration for old `?observed_by=` links.

## Verification
- Toggle an observer off on Adverts -> list re-scopes, page resets to 1, badge greys out.
- Reload page -> selection restored from localStorage before first API call (filtered results
  appear immediately, no flash of unfiltered data).
- Switch to Messages -> same selection applies (shared key).
- Page through results -> filter persists, total/page count consistent.
- Disable all but one, attempt to disable the last -> blocked, stays enabled.
- Mobile viewport -> badges appear below the Sorting dropdown, above the cards.
