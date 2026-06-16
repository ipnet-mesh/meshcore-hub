# Tasks: Sort Nodes with NULLS LAST for `last_seen`

> Generated from `plan.md` on 2026-06-16

## Fix: Explicit NULLS LAST ordering

- [x] Add `nullslast` to the SQLAlchemy import in `nodes.py`
  - [x] Update `src/meshcore_hub/api/routes/nodes.py:6` from `from sqlalchemy import func, or_, select` to `from sqlalchemy import func, nullslast, or_, select`
- [x] Wrap the `last_seen` ORDER BY clause with `nullslast()`
  - [x] Replace the `elif sort == "last_seen":` block at `nodes.py:181-184` so it computes `order_col` (`Node.last_seen.desc()` / `.asc()`) then applies `query.order_by(nullslast(order_col))`
  - [x] Leave the `name` and `public_key` branches untouched
  - [x] Leave the dead `else` branch (lines 185-187) untouched — out of scope

## Regression tests

- [x] Add `test_sort_last_seen_nulls_last_desc` to `TestNodeSort` in `tests/test_api/test_nodes.py`
  - [x] Seed at least one node with `last_seen=None` (set only `first_seen`, following the `test_nodes.py:534-545` pattern) and one or more nodes with concrete `last_seen` values
  - [x] Request the default sort (no params) and assert the NULL-`last_seen` node is the final `items[]` entry
- [x] Add `test_sort_last_seen_nulls_last_asc` to `TestNodeSort`
  - [x] Seed a mix of NULL and non-null `last_seen` nodes
  - [x] Request `sort=last_seen&order=asc` and assert the NULL-`last_seen` node is still the final `items[]` entry (always-last policy)
- [x] Add `test_sort_last_seen_all_null` to `TestNodeSort`
  - [x] Seed multiple nodes all with `last_seen=None`
  - [x] Assert all nodes are returned, no error, order is stable across both DESC and ASC

## Verification

- [x] Run targeted node tests: `pytest --no-cov tests/test_api/test_nodes.py`
- [x] Run full node test suite with coverage to confirm no regressions: `pytest --no-cov`
- [x] Run pre-commit on all files: `pre-commit run --all-files`
- [x] Run the Postgres test-matrix leg if a Postgres test DB is available (`DATABASE_BACKEND=postgres ... pytest --no-cov tests/test_api/test_nodes.py`) — the true regression catch lives here
- [x] Manual check: load `/nodes` on a Postgres-backed deployment with NULL-`last_seen` nodes; confirm they appear at the bottom under default sort and when toggling Last Seen to ascending
