# Tasks — Improve Filter Options

## Phase 1: Backend API Changes

- [x] **1.1** Remove `public_key` filter from `src/meshcore_hub/api/routes/advertisements.py`
  - Remove `public_key: Optional[str] = Query(...)` param declaration (lines 48–49)
  - Remove `if public_key: query = query.where(Advertisement.public_key == public_key)` WHERE clause (lines 97–98)

- [x] **1.2** Change `observed_by` to `list[str]` in `src/meshcore_hub/api/routes/advertisements.py`
  - Change type: `Optional[str]` → `Optional[list[str]]` (line 50)
  - Change WHERE: `== observed_by` → `.in_(observed_by)` (line 101)
  - Update `asyncio.gather` to remove `public_key` from fetch if present (lines 85–96, review only)

- [x] **1.3** Change `observed_by` to `list[str]` in `src/meshcore_hub/api/routes/messages.py`
  - Change type: `Optional[str]` → `Optional[list[str]]` (line 36)
  - Change WHERE: `== observed_by` → `.in_(observed_by)` (line 67)

## Phase 2: Frontend Infrastructure Fixes

- [x] **2.1** Fix router query parsing in `src/meshcore_hub/web/static/js/spa/router.js` (line 100)
  - Replace `Object.fromEntries(new URLSearchParams(...))` with loop that promotes duplicate keys to arrays
  - Single values remain strings; duplicate keys become `[value1, value2]`

- [x] **2.2** Add array param support to `apiGet` in `src/meshcore_hub/web/static/js/spa/api.js` (line 17)
  - Detect `Array.isArray(v)` and call `url.searchParams.append(k, String(item))` per element
  - Non-array values pass through existing `url.searchParams.set(k, String(v))`

- [x] **2.3** Add array param support to `pagination` in `src/meshcore_hub/web/static/js/spa/components.js` (lines 423–427)
  - Same array-handling pattern: `Array.isArray(v)` → append per element, otherwise `encodeURIComponent`

- [x] **2.4** Fix `createFilterHandler` for multi-value in `src/meshcore_hub/web/static/js/spa/components.js` (lines 558–562)
  - Replace `params.set(k, v)` with `params.append(k, v)`
  - Iterate `new Set(formData.keys())` to get unique keys, then use `formData.getAll(k)` per key

## Phase 3: Collapsible Filter Section

- [x] **3.1** Update `renderFilterCard` signature in `src/meshcore_hub/web/static/js/spa/components.js` (line 659)
  - Add `collapsible = false` and `defaultOpen = false` parameters

- [x] **3.2** Implement collapsible rendering in `renderFilterCard`
  - When `!collapsible`: render existing card layout unchanged
  - When `collapsible`: wrap form in `<details class="collapse collapse-arrow bg-base-200 border border-base-300 rounded-box mb-6" ?open=${defaultOpen}>` with `<summary class="collapse-title text-sm font-medium cursor-pointer">${t('common.filters')}</summary>` and form in `<div class="collapse-content pt-4">`

## Phase 4: Advertisements Page

- [x] **4.1** Remove node filter from `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`
  - Remove `const public_key = query.public_key || '';` (line 14)
  - Remove `public_key` from `apiParams` (`apiParams.append` → direct object property) (line 54)
  - Remove `public_key` from pagination params (line 176)
  - Remove `nodesFilter` template block (lines 78–89)
  - Keep `/api/v1/nodes` fetch (line 58) and `sortedNodes` mapping (lines 73–76) for observer dropdown

- [x] **4.2** Add observer multi-select to advertisements page
  - Extract `observed_by` from router query: handle both string and array (guard with `Array.isArray()`)
  - Add observer `<select multiple size="6">` template using `sortedNodes` with DaisyUI classes
  - Push observer field to `filterFields` array (between search and member, guarded by `sortedNodes.length > 0`)
  - Pass `observed_by` array in `apiParams` when non-empty

- [x] **4.3** Enable collapsible mode with state preservation on advertisements page
  - Compute `hasActiveFilters` from `search`, `observed_by.length`, and `adopted_by` (when OIDC enabled)
  - Before each re-render, read `container.querySelector('details.collapse').open` from DOM
  - Pass `collapsible: true` and `defaultOpen: isFilterOpen` to `renderFilterCard`

## Phase 5: Messages Page

- [x] **5.1** Add node fetch to `src/meshcore_hub/web/static/js/spa/pages/messages.js`
  - Add `apiGet('/api/v1/nodes', { limit: 500 })` in `fetchAndRenderData`
  - Build `sortedNodes` mapping with `_displayName` and `_sortName` (same pattern as ads)

- [x] **5.2** Add observer multi-select to messages page
  - Extract `observed_by` from router query (same pattern as ads)
  - Add observer `<select multiple size="6">` template using `sortedNodes`
  - Push observer field to `filterFields` array (after type and channel selects)
  - Pass `observed_by` array in `apiParams` when non-empty
  - Include `observed_by` in pagination params

- [x] **5.3** Enable collapsible mode with state preservation on messages page
  - Compute `hasActiveFilters` from `message_type`, `channel_idx`, and `observed_by.length`
  - Before each re-render, read `container.querySelector('details.collapse').open` from DOM
  - Pass `collapsible: true` and `defaultOpen: isFilterOpen` to `renderFilterCard`

## Phase 6: i18n

- [x] **6.1** Add new keys to `src/meshcore_hub/web/static/locales/en.json` under `"common"`:
  - `"filters": "Filters"` — collapse title
  - `"filter_observer_label": "Observer"` — multi-select label

## Phase 7: Tests

- [x] **7.1** Update `tests/test_api/test_advertisements.py`
  - Remove tests exercising the `public_key` query parameter
  - Add test: single observer filter returns matching ads
  - Add test: multiple observer filter returns ads from any matching observer

- [x] **7.2** Update `tests/test_api/test_messages.py`
  - Add test: single observer filter returns matching messages
  - Add test: multiple observer filter returns messages from any matching observer

## Verification

- [x] Run `pytest tests/test_api/test_advertisements.py -v`
- [x] Run `pytest tests/test_api/test_messages.py -v`
- [x] Manually verify in browser:
  - Advertisements page: no node filter, observer multi-select in collapsible section
  - Messages page: observer multi-select in collapsible section
  - Multi-value selection → URL reflects `?observed_by=a&observed_by=b`
  - Pagination preserves observer params
  - Auto-refresh preserves collapse state
  - Backward-compatible: single-select filters still work via Filter button
- [x] Run `pre-commit run --all-files`
