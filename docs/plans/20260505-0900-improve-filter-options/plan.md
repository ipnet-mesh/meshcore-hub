# Plan: Improve Filter Options — Remove Node Filter & Add Observer Multi-Select

**Date**: 2026-05-05
**Status**: Draft

---

## Summary

Two changes to the Advertisements and Messages pages:

1. **Remove the Node filter** from the Advertisements page (frontend dropdown + API query param `public_key`)
2. **Add an Observer multi-select filter** to both Advertisements and Messages pages, using a standard `<select multiple>` inside a collapsible filter section (DaisyUI `collapse`, collapsed by default)

The collapsible section solves the vertical space concern: the multi-select only consumes space when the user expands the filter panel.

---

## Current State

| Feature | Ads Backend | Ads Frontend | Msgs Backend | Msgs Frontend |
|---|---|---|---|---|
| `public_key` (node filter) | Yes | **Yes (remove)** | N/A | N/A |
| `observed_by` (observer) | Yes (single) | **No** | Yes (single) | **No** |
| Search text | Yes | Yes | Yes | No |
| `since`/`until` timestamps | Yes | No | Yes | No |
| `adopted_by` (member) | Yes | Yes (OIDC cond.) | N/A | N/A |
| `message_type` | N/A | N/A | Yes | Yes |
| `channel_idx` | N/A | N/A | Yes | Yes |
| `pubkey_prefix` (sender) | N/A | N/A | Yes | No |

### Key files

- **Advertisements API**: `src/meshcore_hub/api/routes/advertisements.py` — `list_advertisements()` endpoint, query params at lines 42–59
- **Messages API**: `src/meshcore_hub/api/routes/messages.py` — `list_messages()` endpoint, query params at lines 29–43
- **Advertisements frontend**: `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` — filter form at lines 179–215, node filter at lines 73–89
- **Messages frontend**: `src/meshcore_hub/web/static/js/spa/pages/messages.js` — filter form at lines 306–334
- **Shared components**: `src/meshcore_hub/web/static/js/spa/components.js` — `renderFilterCard` (line 659), `createFilterHandler` (line 555), `pagination` (line 419)
- **Router**: `src/meshcore_hub/web/static/js/spa/router.js` — query parsing at line 100
- **API client**: `src/meshcore_hub/web/static/js/spa/api.js` — `apiGet` at line 13
- **i18n**: `src/meshcore_hub/web/static/locales/en.json`
- **DaisyUI collapse**: `node_modules/daisyui/components/collapse.css` — supports both checkbox-based and `<details>`-based toggling

---

## Change 1: Remove Node Filter from Advertisements

**Rationale**: The `public_key` filter filters by the originating node. Since ads already show the originating node in the table and users navigate from there, this filter adds little value beyond the existing `search` field (which already matches node names, tag names, and public keys with `ILIKE` wildcards). Removing it simplifies the UI and frees its slot for the observer filter.

### 1a. Frontend — `advertisements.js`

Lines to remove/change:
- **Line 14**: Remove `const public_key = query.public_key || '';`
- **Line 54**: Remove `public_key` from `apiParams` → `const apiParams = { limit, offset, search };`
- **Lines 73–89**: Remove the entire `sortedNodes` mapping + `nodesFilter` template block. The `/api/v1/nodes` fetch (line 58) is **kept** and repurposed to populate the observer multi-select (see Change 2e).
- **Lines 188–190**: Remove `if (sortedNodes.length > 0) { filterFields.push(() => nodesFilter); }`
- **Line 176**: Remove `public_key` from pagination params

### 1b. Backend — `advertisements.py`

- **Lines 48–49**: Remove `public_key: Optional[str] = Query(None, description="Filter by public key")`
- **Lines 97–98**: Remove `if public_key: query = query.where(Advertisement.public_key == public_key)`

### 1c. Tests

- `tests/test_api/test_advertisements.py` — remove or update tests exercising the `public_key` query parameter

---

## Change 2: Add Observer Multi-Select Filter

