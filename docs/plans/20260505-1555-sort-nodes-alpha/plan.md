# Plan: Column Sort Controls on List Pages + Alpha Sort Default for Nodes

**Date:** 2026-05-05
**Branch:** `feat/list-sort-controls`

---

## Background

The Nodes, Advertisements, and Messages list pages each render a table with static column headers. Sorting is entirely server-side and hardcoded:

| Page | Current Sort |
|------|-------------|
| Nodes | `last_seen DESC` |
| Advertisements | `received_at DESC` |
| Messages | `received_at DESC` |

Two requests:
1. **Change Nodes default sort** to alpha by display name (name tag → node.name → public_key fallback) so observers/companions don't constantly sit at the top.
2. **Add clickable column headers** on all three list pages so users can sort by any column. Sort state should be encoded in the URL query string, which naturally survives auto-refresh (since auto-refresh re-reads `params.query` on each tick).

---

## Feature 1: Server-Side Sort Parameters (API)

Add `sort` and `order` query parameters to all three list endpoints. The `sort` parameter accepts a set of column names per endpoint; invalid values are ignored (default sort is applied). The `order` parameter accepts `asc` or `desc`.

### 1A. `GET /api/v1/nodes` — `src/meshcore_hub/api/routes/nodes.py`

**New query parameters:**

| Parameter | Type | Default | Valid Values |
|-----------|------|---------|--------------|
| `sort` | `str` | `name` | `name`, `public_key`, `last_seen` |
| `order` | `str` | `asc` (when `sort=name`) / `desc` (when `sort=public_key` or `last_seen`) | `asc`, `desc` |

**Sort column mapping:**

| `sort` value | ORDER BY expression | Index required? |
|-------------|-------------------|----------------|
| `name` (new default) | `COALESCE(name_tag_value, Node.name, Node.public_key)` | Functional index recommended |
| `public_key` | `Node.public_key` | Already indexed |
| `last_seen` | `Node.last_seen` | Already indexed (`ix_nodes_last_seen`) |

**Name sort implementation:**

The display name resolution used in the frontend (`tagName || node.name || truncated public_key`) must be mirrored in SQL. Use a correlated scalar subquery to fetch the `name` tag value:

```python
from sqlalchemy import func

name_tag_subq = (
    select(NodeTag.value)
    .where(NodeTag.node_id == Node.id, NodeTag.key == "name")
    .correlate(Node)
    .scalar_subquery()
)

if sort == "name":
    sort_col = func.coalesce(name_tag_subq, Node.name, Node.public_key)
elif sort == "public_key":
    sort_col = Node.public_key
elif sort == "last_seen":
    sort_col = Node.last_seen
else:
    sort_col = func.coalesce(name_tag_subq, Node.name, Node.public_key)

if order == "desc":
    query = query.order_by(sort_col.desc())
else:
    query = query.order_by(sort_col.asc())
```

**Edge case:** `Node.last_seen` can be `NULL`. When `order=asc` and sorting by `last_seen`, `NULL` values sort first in SQLite (which is fine — unseen nodes naturally sort to top). When `order=desc`, `NULL` values sort last (also fine). No special treatment needed.

**Default change:** The default when no `sort` param is provided changes from `last_seen DESC` to alpha-by-name ascending.

**Functional index (optional optimization):**

An expression index on `COALESCE((SELECT value FROM node_tags WHERE node_id = nodes.id AND key = 'name'), name, public_key)` would speed up name sorts. This can be deferred — SQLite handles ORDER BY reasonably without indexes for typical dataset sizes. If added later, it would go in an Alembic migration.

### 1B. `GET /api/v1/advertisements` — `src/meshcore_hub/api/routes/advertisements.py`

**New query parameters:**

| Parameter | Type | Default | Valid Values |
|-----------|------|---------|--------------|
| `sort` | `str` | `time` | `time`, `node_name`, `public_key` |
| `order` | `str` | `desc` | `asc`, `desc` |

**Sort column mapping:**

