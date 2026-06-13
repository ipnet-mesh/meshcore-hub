# Tasks: Fix `observed_by` Filter to Use `event_observers` Junction Table

> Generated from `plan.md` on 2026-06-13

## Shared Filter Helper

- [x] Add `observed_by_filter_clause()` to `src/meshcore_hub/api/observer_utils.py`
  - [x] Define function signature: `(event_type: str, event_hash_col, observer_public_keys: list[str])`
  - [x] Build `IN` subquery: `select(EventObserver.event_hash).join(Node, ...).where(event_type, Node.public_key.in_(...))`
  - [x] Return `event_hash_col.in_(subquery)` — a SQLAlchemy `ColumnElement[bool]`
  - [x] Verify `EventObserver` and `Node` are already imported in `observer_utils.py`

## Route Predicate Swaps

- [x] Fix `observed_by` filter in `src/meshcore_hub/api/routes/messages.py`
  - [x] Import `observed_by_filter_clause` from `observer_utils`
  - [x] Replace `query.where(ObserverNode.public_key.in_(observed_by))` ~line 87 with `observed_by_filter_clause("message", Message.event_hash, observed_by)`
  - [x] Keep `ObserverNode` outerjoin intact (it populates display fields)

- [x] Fix `observed_by` filter in `src/meshcore_hub/api/routes/advertisements.py`
  - [x] Import `observed_by_filter_clause` from `observer_utils`
  - [x] Replace `query.where(ObserverNode.public_key.in_(observed_by))` ~line 116 with `observed_by_filter_clause("advertisement", Advertisement.event_hash, observed_by)`
  - [x] Keep `ObserverNode` outerjoin intact

- [x] Fix `observed_by` filter in `src/meshcore_hub/api/routes/telemetry.py`
  - [x] Import `observed_by_filter_clause` from `observer_utils`
  - [x] Replace `query.where(ObserverNode.public_key.in_([observed_by]))` ~line 45 with `observed_by_filter_clause("telemetry", Telemetry.event_hash, [observed_by])`
  - [x] Note: `observed_by` is a single `str` — wrap in a list for the helper call
  - [x] Keep `ObserverNode` outerjoin intact

- [x] Fix `observed_by` filter in `src/meshcore_hub/api/routes/trace_paths.py`
  - [x] Import `observed_by_filter_clause` from `observer_utils`
  - [x] Replace `query.where(ObserverNode.public_key.in_([observed_by]))` ~line 41 with `observed_by_filter_clause("trace", TracePath.event_hash, [observed_by])`
  - [x] Note: `observed_by` is a single `str` — wrap in a list for the helper call
  - [x] Keep `ObserverNode` outerjoin intact

## Conftest Fixture Updates

- [x] Add `EventObserver` to the `tests/test_api/conftest.py` imports
  - [x] Add `EventObserver` to the existing `from meshcore_hub.common.models import (...)` block

- [x] Update `sample_message_with_receiver` fixture (~line 311)
  - [x] Set `event_hash="deadbeefdeadbeefdeadbeefdeadbe01"` on the `Message` constructor
  - [x] After `api_db_session.commit()` + `refresh()`, insert `EventObserver(event_type="message", event_hash=..., observer_node_id=receiver_node.id, observed_at=datetime.now(timezone.utc))`
  - [x] Commit the `EventObserver` insert

- [x] Update `sample_advertisement_with_receiver` fixture (~line 328)
  - [x] Set `event_hash="deadbeefdeadbeefdeadbeefdeadbe02"` on the `Advertisement` constructor
  - [x] After commit + refresh, insert `EventObserver(event_type="advertisement", event_hash=..., observer_node_id=receiver_node.id, observed_at=datetime.now(timezone.utc))`
  - [x] Commit the `EventObserver` insert

- [x] Update `sample_telemetry_with_receiver` fixture (~line 345)
  - [x] Set `event_hash="deadbeefdeadbeefdeadbeefdeadbe03"` on the `Telemetry` constructor
  - [x] After commit + refresh, insert `EventObserver(event_type="telemetry", event_hash=..., observer_node_id=receiver_node.id, observed_at=datetime.now(timezone.utc))`
  - [x] Commit the `EventObserver` insert

