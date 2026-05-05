# Plan: Default Nodes Sort by Time + Mobile Sort Controls

**Date:** 2026-05-05
**Branch:** `feat/mobile-sort-time-default`

---

## Background

Two issues with the current sorting UX:

1. **Nodes default sort is alphabetical by name** (`sort=name, order=asc`). For a mesh network dashboard, sorting by most recently seen is more useful — operators want to see active nodes first.

2. **Mobile view has no sort controls.** The desktop table view has clickable column headers, but the mobile card view (`lg:hidden`) renders a separate card layout with no sort mechanism. Mobile users cannot change the sort order at all.

---

## Feature 1: Change Default Nodes Sort to Last Seen (Descending)

### 1A. API — `src/meshcore_hub/api/routes/nodes.py`

Change lines 205–206:

```python
# Before
sort = sort if sort in VALID_NODE_SORT_COLUMNS else "name"
order = order if order in ("asc", "desc") else ("asc" if sort == "name" else "desc")

# After
sort = sort if sort in VALID_NODE_SORT_COLUMNS else "last_seen"
order = order if order in ("asc", "desc") else "desc"
```

The default when no `sort`/`order` params are provided is now `last_seen DESC` (newest first).

### 1B. Frontend — `src/meshcore_hub/web/static/js/spa/pages/nodes.js`

Change lines 19–20:

```javascript
// Before
const sort = query.sort || 'name';
const order = query.order || 'asc';

// After
const sort = query.sort || 'last_seen';
const order = query.order || 'desc';
```

This ensures the "Last Seen" column header shows the correct ▾ indicator on first load.

### 1C. Tests

Update existing sort tests in `tests/test_api/test_nodes.py` that assume `name` default:

- **`test_sort_by_name_default`** (line 472): Change name/docstring to `test_sort_by_last_seen_default`. Both nodes currently get identical `last_seen=datetime.now(timezone.utc)` timestamps — they must be given **staggered** timestamps (e.g., 1 hour apart) so the `last_seen DESC` default produces a deterministic order. Assert newest-first (`node_b` first if it has the later timestamp).

- **`test_sort_invalid_ignored`** (line 643): Update docstring from "falls back to default (name alpha)" to "**falls back to default (last_seen desc)**". Both nodes currently have `last_seen=NULL` (only `first_seen` is set), so the sort order would be non-deterministic. Give the nodes staggered `last_seen` timestamps and assert the newest-first ordering.

---

## Feature 2: Mobile Sort Select Dropdown

### Design

A compact native `<select>` dropdown shown only on mobile (below `lg` breakpoint), positioned between the stats row and the card list. Combines sort column and direction into a single control for minimal UI footprint.

```
 ┌──────────────────────────────┐
 │ Nodes              🕐 30s    │  ← page title + auto-refresh
 │ 42 total                     │  ← stats badges
 │                              │
 │ Sort: [Last Seen (newest) ▾] │  ← NEW: mobile sort select
 │                              │
 │ ┌────────────────────────┐   │
 │ │ Node ABC    2 min ago  │   │  ← mobile cards
 │ └────────────────────────┘   │
 │ ┌────────────────────────┐   │
 │ │ Node XYZ    5 min ago  │   │
 │ └────────────────────────┘   │
 └──────────────────────────────┘
```

### Why native `<select>`

| Factor | Native `<select>` | Pill chips | Dropdown menu |
|--------|-------------------|------------|---------------|
| Touch optimization | Native iOS/Android picker | Custom tap targets | Custom tap targets |
| UI footprint | 1 line | 1–2 lines | 1 line + overlay |
| Discoverability | All options visible in picker | Only visible pills | Hidden until opened |
| Consistency | Matches filter `<select>` already used | New pattern | New pattern |
| Accessibility | Built-in | Needs ARIA | Needs ARIA |

### 2A. Shared component — `src/meshcore_hub/web/static/js/spa/components.js`

Add a `mobileSortSelect()` function. It calls `buildSortUrl()` (line 18), which is a **module-scoped (non-exported) function** in the same file — accessible via closure scope, no export needed.

```javascript
export function mobileSortSelect({ currentSort, currentOrder, navigate, basePath, params, options }) {
    const currentValue = `${currentSort}:${currentOrder}`;

    const sortOptions = options.map(opt =>
        html`<option value=${opt.value} ?selected=${opt.value === currentValue}>${opt.label}</option>`
    );

    const onChange = (e) => {
        const [sort, order] = e.target.value.split(':');
        const url = buildSortUrl(basePath, params, sort, order);
        navigate(url);
    };

    return html`<div class="lg:hidden mb-3">
        <div class="flex items-center gap-2">
            <span class="text-xs opacity-60">${t('common.sort_by')}</span>
            <select class="select select-sm select-bordered flex-1"
                    @change=${onChange}>
                ${sortOptions}
            </select>
        </div>
    </div>`;
}
```