| `sort` value | ORDER BY expression |
|-------------|-------------------|
| `time` (default) | `Advertisement.received_at` |
| `node_name` | `COALESCE(name_tag_subq, SourceNode.name, Advertisement.public_key)` |
| `public_key` | `Advertisement.public_key` |

**Node name sort implementation:**

The ads route already joins `SourceNode` (aliased `Node`) via `outerjoin(SourceNode, Advertisement.node_id == SourceNode.id)`. To sort by display name, add a correlated scalar subquery for the name tag — same pattern as the nodes endpoint:

```python
from sqlalchemy import func

# SourceNodeNameTag is an alias for the tag lookup
SourceNodeNameTag = aliased(NodeTag)

name_tag_subq = (
    select(SourceNodeNameTag.value)
    .where(
        SourceNodeNameTag.node_id == SourceNode.id,
        SourceNodeNameTag.key == "name",
    )
    .correlate(SourceNode)
    .scalar_subquery()
)

if sort == "node_name":
    sort_col = func.coalesce(name_tag_subq, SourceNode.name, Advertisement.public_key)
elif sort == "public_key":
    sort_col = Advertisement.public_key
elif sort == "time":
    sort_col = Advertisement.received_at
else:
    sort_col = Advertisement.received_at
```

The `SourceNode` alias is already defined in the route. The `NodeTag` model is already imported. Only the `aliased(NodeTag)` and the subquery are new.

The "Observers" column is not sortable (it is a count from a separate table) and will render as a plain `<th>` header.

### 1C. `GET /api/v1/messages` — `src/meshcore_hub/api/routes/messages.py`

**New query parameters:**

| Parameter | Type | Default | Valid Values |
|-----------|------|---------|--------------|
| `sort` | `str` | `time` | `time`, `type`, `from`, `message` |
| `order` | `str` | `desc` | `asc`, `desc` |

**Sort column mapping:**

| `sort` value | ORDER BY expression |
|-------------|-------------------|
| `time` (default) | `Message.received_at` |
| `type` | `Message.message_type` |
| `from` | `Message.pubkey_prefix` |
| `message` | `Message.text` |

The "Observers" column is not sortable. The "From" column sorts by `pubkey_prefix` (raw value) rather than resolved display name, since sender name resolution happens in a post-query step.

**Note on `message` sort:** Sorting a large text column alphabetically is valid SQL but may have limited UX value. Still included for consistency since the column is displayed.

### Implementation pattern (shared across all three endpoints)

A helper pattern handles validation and defaults:

```python
VALID_SORT_COLUMNS: dict[str, Any] = { ... }  # column name → ORM attribute or expression
DEFAULT_SORT = "name"  # or "time" for ads/messages

sort = sort if sort in VALID_SORT_COLUMNS else DEFAULT_SORT
order = order if order in ("asc", "desc") else "asc" if sort in ("name", "node_name") else "desc"
```

---

## Feature 2: Clickable Sort Headers (Frontend)

### 2A. Shared sort header component — `src/meshcore_hub/web/static/js/spa/components.js`

Add a `sortableTableHeader()` function that renders a `<th>` with an `<a>` link. Clicking cycles through: none → asc → desc → none.

**Signature:**

```js
export function sortableTableHeader(label, { sortKey, currentSort, currentOrder, navigate, basePath, params })
```

**Parameters:**
- `label`: already-translated label string (e.g., `t('entities.node')`)
- `sortKey`: the column name sent to the API
- `currentSort`: currently active sort column (from URL params)
- `currentOrder`: currently active sort direction (`asc` or `desc`)
- `navigate`: SPA router navigate function
- `basePath`: e.g., `'/nodes'`
- `params`: all current query params (to preserve filters)

**Behavior:**

| Current state | Next state | Indicator |
|--------------|-----------|-----------|
| Not sorted by this column | `sort=key&order=asc` | (none shown before click) |
| Sorted `asc` by this column | `sort=key&order=desc` | ▴ |
| Sorted `desc` by this column | (remove sort params) | ▾ |

