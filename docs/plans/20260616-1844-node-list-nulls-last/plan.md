# Plan: Sort Nodes with NULLS LAST for `last_seen`

## Summary

After migrating from SQLite to Postgres, the Node list regressed: nodes that
have **no `last_seen` timestamp** (never observed activity) now appear at the
**top** of the default view, whereas on SQLite they sat at the **bottom**. This
is a direct consequence of divergent NULL-ordering semantics between the two
databases on the default `ORDER BY last_seen DESC` sort, not an application
logic bug.

The fix is to make NULL ordering **explicit** by appending `NULLS LAST` to the
`last_seen` ORDER BY clause, so nodes without a last-seen date always sink to
the end of the list regardless of the active database backend or sort
direction. SQLAlchemy 2.0's `.nullslast()` emits the standard SQL clause,
supported natively by Postgres and by SQLite ≥ 3.30 (shipped with all supported
Python versions).

## Background & Motivation

### Root cause

The default Node list sort is `last_seen DESC`, set in
`src/meshcore_hub/api/routes/nodes.py:164-165` and applied at `nodes.py:181-184`:

```python
sort = sort if sort in VALID_NODE_SORT_COLUMNS else "last_seen"
order = order if order in ("asc", "desc") else "desc"
...
elif sort == "last_seen":
    query = query.order_by(
        Node.last_seen.desc() if order == "desc" else Node.last_seen.asc()
    )
```

`Node.last_seen` is nullable (`src/meshcore_hub/common/models/node.py:65-69`).
When `last_seen IS NULL`, the row's position depends on the database's implicit
NULL ordering, which is **not portable**:

| Backend | `ORDER BY last_seen DESC` → NULL position |
|---------|--------------------------------------------|
| SQLite  | NULLs **last** (treated as smallest value) |
| Postgres| NULLs **first** (NULLs sort as if largest) |

On SQLite (the previous backend) the default `DESC` sort naturally placed
NULL-`last_seen` nodes at the bottom — the desired behavior. After the Postgres
migration (plan `20260613-2111-postgres-migration`), the same query floats them
to the top. No code changed; only the database's implicit NULL semantics did.

The migration plan (`20260505-1850-mobile-sorting`) changed the default to
`last_seen DESC` and its predecessor (`20260505-1555-sort-nodes-alpha`) even
noted the SQLite NULL behavior explicitly ("When `order=desc`, NULL values sort
last (also fine). No special treatment needed."). That assumption no longer
holds on Postgres, so the implicit behavior must be made explicit.

### Why only `last_seen` is affected

The other two Node sort columns cannot produce NULL sort keys:
- `public_key` is `nullable=False` (`node.py:36-41`).
- `name` sort uses `COALESCE(name_tag_subq, Node.name, Node.public_key)`
  (`nodes.py:174-176`) and always falls back to the non-null `public_key`.

The other list endpoints (advertisements, messages, telemetry, trace_paths,
raw_packets, dashboard) sort by `received_at`, which is declared
`Mapped[datetime]` (non-Optional → `NOT NULL`) on every event model. They are
therefore **not** subject to this NULL-ordering regression, and are out of
scope.

## Goals
- Nodes with a NULL `last_seen` always render at the **end** of the Node list,
  on both SQLite and Postgres, matching the pre-migration (SQLite) behavior.
- NULL ordering is governed by explicit SQL, not implicit per-dialect
  semantics, so it survives future backend changes.
- A regression test pins the contract so the bug cannot silently recur.

## Non-Goals
- Changing the default sort column or direction (stays `last_seen DESC`).
- Altering NULL handling for `name` / `public_key` sorts (non-NULL by
  construction) or for other list endpoints (`received_at` is NOT NULL).
- Frontend changes — the API response shape and existing mobile/desktop sort
  controls are unchanged.
- Index changes — `ix_nodes_last_seen` already exists (`node.py:100`); Postgres
  can still satisfy `ORDER BY last_seen DESC NULLS LAST` via a backward index
  scan. A `NULLS LAST`-aware index is deferred (see Open Questions).

## Requirements

### Functional Requirements
- The default Node list view (`GET /api/v1/nodes`, no sort params) MUST place
  every node with `last_seen IS NULL` after every node with a non-null
  `last_seen`, on both SQLite and Postgres.
- The explicit `sort=last_seen&order=asc` view MUST also place NULL-`last_seen`
  nodes at the end of the list (always-last policy).
- Sorting of nodes that all have a non-null `last_seen` MUST be unchanged
  (newest-first for DESC, oldest-first for ASC).
- All existing filters, pagination, caching, and the `name`/`public_key` sorts
  MUST behave exactly as before.

### Technical Requirements
- NULL ordering MUST be expressed via SQLAlchemy's `nullslast()` (the
  `.nullslast()` method on the `OrderBy` element, or the `nullslast()`
  function from `sqlalchemy`), producing a portable `NULLS LAST` clause.
