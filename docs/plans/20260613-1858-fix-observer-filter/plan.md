# Fix `observed_by` Filter to Use `event_observers` Junction Table

## Summary

When a user filters the message list (and advertisement, telemetry, and
trace-path lists) by observer, the query matches only the **first** observer
that captured each deduplicated event — the value stored in the event row's
`observer_node_id` column. Secondary observers that received the same event
later are recorded in the `event_observers` junction table but are invisible to
the filter, so messages they observed are silently excluded. This produces the
symptom in issue #239: the filtered list appears "several hours behind" because
the dominant observer wins the first-insert race for recent messages, and a
secondary observer's filtered list only retains older or sporadic rows.

The fix replaces the `observed_by` predicate in all four event-list routes so it
queries the canonical `event_observers` junction table (the same source already
used to populate each event's `observers` display array) via an indexed `IN`
subquery. A shared helper is added to `observer_utils.py` to avoid duplication.

## Background & Motivation

### The deduplication model

Every event type (message, advertisement, trace, telemetry) is deduplicated by an
`event_hash`. The first observer to report an event creates a single row in the
event table (e.g. `messages`) with `observer_node_id` set to that observer. When
a **different** observer later reports the same event, no new event row is
created — instead, a new row is inserted into the `event_observers` junction
table via `add_event_observer()` (`collector/handlers/message.py:127`). The
event row's `observer_node_id` is **never updated**.

### The bug

Each list route joins the `ObserverNode` alias on `Event.observer_node_id` and
applies the `observed_by` filter against that join:

```python
# messages.py:75,86-87 (same pattern in advertisements, telemetry, trace_paths)
query = select(Message, ObserverNode.public_key, ...) \
    .outerjoin(ObserverNode, Message.observer_node_id == ObserverNode.id)

if observed_by:
    query = query.where(ObserverNode.public_key.in_(observed_by))
```

Because `observer_node_id` holds only the first observer, the filter excludes any
event whose **first** observer differs from the filter — even if the requested
observer appears in the event's `observers` response array (which is correctly
sourced from `event_observers` via `fetch_observers_for_events()`).

This inconsistency is the root cause: the per-event `observers` field shows the
observer, but the list-level filter drops the event.

### Why "several hours behind"

In a typical multi-observer hub, one well-connected observer consistently
receives messages first and owns `observer_node_id`. A secondary observer is
added to `event_observers` but never to `observer_node_id` for recent messages.
Filtering by the secondary observer therefore yields only older/sporadic messages
where it happened to be first, making the list appear stale.

### Prior work

The plan `20260426-1137-improve-snr-path-visibility` established
`event_observers` as the canonical multi-observer source, created
`api/observer_utils.py`, and wired `fetch_observers_for_events()` into all four
event routes for **display**. This plan applies the same canonical source to the
**filter** predicate, which was overlooked.

### Affected routes

| Route file | `event_type` | `observed_by` type | Bug location |
|---|---|---|---|
| `api/routes/messages.py` | `"message"` | `list[str]` | lines 86-87 |
| `api/routes/advertisements.py` | `"advertisement"` | `list[str]` | lines 115-116 |
| `api/routes/telemetry.py` | `"telemetry"` | single `str` | lines 44-45 |
| `api/routes/trace_paths.py` | `"trace"` | single `str` | lines 40-41 |

`api/routes/raw_packets.py` is **excluded** — raw packets are individual
(non-deduplicated) observations with no `event_hash` and no `event_observers`
representation, so its `observer_node_id` filter is correct.

## Goals
- The `observed_by` filter returns every event observed by any of the requested
  observers, regardless of which observer captured it first.
- Consistent filter behavior across all four event-list routes.
- A regression test proving that a secondary observer (present only in
  `event_observers`) causes the event to appear in filtered results.

## Non-Goals
- Changing the `observers` display array (already correct — sourced from
  `event_observers`).
- Modifying the collector handlers or the deduplication logic.
- Changing the `observed_by` filter in `raw_packets.py` (correct as-is).
- Backfilling `event_observers` for legacy rows that lack junction entries.
  Events with a `NULL` `event_hash` will not match `observed_by`; in production
  the handler always computes `event_hash`, so this is acceptable.
- Frontend changes (the API response shape is unchanged).

## Requirements

### Functional Requirements
- Filtering messages by `observed_by` MUST include any message whose `event_hash`
  has a matching `event_observers` row, even when `observer_node_id` points to a
  different observer.
- The same MUST hold for advertisements, telemetry, and trace paths.
- The primary-observer display fields (`observed_by`, `observer_name`) in the
  response MUST remain populated from the `observer_node_id` join (unchanged).
- Existing filtering, sorting, pagination, and channel-visibility behavior MUST
  be preserved.

### Technical Requirements
- The filter MUST use an `IN` subquery against `event_observers` joined to
  `nodes` on `public_key`, filtered by `event_type`.
- The subquery MUST leverage existing indexes: `ix_event_observers_type_hash`
  (`event_type`, `event_hash`), `event_observers.observer_node_id`, and
  `nodes.public_key`.
