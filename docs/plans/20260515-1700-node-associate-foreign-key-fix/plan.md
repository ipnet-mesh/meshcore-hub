# Node Association Foreign Key Fix

**Date:** 2026-05-15
**Status:** Reviewed
**Severity:** High (500 errors on `/api/v1/user/profiles`, broken Nodes/Members pages)

## Problem

The node retention policy (`NODE_CLEANUP`) deletes `Node` rows, but orphaned rows remain in dependent tables (`user_profile_nodes`, `event_observers`, `node_tags`). When the API loads user profiles with their adopted nodes via `selectinload`, the `assoc.node` relationship resolves to `None` because the referenced node no longer exists. This causes an `AttributeError` crash:

```
AttributeError: 'NoneType' object has no attribute 'public_key'
  at api/routes/user_profiles.py:96 — public_key=assoc.node.public_key
```

The same issue exists for any code that accesses `.node` on `EventObserver` or `NodeTag` after their referenced node has been deleted.

## Root Cause

The `cleanup_inactive_nodes()` function in `collector/cleanup.py` deletes `Node` rows directly via `DELETE FROM nodes WHERE last_seen < cutoff`. Three dependent tables define `ForeignKey("nodes.id", ondelete="CASCADE")`:

- `user_profile_nodes` (`user_profile_node.py:39`)
- `event_observers` (`event_observer.py:57`)
- `node_tags` (`node_tag.py:32`)

However, **the cascade never executes** because:

1. The **async SQLAlchemy engine** (`create_async_engine` in `database.py:115`) does **not** have the `PRAGMA foreign_keys=ON` listener that the sync engine has (`database.py:41-47`).
2. SQLite does not enforce foreign keys or cascades by default. The `PRAGMA` must be enabled per-connection.
3. The collector's cleanup runs via the async engine, so SQLite silently ignores the `ondelete="CASCADE"` constraints, leaving orphaned rows pointing to deleted `nodes.id` values.

## Affected Code

| File | Lines | Issue |
|------|-------|-------|
| `common/database.py` | 115 | Async engine created without SQLite FK pragma listener |
| `api/routes/user_profiles.py` | 34-42, 93-101 | `assoc.node.public_key` crashes when `assoc.node is None` |
| `collector/cleanup.py` | 166-225 | Node cleanup doesn't cascade to dependent tables |
| `collector/cli.py` | 517-601 | CLI `cleanup` command only runs event data cleanup, not node cleanup |
| `collector/cli.py` | 537-545 | Docstring says "Node records are never deleted" — misleading once orphan cleanup is added |
| `collector/cli.py` | 717-724 | `truncate` cascade warning omits `user_profile_nodes` and `event_observers` |
| `tests/test_collector/conftest.py` | 35 | Async test fixture has no FK pragma — can't verify cascade |
| `tests/test_api/conftest.py` | 49 | Sync test engine has no FK pragma — can't verify cascade |
| `tests/test_collector/test_cleanup.py` | — | Missing test for `cleanup_inactive_nodes` entirely |

## Plan

### Step 1: Fix async SQLite FK enforcement

**File:** `src/meshcore_hub/common/database.py`

Add the `PRAGMA foreign_keys=ON` event listener to `self.async_engine` (the `create_async_engine` call), mirroring the existing listener on the sync engine. Use the existing module-scope `event` import — do NOT re-import it.