**URL construction:**

```js
function buildSortUrl(basePath, params, nextSort, nextOrder) {
    const sp = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined && value !== '') {
            sp.set(key, value);
        }
    }
    if (nextSort && nextOrder) {
        sp.set('sort', nextSort);
        sp.set('order', nextOrder);
    } else {
        sp.delete('sort');
        sp.delete('order');
    }
    const qs = sp.toString();
    return qs ? `${basePath}?${qs}` : basePath;
}
```

The `params` object contains filter params only (no `page` — pagination is implicitly reset to page 1 on sort change). When the third click removes sort params, the function returns to the page default via the frontend default logic (see Feature 4).

**Rendering:**

```js
export function sortableTableHeader(label, { sortKey, currentSort, currentOrder, navigate, basePath, params }) {
    let indicator = '';
    let nextSort, nextOrder;

    if (currentSort !== sortKey) {
        nextSort = sortKey;
        nextOrder = 'asc';
    } else if (currentOrder === 'asc') {
        nextSort = sortKey;
        nextOrder = 'desc';
        indicator = ' ▴';
    } else {
        nextSort = null;
        nextOrder = null;
        indicator = ' ▾';
    }

    const url = buildSortUrl(basePath, params, nextSort, nextOrder);

    return html`<th>
        <a href=${url} class="link link-hover inline-flex items-center gap-1 no-underline"
           @click=${(e) => { e.preventDefault(); navigate(url); }}>
            ${label}<span class="text-xs opacity-50">${indicator}</span>
        </a>
    </th>`;
}
```

**Not sortable:** Columns without a sort key render as plain `<th>` elements (unchanged from current behavior).

### 2B. Nodes page — `src/meshcore_hub/web/static/js/spa/pages/nodes.js`

**Changes:**
1. Parse `sort` and `order` from `params.query`; apply frontend defaults if missing:

```js
const sort = query.sort || 'name';
const order = query.order || 'asc';
```

2. Pass `sort`/`order` to `apiGet('/api/v1/nodes', { ..., sort, order })`
3. Replace the static `<th>` elements in the table header with `sortableTableHeader()` calls:

```js
const headerParams = { search, adv_type, adopted_by, limit };
const sortable = (label, sortKey) => sortableTableHeader(label, {
    sortKey, currentSort: sort, currentOrder: order,
    navigate, basePath: '/nodes', params: headerParams,
});

// In table header:
<thead><tr>
    ${sortable(t('entities.node'), 'name')}
    ${sortable(t('common.public_key'), 'public_key')}
    ${sortable(t('common.last_seen'), 'last_seen')}
</tr></thead>
```

**Why set defaults in the frontend?** The server applies its own defaults when `sort`/`order` are omitted, but the frontend needs to know the effective sort state to render the correct indicator on the active column. By setting `sort='name'` and `order='asc'` when the URL has no sort params, the "Node" header shows the ▴ indicator on first load and the URL state is always explicit.

### 2C. Advertisements page — `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`

**Changes:**
1. Parse `sort` and `order` from `params.query`; apply frontend defaults if missing:

```js
const sort = query.sort || 'time';
const order = query.order || 'desc';
```

2. Pass `sort`/`order` to `apiGet('/api/v1/advertisements', { ..., sort, order })`
3. Make the "Node" header sortable by `node_name`, the "Public Key" header sortable by `public_key`, and the "Time" header sortable by `time`:

```js
const headerParams = { search, observed_by, adopted_by, limit };
const sortable = (label, sortKey) => sortableTableHeader(label, {
    sortKey, currentSort: sort, currentOrder: order,
    navigate, basePath: '/advertisements', params: headerParams,
});

// In table header:
<thead><tr>
    ${sortable(t('entities.node'), 'node_name')}
    ${sortable(t('common.public_key'), 'public_key')}
    ${sortable(t('common.time'), 'time')}
    <th>${t('common.observers')}</th>
</tr></thead>
```