- The change MUST be a no-op on SQLite (NULLs already sort last for DESC) and a
  behavioral fix on Postgres, validated by the SQLite+Postgres test matrix
  established in the Postgres migration plan.
- No new dependencies, migrations, or model changes.

## Implementation Plan

### Phase 1: Make `last_seen` ordering explicit — `src/meshcore_hub/api/routes/nodes.py`

Replace the implicit `last_seen` ordering block (`nodes.py:181-184`) with an
explicit `NULLS LAST` clause. Import `nullslast` from `sqlalchemy` (alongside
the existing `func`, `or_`, `select` import on `nodes.py:6`):

```python
from sqlalchemy import func, nullslast, or_, select
...
elif sort == "last_seen":
    order_col = Node.last_seen.desc() if order == "desc" else Node.last_seen.asc()
    query = query.order_by(nullslast(order_col))
```

`nullslast()` wraps the ascending/descending element and emits
`ORDER BY last_seen DESC NULLS LAST` (or `... ASC NULLS LAST`). This is the
minimal, targeted change; the `name` and `public_key` branches are left
untouched.

### Phase 2: Regression tests — `tests/test_api/test_nodes.py`

The existing `TestNodeSort` tests (`test_nodes.py:494-700+`) all set `last_seen`
on every node, so none of them exercise the NULL path. Add tests that seed a mix
of NULL and non-null `last_seen` nodes:

| Test | Description |
|------|-------------|
| `test_sort_last_seen_nulls_last_desc` | Default (`last_seen DESC`): a NULL-`last_seen` node sorts after nodes with timestamps, on both backends |
| `test_sort_last_seen_nulls_last_asc` | `sort=last_seen&order=asc`: a NULL-`last_seen` node still sorts last (always-last policy) |
| `test_sort_last_seen_all_null` | Multiple NULL-`last_seen` nodes — order is stable, all returned, no error |

Each test creates at least one node with `last_seen=None` (only `first_seen`
set, following the pattern in `test_nodes.py:534-545`) and one or more nodes
with concrete `last_seen` values, then asserts the NULL node is the final
`items[]` entry.

> **Note on test efficacy:** On the SQLite test path these tests confirm the
> contract holds (SQLite already does NULLs-last for DESC). The true regression
> catch is on the Postgres path of the test matrix, where the test fails without
> the `nullslast()` change and passes with it. Both must be run.

### Phase 3: Verify

```bash
source .venv/bin/activate
pytest --no-cov tests/test_api/test_nodes.py
# Plus the Postgres matrix leg if a Postgres test DB is available:
# DATABASE_BACKEND=postgres ... pytest --no-cov tests/test_api/test_nodes.py
pre-commit run --all-files
```

Manual check: load `/nodes` on a Postgres-backed deployment that has nodes
with no `last_seen`, and confirm they appear at the bottom of the list under
the default sort and when toggling the Last Seen column to ascending.

## Open Questions
- **`NULLS LAST`-aware index:** Postgres cannot use the existing
  `ix_nodes_last_seen` (a plain ASC index) to satisfy
  `ORDER BY last_seen DESC NULLS LAST` without a sort. If the nodes table grows
  large and this query shows up in slow-query logs, add a
  `CREATE INDEX ... ON nodes (last_seen DESC NULLS LAST)` via an Alembic
  migration. Deferred until measured; typical node counts are small.

## Review

**Status**: Approved

**Reviewed**: 2026-06-16

### Resolutions

- **Always-last vs. direction-aware**: Confirmed always-last policy.
  `nullslast()` applied to both DESC and ASC — nodes with NULL `last_seen`
  always sink to the bottom regardless of sort direction.

### Remaining Action Items

- Monitor query plans on Postgres; if `ORDER BY last_seen DESC NULLS LAST`
  triggers a sort on large node tables, add a NULLS LAST-aware index (see
  Open Questions).

## References
- `docs/plans/20260613-2111-postgres-migration/plan.md` — the migration that
  surfaced this regression; established the SQLite+Postgres test matrix.
- `docs/plans/20260505-1850-mobile-sorting/plan.md` — set the default Node sort
  to `last_seen DESC`.
- `docs/plans/20260505-1555-sort-nodes-alpha/plan.md` — introduced the
  `sort`/`order` params and the (then-SQLite-only) NULL-ordering assumption.
- `src/meshcore_hub/api/routes/nodes.py:164-165,181-184` — default sort and the
  `last_seen` ORDER BY block to change.
- `src/meshcore_hub/common/models/node.py:65-69` — `last_seen` nullable column.
- `tests/test_api/test_nodes.py:494` — `TestNodeSort` class to extend.