- The `ObserverNode` outerjoin MUST remain in each route for display purposes;
  only the `WHERE` predicate changes.
- A shared helper MUST be added to `observer_utils.py` to avoid duplicating the
  subquery across four routes.
- All existing tests MUST continue to pass after fixtures are updated to seed
  the junction table (see Implementation Plan).

## Implementation Plan

### Phase 1: Shared Filter Helper — `api/observer_utils.py`

Add a reusable WHERE-clause builder that returns a SQLAlchemy boolean expression
over the `event_observers` junction table:

```python
def observed_by_filter_clause(
    event_type: str,
    event_hash_col,
    observer_public_keys: list[str],
):
    """Return a WHERE clause matching events observed by any of the given
    observer node public keys, via the event_observers junction table."""
    return event_hash_col.in_(
        select(EventObserver.event_hash)
        .join(Node, EventObserver.observer_node_id == Node.id)
        .where(
            EventObserver.event_type == event_type,
            Node.public_key.in_(observer_public_keys),
        )
    )
```

`EventObserver` and `Node` are already imported in `observer_utils.py`. The
function takes the event-type-specific `event_hash` column (e.g.
`Message.event_hash`) so it can be reused across all four routes.

### Phase 2: Swap the Predicate in Four Routes

Each route replaces its `observed_by` `WHERE` clause with a call to the helper.
The `ObserverNode` outerjoin stays (it populates display fields).

**`api/routes/messages.py` (lines 86-87):**
```python
from meshcore_hub.api.observer_utils import observed_by_filter_clause
...
if observed_by:
    query = query.where(
        observed_by_filter_clause("message", Message.event_hash, observed_by)
    )
```

**`api/routes/advertisements.py` (lines 115-116):** same, event_type
`"advertisement"`.

**`api/routes/telemetry.py` (lines 44-45):** `observed_by` is a single `str`;
wrap as `[observed_by]`, event_type `"telemetry"`:
```python
if observed_by:
    query = query.where(
        observed_by_filter_clause("telemetry", Telemetry.event_hash, [observed_by])
    )
```

**`api/routes/trace_paths.py` (lines 40-41):** single `str`, event_type
`"trace"`, same wrapping pattern.

### Phase 3: Update Test Fixtures — `tests/test_api/conftest.py`

The four `*_with_receiver` fixtures set `observer_node_id` but create no
`event_hash` or `event_observers` row. Under the new filter they return zero
results. Each fixture must also set a deterministic `event_hash` and insert a
matching `EventObserver` row:

- `sample_message_with_receiver` (line 311)
- `sample_advertisement_with_receiver` (line 328)
- `sample_telemetry_with_receiver` (line 345)
- `sample_trace_path_with_receiver` (line 360)

**Import addition:** Add `EventObserver` to the conftest imports:
```python
from meshcore_hub.common.models import (
    ...,
    EventObserver,
)
```

Use fixed hex strings for each event type so conftest stays simple (no
`hash_utils` dependency):

| Fixture | `event_hash` value |
|---|---|
| `sample_message_with_receiver` | `"deadbeefdeadbeefdeadbeefdeadbe01"` |
| `sample_advertisement_with_receiver` | `"deadbeefdeadbeefdeadbeefdeadbe02"` |
| `sample_telemetry_with_receiver` | `"deadbeefdeadbeefdeadbeefdeadbe03"` |
| `sample_trace_path_with_receiver` | `"deadbeefdeadbeefdeadbeefdeadbe04"` |

For each fixture, **set `event_hash` as a constructor argument** on the event
row (the existing pattern sets all attributes before `add()`/`commit()`), then
after the initial commit and refresh, insert a matching `EventObserver` row and
commit again:

```python
# Example for sample_message_with_receiver
message = Message(
    ...,
    observer_node_id=receiver_node.id,
    event_hash="deadbeefdeadbeefdeadbeefdeadbe01",  # NEW
)
api_db_session.add(message)
api_db_session.commit()
api_db_session.refresh(message)

# NEW: seed the junction table
api_db_session.add(EventObserver(
    event_type="message",
    event_hash="deadbeefdeadbeefdeadbeefdeadbe01",
    observer_node_id=receiver_node.id,
    observed_at=datetime.now(timezone.utc),
))
api_db_session.commit()

return message
```

The `observed_at` field uses the already-imported `datetime.now(timezone.utc)`
(conftest line 6).

### Phase 4: Update Inline Test Data

Two tests create event rows directly (bypassing fixtures) with only
`observer_node_id`. They need `event_hash` + `EventObserver` seeding:

- `tests/test_api/test_messages.py::test_filter_by_observed_by_multiple`
  (line 275) — creates `msg1`, `msg2` inline.
- `tests/test_api/test_advertisements.py::test_list_advertisements_filter_by_observed_by_multiple`
  (line 201) — creates `ad1`, `ad2` inline.

Both test files already import `EventObserver` at the top. For deterministic
`event_hash` values, import the relevant hash functions locally or compute the
hash inline:

```python
from meshcore_hub.common.hash_utils import (
    compute_advertisement_hash,
    compute_message_hash,
)
```