**Rationale**: Both APIs already support `observed_by` (filtering by which observer node received the event) as a single-value parameter. Making it multi-value and exposing it in the frontend lets users filter events by one or more observer nodes. Wrapping the filter form in a collapsible section keeps the multi-select from permanently consuming vertical space.

### 2a. Backend — Both API Routes

**`advertisements.py`** (lines 50–52, 100–101):
```python
# Before
observed_by: Optional[str] = Query(None, description="Filter by receiver node public key")
# After
observed_by: Optional[list[str]] = Query(None, description="Filter by receiver node public keys")
```

```python
# Before
if observed_by:
    query = query.where(ObserverNode.public_key == observed_by)
# After
if observed_by:
    query = query.where(ObserverNode.public_key.in_(observed_by))
```

**`messages.py`** (lines 36–38, 66–67): Same changes.

FastAPI natively supports `?observed_by=key1&observed_by=key2` for `list[str]` query params. A single value (`?observed_by=key1`) is parsed as `["key1"]` — fully backward-compatible with `.in_()`.

### 2b. Router Multi-Value Query Parsing — `router.js`

**File**: `router.js`, line 100

**Problem**: `Object.fromEntries(new URLSearchParams(window.location.search))` **overwrites duplicate keys**. For `?observed_by=a&observed_by=b`, the result is `{ observed_by: "b" }` — only the last value survives.

**Fix**: Modify query parsing to promote duplicate keys to arrays, keeping single values as strings:

```js
// Before (line 100)
const query = Object.fromEntries(new URLSearchParams(window.location.search));

// After
const sp = new URLSearchParams(window.location.search);
const query = {};
for (const [k, v] of sp.entries()) {
    if (k in query) {
        query[k] = Array.isArray(query[k]) ? [...query[k], v] : [query[k], v];
    } else {
        query[k] = v;
    }
}
```

Behavior: `?search=foo` → `{ search: "foo" }` (string). `?observed_by=a&observed_by=b` → `{ observed_by: ["a", "b"] }` (array). `?observed_by=a` → `{ observed_by: "a" }` (string — single values unchanged). Backward-compatible with all existing pages.

### 2c. API Client Array Params — `api.js`

**File**: `api.js`, `apiGet` function (line 13–18)

**Problem**: `url.searchParams.set(k, String(v))` converts `['a','b']` to `"a,b"` instead of separate `observed_by=a&observed_by=b` entries.

**Fix**: Detect array values and call `.append()` per element:

```js
// Before
export async function apiGet(path, params = {}) {
    const url = new URL(path, window.location.origin);
    for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined && v !== '') {
            url.searchParams.set(k, String(v));
        }
    }
    // ...
}

// After
export async function apiGet(path, params = {}) {
    const url = new URL(path, window.location.origin);
    for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined && v !== '') {
            if (Array.isArray(v)) {
                v.forEach(item => url.searchParams.append(k, String(item)));
            } else {
                url.searchParams.set(k, String(v));
            }
        }
    }
    // ...
}
```

### 2d. Pagination Array Params — `components.js`

**File**: `components.js`, `pagination` function (lines 419–428)

**Problem**: `encodeURIComponent(v)` on an array serializes to `"a%2Cb"` — wrong.

**Fix**: Handle array values by appending multiple key-value pairs:

```js
// Before
for (const [k, v] of Object.entries(params)) {
    if (k !== 'page' && v !== null && v !== undefined && v !== '') {
        queryParts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
}

// After
for (const [k, v] of Object.entries(params)) {
    if (k === 'page' || v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) {
        v.forEach(item => queryParts.push(`${encodeURIComponent(k)}=${encodeURIComponent(item)}`));
    } else {
        queryParts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
}
```

### 2e. Multi-Value Form Handler — `components.js`

**File**: `components.js`, function `createFilterHandler` (lines 555–566)

The current handler uses `params.set(k, v)` which overwrites duplicate keys. Multi-value form fields (`<select multiple>`) produce multiple entries with the same name — these need `params.append(k, v)`.

