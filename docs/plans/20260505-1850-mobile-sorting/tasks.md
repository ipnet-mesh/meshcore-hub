# Tasks: Default Nodes Sort by Time + Mobile Sort Controls

**Plan:** [plan.md](plan.md)
**Branch:** `feat/mobile-sort-time-default`

---

## Phase 1: Change Default Nodes Sort to Last Seen (Descending)

- [ ] **1.1** Update API default sort in `src/meshcore_hub/api/routes/nodes.py` (lines 205–206)
  - Change `else "name"` → `else "last_seen"`
  - Change `else ("asc" if sort == "name" else "desc")` → `else "desc"`

- [ ] **1.2** Update frontend default sort in `src/meshcore_hub/web/static/js/spa/pages/nodes.js` (lines 19–20)
  - Change `query.sort || 'name'` → `query.sort || 'last_seen'`
  - Change `query.order || 'asc'` → `query.order || 'desc'`

- [ ] **1.3** Update existing tests in `tests/test_api/test_nodes.py`
  - **`test_sort_by_name_default`** (line 472): Rename to `test_sort_by_last_seen_default`
  - Give the two test nodes **staggered** `last_seen` timestamps (e.g., 1 hour apart) instead of identical `datetime.now(timezone.utc)`
  - Assert newest-first order (`node_b` first if it has the later timestamp)
  - **`test_sort_invalid_ignored`** (line 643): Update docstring to "falls back to default (last_seen desc)"
  - Give the two test nodes staggered `last_seen` timestamps and assert newest-first ordering

## Phase 2: Shared Mobile Sort Component

- [ ] **2.1** Add `mobileSortSelect()` export in `src/meshcore_hub/web/static/js/spa/components.js`
  - Parameters: `{ currentSort, currentOrder, navigate, basePath, params, options }`
  - Renders `lg:hidden` wrapper with label + native `<select>`
  - Calls `buildSortUrl()` (module-scoped, line 18) via closure on change
  - Splits `option.value` on `:` to extract sort/order, navigates via SPA router
  - Mark currently-selected option with `?selected`

## Phase 3: Mobile Sort Select on Each List Page

- [ ] **3.1** Add mobile sort select to `src/meshcore_hub/web/static/js/spa/pages/nodes.js`
  - Import `mobileSortSelect` from `../components.js`
  - Define sort options: `last_seen:desc`, `last_seen:asc`, `name:asc`, `name:desc`, `public_key:asc`, `public_key:desc`
  - Insert `${mobileSortSelect(...)}` between stats badges and mobile card list
  - Pass `headerParams` to preserve filter state

- [ ] **3.2** Add mobile sort select to `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`
  - Import `mobileSortSelect` from `../components.js`
  - Define sort options: `time:desc`, `time:asc`, `node_name:asc`, `node_name:desc`, `public_key:asc`, `public_key:desc`
  - Insert between stats badges and mobile card list

- [ ] **3.3** Add mobile sort select to `src/meshcore_hub/web/static/js/spa/pages/messages.js`
  - Import `mobileSortSelect` from `../components.js`
  - Define sort options: `time:desc`, `time:asc`, `type:asc`, `type:desc`, `from:asc`, `from:desc`, `message:asc`, `message:desc`
  - Insert between stats badges and mobile card list

## Phase 4: i18n

- [ ] **4.1** Add sort translation keys to `src/meshcore_hub/web/static/locales/en.json`
  - Add `common.sort_by`: "Sort by"
  - Add `nodes.sort.*` (6 keys): `last_seen_newest`, `last_seen_oldest`, `name_az`, `name_za`, `key_asc`, `key_desc`
  - Add `advertisements.sort.*` (6 keys): `newest`, `oldest`, `node_az`, `node_za`, `key_asc`, `key_desc`
  - Add `messages.sort.*` (8 keys): `newest`, `oldest`, `type_az`, `type_za`, `from_az`, `from_za`, `message_az`, `message_za`

- [ ] **4.2** Document new keys in `docs/i18n.md`

## Verification

- [ ] Run `pytest tests/test_api/test_nodes.py -v`
- [ ] Run `pytest tests/test_common/test_i18n.py -v`
- [ ] Run `pre-commit run --all-files`
- [ ] Visual verification in browser:
  - Nodes: default sort shows newest-first; Last Seen column header shows ▾ on first load
  - Nodes mobile: sort select visible below `lg` breakpoint; changing it updates the card order
  - Advertisements mobile: sort select with time/node/key options
  - Messages mobile: sort select with time/type/from/message options
  - Desktop view: no sort select visible (hidden at `lg:` breakpoint)
  - Auto-refresh preserves sort state across ticks
  - Filter change preserves sort state