Then for each inline event, set `event_hash=` in the constructor and insert a
matching `EventObserver` row after commit, following the same pattern as the
conftest fixtures in Phase 3.

### Phase 5: Add Regression Tests (one per route)

Each test creates the scenario from the bug report: an event whose
`observer_node_id = NodeA`, but `NodeB` has an `EventObserver` row for the same
`event_hash`. Assert `?observed_by=<NodeB.public_key>` returns that event.

| Test file | New test |
|---|---|
| `tests/test_api/test_messages.py` | `test_filter_by_observed_by_secondary_observer` |
| `tests/test_api/test_advertisements.py` | `test_filter_by_observed_by_secondary_observer` |
| `tests/test_api/test_telemetry.py` | `test_filter_by_observed_by_secondary_observer` |
| `tests/test_api/test_trace_paths.py` | `test_filter_by_observed_by_secondary_observer` |

Each test:
1. Creates `primary_node` (observer A) and `secondary_node` (observer B).
2. Creates an event with `observer_node_id=primary_node.id` and a known
   `event_hash`.
3. Adds an `EventObserver` row for `secondary_node` with the same `event_hash`.
4. GETs the list filtered by `observed_by=secondary_node.public_key`.
5. Asserts the event appears in results (currently fails — this is the bug).

For `test_telemetry.py` and `test_trace_paths.py`, the new tests should follow
the existing inline-import pattern from the `_observers_populated` tests
(`test_telemetry.py:129`, `test_trace_paths.py:164`), which import
`EventObserver`, `Node`, and `compute_*_hash` locally inside the test function
to keep imports self-contained.

### Phase 6: Verify

```bash
source .venv/bin/activate
pytest --no-cov tests/test_api/test_messages.py \
                 tests/test_api/test_advertisements.py \
                 tests/test_api/test_telemetry.py \
                 tests/test_api/test_trace_paths.py
pre-commit run --all-files
```

## Open Questions

- ~~Should we add a composite index on `event_observers(observer_node_id,
  event_hash)`?~~ **Resolved (review):** Deferred. The existing indexes
  (`ix_event_observers_type_hash`, `observer_node_id` FK index, `nodes.public_key`
  unique index) are sufficient for now. Monitor performance on large deployments.
- ~~Should the API expose which observer "won" the filter match?~~ **Resolved
  (review):** No — current behavior is correct. The primary `observed_by` from
  `observer_node_id` is fine; the full observer set is in the `observers` array.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-06-13

### Resolutions

- **Fixture `event_hash` approach**: Use fixed hex strings in conftest fixtures
  (e.g. `"deadbeefdeadbeefdeadbeefdeadbe01"`) instead of `compute_*_hash()`
  functions — keeps conftest simple, avoids importing `hash_utils`.
- **Fixture `EventObserver` import**: `tests/test_api/conftest.py` needs
  `EventObserver` added to its `meshcore_hub.common.models` import (currently
  not imported).
- **Phase 3 fixture update ordering**: `event_hash` must be set as a constructor
  argument on the event row (before `add()`/`commit()`) — not as a post-commit
  step. The `EventObserver` row is inserted after the initial commit.
- **Phase 4 inline test imports**: `test_messages.py` and `test_advertisements.py`
  already import `EventObserver` at top-level; need to add
  `compute_message_hash` / `compute_advertisement_hash` from
  `meshcore_hub.common.hash_utils`.
- **Phase 5 import pattern**: For `test_telemetry.py` and `test_trace_paths.py`
  regression tests, follow the existing inline-import pattern from the
  `_observers_populated` tests (`test_telemetry.py:129`, `test_trace_paths.py:164`)
  — import `EventObserver`, `Node`, and `compute_*_hash` locally inside the test.
- **Composite index**: Deferred (not needed now — existing indexes sufficient).
- **Filter-match display**: No change needed (current `observed_by` display from
  `observer_node_id` is correct).

### Remaining Action Items

- Verify SQLAlchemy's `query.subquery()` wrapping handles the correlated `IN`
  subquery in the count query correctly (messages.py line 111 and equivalents).
  Standard SQLAlchemy behavior should handle this, but confirm during
  implementation.
- Monitor query performance after deployment; if the subquery is slow on large
  `event_observers` tables, add the deferred composite index.

## References
- Issue #239 — "Observer Filtered Message List Appears Several Hours Behind"
- `docs/plans/20260426-1137-improve-snr-path-visibility/plan.md` — established
  `event_observers` as canonical multi-observer source; created
  `api/observer_utils.py`; wired `fetch_observers_for_events()` into all routes
  for display.
- `src/meshcore_hub/common/models/event_observer.py` — `EventObserver` model,
  `add_event_observer()` helper (INSERT OR IGNORE semantics).
- `src/meshcore_hub/collector/handlers/message.py:120-141` — duplicate path that
  adds secondary observers to junction without updating `observer_node_id`.
- `src/meshcore_hub/api/observer_utils.py` — existing `fetch_observers_for_events()`
  (display source), where the new helper will live.
- `src/meshcore_hub/common/hash_utils.py` — `compute_*_hash()` functions for
  deterministic `event_hash` values in tests.
```