```js
// Before
export function createFilterHandler(basePath, navigate) {
    return (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const params = new URLSearchParams();
        for (const [k, v] of formData.entries()) {
            if (v) params.set(k, v);
        }
        const queryStr = params.toString();
        navigate(queryStr ? `${basePath}?${queryStr}` : basePath);
    };
}

// After
export function createFilterHandler(basePath, navigate) {
    return (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const params = new URLSearchParams();
        const keys = new Set(formData.keys());
        for (const k of keys) {
            for (const v of formData.getAll(k)) {
                if (v) params.append(k, v);
            }
        }
        const queryStr = params.toString();
        navigate(queryStr ? `${basePath}?${queryStr}` : basePath);
    };
}
```

Backward-compatible: single-select `<select>` elements produce one entry per key, so `append` with one value behaves identically to `set`.

### 2f. Observer Multi-Select Field Template

Standard `<select multiple>` with DaisyUI classes:

```html
<div class="form-control">
    <label class="label py-1">
        <span class="label-text">${t('common.filter_observer_label')}</span>
    </label>
    <select name="observed_by" multiple size="6"
            class="select select-bordered select-sm w-full max-w-xs">
        ${sortedNodes.map(n => html`
            <option value=${n.public_key}
                    ?selected=${observed_by.includes(n.public_key)}>
                ${n._displayName}
            </option>
        `)}
    </select>
</div>
```

Key design decisions:
- `size="6"` — shows 6 rows; scrollable when there are more nodes (browser-native scrollbar)
- `max-w-xs` — prevents the select from growing too wide
- No `@change=${autoSubmit}` — user makes selections then clicks the Filter button (inside the collapse)
- Pre-selection via `?selected=` binds to URL state
- Nodes are sorted by display name (same as existing node dropdown in ads)

### 2g. Collapsible Filter Section — `components.js`

Modify `renderFilterCard` to accept a `collapsible` option. When enabled, the form is wrapped in a DaisyUI `collapse` component using native `<details>`/`<summary>`.

**DaisyUI collapse with `<details>`:**

```html
<details class="collapse collapse-arrow bg-base-200 border border-base-300 rounded-box mb-6"
         ?open=${defaultOpen}>
    <summary class="collapse-title text-sm font-medium cursor-pointer">
        Filters
    </summary>
    <div class="collapse-content pt-4">
        <!-- form goes here -->
    </div>
</details>
```

DaisyUI's collapse CSS responds to the native `[open]` attribute on `<details>`, with an animated expand/collapse via `grid-template-rows` transition. Clicking the `<summary>` toggles `open` natively (no JS, no checkbox). `?open=${defaultOpen}` sets the initial state from lit-html.

**Updated `renderFilterCard` signature:**

```js
export function renderFilterCard({
    fields, basePath, navigate,
    submitLabel, clearLabel,
    collapsible = false,      // NEW: wrap in <details> collapse
    defaultOpen = false,      // NEW: <details open> when active filters exist
}) { ... }
```

**Behavior:**
- When `collapsible: true` and `defaultOpen: false` → collapse starts closed
- When `collapsible: true` and `defaultOpen: true` → collapse starts expanded (user sees active filters)
- Page modules compute `defaultOpen` by checking whether any filter is active (e.g., `search !== '' || observed_by.length > 0 || ...`)
- Clicking the summary title toggles open/closed with DaisyUI's animated transition

**Structure when collapsible:**
```
┌──────────────────────────────────────┐
│ Filters                          ▼  │  ← <summary> (always visible)
├──────────────────────────────────────┤
│ [search input]    [Observer multi]   │  ← <div class="collapse-content">
│ [Member select]                      │    (hidden when closed)
│ [Filter btn] [Clear]                 │
└──────────────────────────────────────┘
```

**Implementation for `renderFilterCard`:**