- [x] Update `sample_trace_path_with_receiver` fixture (~line 360)
  - [x] Set `event_hash="deadbeefdeadbeefdeadbeefdeadbe04"` on the `TracePath` constructor
  - [x] After commit + refresh, insert `EventObserver(event_type="trace", event_hash=..., observer_node_id=receiver_node.id, observed_at=datetime.now(timezone.utc))`
  - [x] Commit the `EventObserver` insert

## Inline Test Data Updates

- [x] Update `test_filter_by_observed_by_multiple` in `tests/test_api/test_messages.py` (~line 275)
  - [x] Add `from meshcore_hub.common.hash_utils import compute_message_hash` to imports (if not already present)
  - [x] Set `event_hash=compute_message_hash(...)` on each inline `msg1`/`msg2` constructor
  - [x] After each message commit, insert a matching `EventObserver` row for the observer node

- [x] Update `test_list_advertisements_filter_by_observed_by_multiple` in `tests/test_api/test_advertisements.py` (~line 201)
  - [x] Add `from meshcore_hub.common.hash_utils import compute_advertisement_hash` to imports
  - [x] Set `event_hash=compute_advertisement_hash(...)` on each inline `ad1`/`ad2` constructor
  - [x] After each advertisement commit, insert a matching `EventObserver` row for the observer node

## Regression Tests

- [x] Add `test_filter_by_observed_by_secondary_observer` to `tests/test_api/test_messages.py`
  - [x] Create two nodes: `primary_node` and `secondary_node`
  - [x] Create a message with `observer_node_id=primary_node.id` and a deterministic `event_hash`
  - [x] Insert `EventObserver` for `secondary_node` with the same `event_hash`
  - [x] GET `/messages?observed_by=<secondary_node.public_key>` and assert the message appears
  - [x] Assert the returned message's `observed_by` field shows `primary_node` (display not changed)

- [x] Add `test_filter_by_observed_by_secondary_observer` to `tests/test_api/test_advertisements.py`
  - [x] Same pattern: primary/secondary nodes, ad with `observer_node_id=primary`, `EventObserver` for secondary
  - [x] GET `/advertisements?observed_by=<secondary_node.public_key>` and assert the ad appears

- [x] Add `test_filter_by_observed_by_secondary_observer` to `tests/test_api/test_telemetry.py`
  - [x] Follow existing inline-import pattern (import `EventObserver`, `Node`, `compute_telemetry_hash` locally inside test)
  - [x] Same pattern: primary/secondary nodes, telemetry with `observer_node_id=primary`, `EventObserver` for secondary
  - [x] GET `/telemetry?observed_by=<secondary_node.public_key>` and assert the telemetry appears

- [x] Add `test_filter_by_observed_by_secondary_observer` to `tests/test_api/test_trace_paths.py`
  - [x] Follow existing inline-import pattern (import `EventObserver`, `Node`, `compute_trace_hash` locally inside test)
  - [x] Same pattern: primary/secondary nodes, trace with `observer_node_id=primary`, `EventObserver` for secondary
  - [x] GET `/trace_paths?observed_by=<secondary_node.public_key>` and assert the trace appears

## Verification

- [x] Run targeted test suite
  - [x] `pytest --no-cov tests/test_api/test_messages.py`
  - [x] `pytest --no-cov tests/test_api/test_advertisements.py`
  - [x] `pytest --no-cov tests/test_api/test_telemetry.py`
  - [x] `pytest --no-cov tests/test_api/test_trace_paths.py`

- [x] Run full API test suite to catch any unexpected breakage
  - [x] `pytest --no-cov tests/test_api/`

- [x] Run pre-commit checks
  - [x] `pre-commit run --all-files`

- [x] Verify count query compatibility
  - [x] Confirm `query.subquery()` wrapping in messages.py (~line 111) and equivalents handle the correlated `IN` subquery without error