```python
# After creating self.async_engine (at database.py:115):
if database_url.startswith("sqlite"):
    @event.listens_for(self.async_engine.sync_engine, "connect")
    def set_sqlite_pragma_async(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

This fixes the root cause for all future cleanup operations across all three dependent tables.

### Step 2: Add null-safety to API routes

**File:** `src/meshcore_hub/api/routes/user_profiles.py`

Make `_build_adopted_nodes()` resilient to orphaned associations:

1. In `_build_adopted_nodes()` (line 34): Skip associations where `assoc.node is None`, log a warning with `profile.id` and `assoc.node_id` for diagnostics.
2. Remove the duplicate inline adoption loop in `list_profiles()` (lines 93-101); refactor it to call `_build_adopted_nodes()` instead.

This prevents the 500 error even if orphaned rows exist in the database (e.g., from past cleanup runs before this fix). All three callers (`get_my_profile`, `get_profile`, `list_profiles`) are protected.

### Step 3: Add orphan cleanup function

**File:** `src/meshcore_hub/collector/cleanup.py`

Add a new function `cleanup_orphaned_node_relations(db, dry_run=False) -> dict` that:

1. Finds orphaned rows in all three dependent tables (`user_profile_nodes`, `event_observers`, `node_tags`) where `node_id` does not exist in the `nodes` table (using `LEFT JOIN ... WHERE nodes.id IS NULL` pattern).
2. Deletes those orphaned rows (or counts them in dry-run mode).
3. Returns a dict with per-table counts, e.g. `{"user_profile_nodes": 3, "event_observers": 0, "node_tags": 5}`.

This repairs existing production databases that already have broken data from past cleanup runs.

### Step 4: Integrate orphan cleanup into retention cycle

**File:** `src/meshcore_hub/collector/subscriber.py`

In the `run_cleanup()` async function within `_start_cleanup_scheduler()` (around line 303):

1. Remove the inline `async def run_cleanup()` and extract it as a proper method `_run_scheduled_cleanup(db_session)` on the subscriber class.
2. After `cleanup_inactive_nodes()`, call `cleanup_orphaned_node_relations()`.
3. Log the orphan cleanup results.

This ensures orphans are cleaned up automatically in future runs as a belt-and-suspenders defense even after the PRAGMA fix.

### Step 5: Wire cleanup into CLI

**File:** `src/meshcore_hub/collector/cli.py`

1. Add a `--node-cleanup` option (default: `false`) to the `cleanup` CLI command. When set, also runs `cleanup_inactive_nodes()` and `cleanup_orphaned_node_relations()`.
2. Update the docstring to remove "Node records are never deleted" and document the new option.
3. Add a `--node-cleanup-days` option (default: `30`) for the node inactivity threshold.
4. Display orphan cleanup results in the output.

### Step 6: Fix test fixtures with FK PRAGMA

**File:** `tests/test_collector/conftest.py`

Add `PRAGMA foreign_keys=ON` event listener to the async engine created at line 35.

**File:** `tests/test_api/conftest.py`

Add `PRAGMA foreign_keys=ON` event listener to the sync engine created at line 49.

### Step 7: Fix `truncate` CLI cascade warning

**File:** `src/meshcore_hub/collector/cli.py` (lines 717-724)

Add `user_profile_nodes` and `event_observers` to the cascade warning list.

### Step 8: Tests

- **`tests/test_collector/test_cleanup.py`**:
  - Add test for `cleanup_inactive_nodes()` — create a node with associations in all three dependent tables, delete the node, verify cascade removes all dependent rows.
  - Add test for `cleanup_orphaned_node_relations()` — create orphaned rows in all three tables (rows referencing non-existent node_ids), verify the function deletes them.

- **`tests/test_api/test_user_profiles.py`**:
  - Add test verifying `list_profiles` returns 200 (not 500) when orphaned `UserProfileNode` rows exist with a deleted node, and that the orphaned association is excluded from `adopted_nodes` output.

### Step 9: Documentation

- **`docs/upgrading.md`**: Add a note about this fix, the automatic orphan cleanup, and a manual repair command for existing deployments.
- **`AGENTS.md`**: No changes needed (no new env vars or config).
- **`SCHEMAS.md`**: No changes needed (FK relationships unchanged).

## Execution Order

1. Fix async FK pragma (Step 1) — prevents future orphans
2. Fix test fixtures with FK pragma (Step 6) — unblocks testability
3. Add null-safety (Step 2) — stops the 500 errors immediately
4. Add orphan cleanup function (Step 3) — provides the repair tool
5. Integrate into retention cycle (Step 4) — makes it automatic
6. Wire into CLI (Step 5) — exposes manual control
7. Fix truncate warning (Step 7)
8. Add tests (Step 8)
9. Update docs (Step 9)

## Risk Assessment

- **Step 1 (PRAGMA fix):** Low risk. Enables a constraint that was always intended to be active. All `ondelete` clauses use either `CASCADE` or `SET NULL`, which are safe operations.
- **Step 2 (Null-safety):** Zero risk. Purely defensive — only affects display, changes no data.
- **Step 3-4 (Orphan cleanup):** Low risk. Deletes rows that reference non-existent nodes, which are broken data by definition.
- **Step 5 (CLI):** Low risk. The `--node-cleanup` flag defaults to `false` (opt-in), preserving backward compatibility.
- **Step 6 (Test fix):** Zero risk. Only affects test infrastructure.

## Verification

After deploying:

1. Check the API returns 200 for `/api/v1/user/profiles`:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/user/profiles
   ```
2. Run manual cleanup to repair existing orphans:
   ```bash
   meshcore-hub collector cleanup --dry-run --node-cleanup
   meshcore-hub collector cleanup --node-cleanup
   ```
3. Confirm no orphaned rows remain across all three tables:
   ```sql
   SELECT 'user_profile_nodes' AS tbl, COUNT(*) FROM user_profile_nodes upn
   LEFT JOIN nodes n ON n.id = upn.node_id WHERE n.id IS NULL
   UNION ALL
   SELECT 'event_observers', COUNT(*) FROM event_observers eo
   LEFT JOIN nodes n ON n.id = eo.observer_node_id WHERE n.id IS NULL
   UNION ALL
   SELECT 'node_tags', COUNT(*) FROM node_tags nt
   LEFT JOIN nodes n ON n.id = nt.node_id WHERE n.id IS NULL;
   ```
   Expected: 0 for all three.

## Resolved Review Issues

| Issue | Resolution |
|-------|-----------|
| Orphan cleanup scope (UserProfileNode only vs. all 3 tables) | Cover all 3 tables: `user_profile_nodes`, `event_observers`, `node_tags` |
| Test fixtures lack FK pragma | Add `PRAGMA foreign_keys=ON` to both collector and API test fixtures |
| CLI `cleanup` doesn't run node cleanup | Add `--node-cleanup` option (default off, opt-in) |
| Step 1 code uses shadow-import `from sqlalchemy import event as ...` | Reuse existing module-scope `event` import |
| Missing test for `cleanup_inactive_nodes` | Add test with cascade verification |