```js
export function renderFilterCard({ fields, basePath, navigate, submitLabel, clearLabel, collapsible = false, defaultOpen = false }) {
    const formBody = html`
        <form method="GET" action=${basePath}
              class="flex gap-4 flex-wrap items-end"
              @submit=${createFilterHandler(basePath, navigate)}>
            ${fields.map(f => f())}
            <div class="flex gap-2 w-full sm:w-auto">
                <button type="submit" class="btn btn-primary btn-sm">
                    ${submitLabel || t('common.filter')}
                </button>
                <a href=${basePath} class="btn btn-ghost btn-sm">
                    ${clearLabel || t('common.clear')}
                </a>
            </div>
        </form>
    `;

    if (!collapsible) {
        return html`
            <div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
                <div class="card-body py-4">${formBody}</div>
            </div>
        `;
    }

    return html`
        <details class="collapse collapse-arrow bg-base-200 border border-base-300 rounded-box mb-6"
                 ?open=${defaultOpen}>
            <summary class="collapse-title text-sm font-medium cursor-pointer">
                ${t('common.filters')}
            </summary>
            <div class="collapse-content pt-4">
                ${formBody}
            </div>
        </details>
    `;
}
```

Note: When the collapse is closed, the form fields are still in the DOM (only visually clipped via `overflow: hidden`). The Filter button is only visible when expanded, so submission only happens with user intent.

**Collapse state preservation across auto-refresh:** Both pages use `createAutoRefresh` which calls `fetchAndRenderData` periodically, re-rendering the entire page (including the filter card). Without mitigation, `?open=${defaultOpen}` would reset the collapse state on every refresh tick.

**Fix**: Before re-rendering, read the current `<details>.open` DOM state and pass it as `defaultOpen`:

```js
// In fetchAndRenderData, before building the filter card:
const existingDetails = container.querySelector('details.collapse');
const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;
const filterCard = renderFilterCard({
    fields: filterFields,
    basePath: '/advertisements',
    navigate,
    collapsible: true,
    defaultOpen: isFilterOpen,
});
```

This preserves the user's collapse toggle across re-renders.

### 2h. Frontend — Advertisements Page

**File**: `advertisements.js`

- **Extract** `observed_by` from URL (via router, which now preserves multi-value as array):
  ```js
  const observed_by = query.observed_by
      ? (Array.isArray(query.observed_by) ? query.observed_by : [query.observed_by])
      : [];
  ```

- **Repurpose** the `/api/v1/nodes` fetch (line 58, currently for old node filter) to populate the observer dropdown. Keep `sortedNodes` mapping with `_displayName` and `_sortName` props.

- **Replace** the old `nodesFilter` `<select>` block with the observer multi-select:
  ```js
  const observerFilter = sortedNodes.length > 0
      ? () => html`
          <div class="form-control">
              <label class="label py-1">
                  <span class="label-text">${t('common.filter_observer_label')}</span>
              </label>
              <select name="observed_by" multiple size="6"
                      class="select select-bordered select-sm w-full max-w-xs">
                  ${sortedNodes.map(n => html`
                      <option value=${n.public_key}
                              ?selected=${observed_by.includes(n.public_key)}>
                          ${n._displayName}
                      </option>
                  `)}
              </select>
          </div>`
      : nothing;
  ```

- **Update** `filterFields` array — observer field goes where node filter was (between search and member):
  ```js
  const filterFields = [/* search field */];
  if (sortedNodes.length > 0) {
      filterFields.push(() => observerFilter);  // note: wrapped in closure for lazy render
  }
  if (config.oidc_enabled && profiles.length > 0) {
      filterFields.push(/* member field */);
  }
  ```

- **Pass** `observed_by` array in API params (now supported by `apiGet`):
  ```js
  const apiParams = { limit, offset, search };
  if (observed_by.length > 0) {
      apiParams.observed_by = observed_by;
  }
  ```

- **Update** pagination to include `observed_by` as array (now supported by `pagination`).

