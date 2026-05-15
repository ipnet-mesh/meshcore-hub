# Tasks — Node Association Foreign Key Fix

Reference: [plan.md](./plan.md)

## Phase 1: Root Cause Fix + Defensive Hardening

- [ ] **T1.1** — Add `PRAGMA foreign_keys=ON` event listener to `self.async_engine.sync_engine` in `src/meshcore_hub/common/database.py` (after line 115). Reuse existing module-scope `event` import. Guard with `if database_url.startswith("sqlite"):`.
- [ ] **T1.2** — Add `PRAGMA foreign_keys=ON` event listener to async engine in `tests/test_collector/conftest.py:35`.
- [ ] **T1.3** — Add `PRAGMA foreign_keys=ON` event listener to sync engine in `tests/test_api/conftest.py:49`.
- [ ] **T1.4** — In `src/meshcore_hub/api/routes/user_profiles.py`, add null-guard in `_build_adopted_nodes()` (line 34): skip associations where `assoc.node is None`, log a warning with `assoc.node_id`.
- [ ] **T1.5** — In `src/meshcore_hub/api/routes/user_profiles.py`, refactor the duplicate inline adoption loop in `list_profiles()` (lines 92–101) to call `_build_adopted_nodes()` instead.

## Phase 2: Orphan Cleanup Function

- [ ] **T2.1** — Add `cleanup_orphaned_node_relations(db: AsyncSession, dry_run: bool = False) -> dict[str, int]` to `src/meshcore_hub/collector/cleanup.py`. Must cover all three tables (`user_profile_nodes.node_id`, `event_observers.observer_node_id`, `node_tags.node_id`) using `LEFT JOIN nodes ... WHERE nodes.id IS NULL` pattern. Return per-table counts.

## Phase 3: Integration

- [ ] **T3.1** — In `src/meshcore_hub/collector/subscriber.py`, add `cleanup_orphaned_node_relations()` call inside the `run_cleanup()` inline function (after `cleanup_inactive_nodes()` at line ~323). Gate it behind the same `if self._node_cleanup_enabled:` block. Log the orphan results.
- [ ] **T3.2** — In `src/meshcore_hub/collector/cli.py`, add `--node-cleanup` flag (default `false`) and `--node-cleanup-days` option (default `30`) to the `cleanup` CLI command. When `--node-cleanup` is set, run `cleanup_inactive_nodes()` and `cleanup_orphaned_node_relations()`. Display results.
- [ ] **T3.3** — Update the `cleanup` command docstring (`cli.py:537–545`): remove "Node records are never deleted", document `--node-cleanup` and `--node-cleanup-days`.
- [ ] **T3.4** — In `src/meshcore_hub/collector/cli.py`, add `user_profile_nodes` and `event_observers` to the truncate cascade warning (lines 717–724).

## Phase 4: Tests

- [ ] **T4.1** — Add test for `cleanup_inactive_nodes()` in `tests/test_collector/test_cleanup.py`: create a node with rows in all three dependent tables (`user_profile_nodes`, `event_observers`, `node_tags`), run cleanup, assert cascade deleted all dependent rows.
- [ ] **T4.2** — Add test for `cleanup_orphaned_node_relations()` in `tests/test_collector/test_cleanup.py`: create orphaned rows in all three tables referencing non-existent `node_id`s, run function, assert all orphans deleted and per-table counts correct.
- [ ] **T4.3** — Add test in `tests/test_api/test_user_profiles.py`: create a profile with an adopted node, delete the node (leaving an orphaned `UserProfileNode`), call `GET /profiles`, assert 200 response and orphaned node excluded from `adopted_nodes`.

## Phase 5: Documentation

- [ ] **T5.1** — Add upgrade note to `docs/upgrading.md`: describe the async FK pragma fix, automatic orphan cleanup in the retention cycle, and the manual repair command (`meshcore-hub collector cleanup --node-cleanup`).

## Verification

After all tasks complete:

```bash
# Lint and typecheck
source .venv/bin/activate
pre-commit run --all-files

# Targeted tests
pytest tests/test_collector/test_cleanup.py -v
pytest tests/test_api/test_user_profiles.py -v
pytest tests/test_common/ -v

# Full suite (only if changes span components)
pytest
```