**Parameters:**
- `currentSort` / `currentOrder`: current sort state from URL
- `navigate`: SPA router navigate function
- `basePath`: e.g., `'/nodes'`
- `params`: filter params to preserve
- `options`: array of `{ value: 'sort:order', label: 'Display Name' }` objects

### 2B. Nodes page — `src/meshcore_hub/web/static/js/spa/pages/nodes.js`

Add the mobile sort select between the stats row and the card list:

```javascript
import { mobileSortSelect } from '../components.js';

// Define sort options
const sortOptions = [
    { value: 'last_seen:desc', label: t('nodes.sort.last_seen_newest') },
    { value: 'last_seen:asc', label: t('nodes.sort.last_seen_oldest') },
    { value: 'name:asc', label: t('nodes.sort.name_az') },
    { value: 'name:desc', label: t('nodes.sort.name_za') },
    { value: 'public_key:asc', label: t('nodes.sort.key_asc') },
    { value: 'public_key:desc', label: t('nodes.sort.key_desc') },
];

// In the render, between stats badges and mobile cards:
${mobileSortSelect({
    currentSort: sort, currentOrder: order,
    navigate, basePath: '/nodes',
    params: headerParams, options: sortOptions,
})}
```

### 2C. Advertisements page — `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`

Same pattern, with ad-specific sort options:

```javascript
const sortOptions = [
    { value: 'time:desc', label: t('advertisements.sort.newest') },
    { value: 'time:asc', label: t('advertisements.sort.oldest') },
    { value: 'node_name:asc', label: t('advertisements.sort.node_az') },
    { value: 'node_name:desc', label: t('advertisements.sort.node_za') },
    { value: 'public_key:asc', label: t('advertisements.sort.key_asc') },
    { value: 'public_key:desc', label: t('advertisements.sort.key_desc') },
];
```

### 2D. Messages page — `src/meshcore_hub/web/static/js/spa/pages/messages.js`

Same pattern, with message-specific sort options:

```javascript
const sortOptions = [
    { value: 'time:desc', label: t('messages.sort.newest') },
    { value: 'time:asc', label: t('messages.sort.oldest') },
    { value: 'type:asc', label: t('messages.sort.type_az') },
    { value: 'type:desc', label: t('messages.sort.type_za') },
    { value: 'from:asc', label: t('messages.sort.from_az') },
    { value: 'from:desc', label: t('messages.sort.from_za') },
    { value: 'message:asc', label: t('messages.sort.message_az') },
    { value: 'message:desc', label: t('messages.sort.message_za') },
];
```

---

## i18n Changes

### `src/meshcore_hub/web/static/locales/en.json`

Add new keys:

```json
{
  "common": {
    "sort_by": "Sort by"
  },
  "nodes": {
    "sort": {
      "last_seen_newest": "Last Seen (newest)",
      "last_seen_oldest": "Last Seen (oldest)",
      "name_az": "Name (A\u2013Z)",
      "name_za": "Name (Z\u2013A)",
      "key_asc": "Public Key (ascending)",
      "key_desc": "Public Key (descending)"
    }
  },
  "advertisements": {
    "sort": {
      "newest": "Time (newest)",
      "oldest": "Time (oldest)",
      "node_az": "Node (A\u2013Z)",
      "node_za": "Node (Z\u2013A)",
      "key_asc": "Public Key (ascending)",
      "key_desc": "Public Key (descending)"
    }
  },
  "messages": {
    "sort": {
      "newest": "Time (newest)",
      "oldest": "Time (oldest)",
      "type_az": "Type (A\u2013Z)",
      "type_za": "Type (Z\u2013A)",
      "from_az": "From (A\u2013Z)",
      "from_za": "From (Z\u2013A)",
      "message_az": "Message (A\u2013Z)",
      "message_za": "Message (Z\u2013A)"
    }
  }
}
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/meshcore_hub/api/routes/nodes.py` | Change default sort from `name ASC` to `last_seen DESC` |
| `src/meshcore_hub/web/static/js/spa/pages/nodes.js` | Change frontend default sort; add mobile sort select |
| `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` | Add mobile sort select |
| `src/meshcore_hub/web/static/js/spa/pages/messages.js` | Add mobile sort select |
| `src/meshcore_hub/web/static/js/spa/components.js` | Add `mobileSortSelect()` export |
| `src/meshcore_hub/web/static/locales/en.json` | Add sort option translation keys |
| `docs/i18n.md` | Document new translation keys |
| `tests/test_api/test_nodes.py` | Update default sort test expectations |

---

## Sequence

1. Change default sort in API (`nodes.py`)
2. Change frontend default in `nodes.js`
3. Add `mobileSortSelect()` to `components.js`
4. Add mobile sort select to `nodes.js`
5. Add mobile sort select to `advertisements.js`
6. Add mobile sort select to `messages.js`
7. Add i18n keys to `en.json` and update `docs/i18n.md`
8. Update API tests
9. Run `pytest tests/test_api/`
10. Run `pre-commit run --all-files`