- **Enable collapsible** mode with state preservation:
  ```js
  const hasActiveFilters = search !== '' || observed_by.length > 0 || (config.oidc_enabled && adopted_by !== '');
  const existingDetails = container.querySelector('details.collapse');
  const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;
  const filterCard = renderFilterCard({
      fields: filterFields,
      basePath: '/advertisements',
      navigate,
      collapsible: true,
      defaultOpen: isFilterOpen,
  });
  ```

### 2i. Frontend — Messages Page

**File**: `messages.js`

- **Extract** `observed_by` from URL (same pattern as ads)
- **Add** node fetch: `apiGet('/api/v1/nodes', { limit: 500 })` — messages page currently does NOT fetch extra data
- **Build** same observer `<select multiple>` as advertisements
- **Add** to `filterFields` array (after type and channel dropdowns)
- **Pass** `observed_by` in API params
- **Update** pagination to include `observed_by`
- **Enable collapsible** mode with state preservation:
  ```js
  const hasActiveFilters = message_type !== '' || channel_idx !== '' || observed_by.length > 0;
  const existingDetails = container.querySelector('details.collapse');
  const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;
  const filterCard = renderFilterCard({
      fields: filterFields,
      basePath: '/messages',
      navigate,
      collapsible: true,
      defaultOpen: isFilterOpen,
  });
  ```

---

## Change 3: i18n Updates

**File**: `src/meshcore_hub/web/static/locales/en.json`

Add under `"common"`:
```json
"filters": "Filters",
"filter_observer_label": "Observer"
```

(`"observers": "Observers"` already exists at line 98 — needed for observer display, not the filter label.)

---

## Files Changed — Summary

| File | Change |
|---|---|
| `src/meshcore_hub/web/static/js/spa/router.js` | Query parsing: promote duplicate keys to arrays |
| `src/meshcore_hub/web/static/js/spa/api.js` | `apiGet`: detect array param values, call `.append()` per element |
| `src/meshcore_hub/web/static/js/spa/components.js` | `createFilterHandler`: use `getAll`/`append`; `pagination`: handle array params; `renderFilterCard`: add `collapsible` + `defaultOpen` with `<details>`/`<summary>` |
| `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` | Remove node filter; add observer `<select multiple>`; enable collapsible mode with state preservation |
| `src/meshcore_hub/web/static/js/spa/pages/messages.js` | Add observer `<select multiple>` + node fetch; enable collapsible mode with state preservation |
| `src/meshcore_hub/api/routes/advertisements.py` | Remove `public_key` param + WHERE clause; `observed_by` → `list[str]` |
| `src/meshcore_hub/api/routes/messages.py` | `observed_by` → `list[str]` |
| `src/meshcore_hub/web/static/locales/en.json` | Add `filters`, `filter_observer_label` |
| `tests/test_api/test_advertisements.py` | Remove `public_key` tests; add multi-observer tests |
| `tests/test_api/test_messages.py` | Add multi-observer tests |

---

## Verification

```bash
# Targeted backend tests
pytest tests/test_api/test_advertisements.py -v
pytest tests/test_api/test_messages.py -v

# Quality checks
pre-commit run --all-files
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `createFilterHandler` change breaks single-select filters | `formData.getAll()` returns single-element arrays for single-select fields; `append` with one value ≡ `set` |
| Dropped node filter confuses users | The `search` field already finds nodes by name, tag name, or public key prefix with `ILIKE` wildcards |
| Router multi-value parsing affects other pages | Single-value params remain strings (unchanged); only duplicate keys become arrays; no current page ever sends duplicate keys |
| `apiGet` array handling affects other callers | Non-array values pass through `else` branch unchanged; only callers that pass arrays are the new observer pages |
| Collapse state resets on auto-refresh | DOM state read from `container.querySelector('details.collapse').open` before each re-render preserves toggle state |
| Large observer node list makes `<select>` unwieldy | Node fetch limited to 500 (same as existing ads page); `size="6"` with scrollbar handles overflow |
| DaisyUI collapse animation performance | CSS `grid-template-rows` transition with `prefers-reduced-motion` support — well-behaved |
