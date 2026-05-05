# Tasks: Column Sort Controls on List Pages + Alpha Sort Default for Nodes

**Plan:** [plan.md](plan.md)
**Branch:** `feat/list-sort-controls`

---

## Phase 1: Shared Frontend Component

- [ ] **1.1** Add `buildSortUrl()` helper in `src/meshcore_hub/web/static/js/spa/components.js`
  - Accepts `(basePath, params, nextSort, nextOrder)` and returns a URL string
  - Uses `URLSearchParams` to build query string from `params`, adds/removes `sort`/`order`

- [ ] **1.2** Add `sortableTableHeader()` export in `src/meshcore_hub/web/static/js/spa/components.js`
  - Accepts `(label, { sortKey, currentSort, currentOrder, navigate, basePath, params })`
  - Renders `<th><a>` with cycling sort indicator (▴ / ▾) using `buildSortUrl()`
  - Cycle: none → asc → desc → none (removes sort/order on third click)

## Phase 2: Nodes — Backend + Frontend

- [ ] **2.1** Add `sort`/`order` query params to `src/meshcore_hub/api/routes/nodes.py`
  - Add `sort: Optional[str] = Query(default=None)` param
  - Add `order: Optional[str] = Query(default=None)` param
  - Define `VALID_SORT_COLUMNS` dict: `name`, `public_key`, `last_seen`
  - Build correlated subquery: `COALESCE(name_tag_subq, Node.name, Node.public_key)` for `name` sort
  - Change default sort from `last_seen DESC` to alpha-by-name ascending (when no params provided)
  - Invalid `sort`/`order` falls back to defaults

- [ ] **2.2** Update `src/meshcore_hub/web/static/js/spa/pages/nodes.js`
  - Parse `sort` and `order` from `query`, applying frontend defaults: `sort = query.sort || 'name'`, `order = query.order || 'asc'`
  - Pass `sort`/`order` to `apiGet('/api/v1/nodes', { ..., sort, order })`
  - Build `headerParams` from current filter params (search, adv_type, adopted_by, limit)
  - Replace static `<th>` elements with `sortableTableHeader()` calls for Node, Public Key, Last Seen columns

## Phase 3: Advertisements — Backend + Frontend

- [ ] **3.1** Add `sort`/`order` query params to `src/meshcore_hub/api/routes/advertisements.py`
  - Add `sort: Optional[str] = Query(default=None)` param
  - Add `order: Optional[str] = Query(default=None)` param
  - Define `VALID_SORT_COLUMNS` dict: `time`, `node_name`, `public_key`
  - Import `aliased` from `sqlalchemy.orm` (`NodeTag` already imported)
  - Build correlated subquery via `aliased(NodeTag)` for `node_name` sort: `COALESCE(name_tag_subq, SourceNode.name, Advertisement.public_key)`
  - Invalid `sort`/`order` falls back to `received_at DESC`

- [ ] **3.2** Update `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`
  - Parse `sort` and `order` from `query`, applying frontend defaults: `sort = query.sort || 'time'`, `order = query.order || 'desc'`
  - Pass `sort`/`order` to `apiGet('/api/v1/advertisements', { ..., sort, order })`
  - Build `headerParams` from current filter params (search, observed_by, adopted_by, limit)
  - Replace static `<th>` elements with `sortableTableHeader()` calls for Node (`node_name`), Public Key, Time columns
  - Keep Observers column as plain `<th>`

## Phase 4: Messages — Backend + Frontend

- [ ] **4.1** Add `sort`/`order` query params to `src/meshcore_hub/api/routes/messages.py`
  - Add `sort: Optional[str] = Query(default=None)` param
  - Add `order: Optional[str] = Query(default=None)` param
  - Define `VALID_SORT_COLUMNS` dict: `time`, `type`, `from`, `message`
  - Invalid `sort`/`order` falls back to `received_at DESC`

- [ ] **4.2** Update `src/meshcore_hub/web/static/js/spa/pages/messages.js`
  - Parse `sort` and `order` from `query`, applying frontend defaults: `sort = query.sort || 'time'`, `order = query.order || 'desc'`
  - Pass `sort`/`order` to `apiGet('/api/v1/messages', { ..., sort, order })`
  - Build `headerParams` from current filter params (message_type, channel_idx, observed_by, limit)
  - Replace static `<th>` elements with `sortableTableHeader()` calls for Type, Time, From, Message columns
  - Keep Observers column as plain `<th>`

## Phase 5: API Tests

- [ ] **5.1** Add `TestNodeSort` class to `tests/test_api/test_nodes.py`
  - `test_sort_by_name_default` — no sort param returns alpha by display name
  - `test_sort_by_name_asc` — `sort=name&order=asc`
  - `test_sort_by_name_desc` — `sort=name&order=desc`
  - `test_sort_by_public_key` — `sort=public_key`
  - `test_sort_by_last_seen` — `sort=last_seen&order=asc`
  - `test_sort_name_tag_priority` — name tag takes priority over `node.name`
  - `test_sort_invalid_ignored` — invalid sort falls back to default
  - `test_sort_nodes_with_null_name` — `name=NULL` sorts by public_key

- [ ] **5.2** Add `TestAdvertisementSort` class to `tests/test_api/test_advertisements.py`
  - `test_sort_by_time_default` — default sorts by `received_at DESC`
  - `test_sort_by_time_asc` — `sort=time&order=asc`
  - `test_sort_by_node_name` — `sort=node_name&order=asc` sorts by display name
  - `test_sort_by_node_name_tag_priority` — name tag takes priority over SourceNode.name
  - `test_sort_by_public_key` — `sort=public_key&order=asc`
  - `test_sort_invalid_ignored` — invalid sort falls back to default

- [ ] **5.3** Add `TestMessageSort` class to `tests/test_api/test_messages.py`
  - `test_sort_by_time_default` — default sorts by `received_at DESC`
  - `test_sort_by_type` — `sort=type&order=asc`
  - `test_sort_by_from` — `sort=from&order=asc`
  - `test_sort_by_message` — `sort=message&order=asc`
  - `test_sort_invalid_ignored` — invalid sort falls back to default

## Verification

- [ ] Run `pytest tests/test_api/test_nodes.py -v`
- [ ] Run `pytest tests/test_api/test_advertisements.py -v`
- [ ] Run `pytest tests/test_api/test_messages.py -v`
- [ ] Visual verification in browser:
  - Nodes: default sort is alpha by name; Node header shows ▴ indicator on first load
  - Click "Last Seen" → newest-first with ▾ indicator; click again → oldest-first ▴; click again → reset to default
  - Advertisements: default sort is newest-first; sort by Node name; sort by Public Key
  - Messages: default sort is newest-first; sort by Type, From, Message
  - Observers column header on ads/messages is not clickable
  - Auto-refresh preserves sort state across ticks
  - Pagination preserves sort params in page links
  - Filter change resets sort to default
- [ ] Run `pre-commit run --all-files`