Sorting the "Node" column uses the same COALESCE display name logic as the nodes endpoint (name tag → SourceNode.name → public_key fallback), so the sort order matches the displayed names.

### 2D. Messages page — `src/meshcore_hub/web/static/js/spa/pages/messages.js`

**Changes:**
1. Parse `sort` and `order` from `params.query`; apply frontend defaults if missing:

```js
const sort = query.sort || 'time';
const order = query.order || 'desc';
```

2. Pass `sort`/`order` to `apiGet('/api/v1/messages', { ..., sort, order })`
3. Make Type, Time, From, and Message headers sortable; Observers stays plain:

```js
const headerParams = { message_type, channel_idx, observed_by, limit };
const sortable = (label, sortKey) => sortableTableHeader(label, {
    sortKey, currentSort: sort, currentOrder: order,
    navigate, basePath: '/messages', params: headerParams,
});

// In table header:
<thead><tr>
    ${sortable(t('common.type'), 'type')}
    ${sortable(t('common.time'), 'time')}
    ${sortable(t('common.from'), 'from')}
    ${sortable(t('entities.message'), 'message')}
    <th>${t('common.observers')}</th>
</tr></thead>
```

---

## Feature 3: Sort State Persistence

### How it works (no code changes needed beyond what's above)

1. Clicking a column header calls `router.navigate(url)`, which pushes a new history entry and triggers a page re-render.
2. The page component reads `sort`/`order` from `params.query` and passes them to the API.
3. The auto-refresh timer calls `fetchAndRenderData()`, which reads the same `params.query` — so the sort params are included in each refresh tick.
4. The `pagination()` component already preserves all non-empty params (it skips `page` explicitly), so `sort`/`order` flow through pagination links automatically.

### Edge case: What happens to sort when filters change?

Filter form submits use `createFilterHandler`, which navigates to a URL with only the filter params (no sort/order). This means changing a filter **loses** the current sort state. This is acceptable UX:
- Changing a filter implies a new query intent; resetting sort is reasonable.
- Users can re-apply sort after filtering.

If this becomes a pain point later, the filter form could be updated to preserve `sort`/`order` params.

---

## Feature 4: Frontend Default Sort (Explicit State)

To ensure sort indicators are always correct on first load, each page sets explicit `sort`/`order` values when the URL has none:

| Page | Frontend default |
|------|-----------------|
| Nodes | `sort=name, order=asc` |
| Advertisements | `sort=time, order=desc` |
| Messages | `sort=time, order=desc` |

```js
// Nodes page
const sort = query.sort || 'name';
const order = query.order || 'asc';

// Advertisements / Messages pages
const sort = query.sort || 'time';
const order = query.order || 'desc';
```

These defaults are passed to both the API call and the `sortableTableHeader()` component. This ensures:
- The active column header shows the correct indicator (▴ or ▾) on first load.
- The URL state is always explicit — no ambiguous "implicit default" state.
- Clicking the default-sorted column's header cycles to the next state (desc), rather than being a no-op.

---

## i18n Changes

### `src/meshcore_hub/web/static/locales/en.json`

No new translation keys are strictly needed — the column headers already have translations (`entities.node`, `common.public_key`, etc.). Sort indicators use Unicode arrows (▴ / ▾), which are language-neutral.

**Optional:** Add `aria-sort` attribute values for screen readers. These would be English-only static strings embedded in the component (e.g., `"ascending"`, `"descending"`) since they are accessibility metadata, not user-visible labels. Not required for initial implementation.

---

## Test Plan

### API Tests (`tests/test_api/`)

**test_nodes.py** — Add test class `TestNodeSort`:

| Test | Description |
|------|-------------|
| `test_sort_by_name_default` | Default (no `sort` param) returns nodes alpha by display name |
| `test_sort_by_name_asc` | `sort=name&order=asc` |
| `test_sort_by_name_desc` | `sort=name&order=desc` — Z-to-A |
| `test_sort_by_public_key` | `sort=public_key` |
| `test_sort_by_last_seen` | `sort=last_seen&order=asc` |
| `test_sort_name_tag_priority` | Name tag value takes priority over `node.name` in sort order |
| `test_sort_invalid_ignored` | Invalid `sort` value falls back to default |
| `test_sort_nodes_with_null_name` | Nodes with `name=NULL` sort by public_key via COALESCE fallback |

**test_advertisements.py** — Add test class `TestAdvertisementSort`:

| Test | Description |
|------|-------------|
| `test_sort_by_time_default` | Default sorts by `received_at DESC` |
| `test_sort_by_time_asc` | `sort=time&order=asc` |
| `test_sort_by_node_name` | `sort=node_name&order=asc` — sorts by display name (COALESCE of name tag → SourceNode.name → public_key) |
| `test_sort_by_node_name_tag_priority` | Name tag value takes priority over SourceNode.name in sort order |
| `test_sort_by_public_key` | `sort=public_key&order=asc` |
| `test_sort_invalid_ignored` | Invalid `sort` value falls back to default |

**test_messages.py** — Add test class `TestMessageSort`:

| Test | Description |
|------|-------------|
| `test_sort_by_time_default` | Default sorts by `received_at DESC` |
| `test_sort_by_type` | `sort=type&order=asc` |
| `test_sort_by_from` | `sort=from&order=asc` (sorts by `pubkey_prefix`) |
| `test_sort_by_message` | `sort=message&order=asc` (sorts by `text`) |
| `test_sort_invalid_ignored` | Invalid `sort` value falls back to default |

### Frontend Tests (`tests/test_web/`)

No existing frontend JS test infrastructure. Visual verification:
1. Load Nodes page — verify default sort is alpha by name
2. Click "Last Seen" header — verify sort switches to newest-first, indicator shows ▾
3. Click "Last Seen" again — verify indicator switches to ▴ (oldest-first)
4. Click "Last Seen" a third time — verify sort returns to default (name alpha)
5. Enable auto-refresh — verify sort state persists across refresh ticks
6. Repeat steps 2-5 on Advertisements and Messages pages
7. Verify pagination preserves sort params in page links
8. Verify the "Observers" column header on ads/messages is not clickable

---

## Files Changed

| File | Change |
|------|--------|
| `src/meshcore_hub/api/routes/nodes.py` | Add `sort`/`order` params, name-sort via COALESCE subquery, change default sort |
| `src/meshcore_hub/api/routes/advertisements.py` | Add `sort`/`order` params (time, node_name, public_key) with COALESCE name-sort |
| `src/meshcore_hub/api/routes/messages.py` | Add `sort`/`order` params (time, type, from, message) |
| `src/meshcore_hub/web/static/js/spa/components.js` | Add `sortableTableHeader()` export |
| `src/meshcore_hub/web/static/js/spa/pages/nodes.js` | Parse sort/order, pass to API, replace `<th>` with sortable headers |
| `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` | Parse sort/order, pass to API, replace `<th>` with sortable headers |
| `src/meshcore_hub/web/static/js/spa/pages/messages.js` | Parse sort/order, pass to API, replace `<th>` with sortable headers |
| `tests/test_api/test_nodes.py` | Add `TestNodeSort` class |
| `tests/test_api/test_advertisements.py` | Add `TestAdvertisementSort` class |
| `tests/test_api/test_messages.py` | Add `TestMessageSort` class |

---

## Sequence

1. Add `sortableTableHeader()` to `components.js`
2. Add `sort`/`order` params to `nodes.py` with COALESCE name-sort (changing default)
3. Update `nodes.js` with sortable headers and sort/order param passing
4. Add `sort`/`order` params to `advertisements.py`
5. Update `advertisements.js` with sortable headers
6. Add `sort`/`order` params to `messages.py`
7. Update `messages.js` with sortable headers
8. Write API tests for all three endpoints
9. Run `pytest tests/test_api/` to verify
10. Visual verification of all three pages
