# Observer Detail Rows — Task Checklist

**Plan:** `docs/plans/20260426-1137-improve-snr-path-visibility/plan.md`
**Status:** Complete

## Review Notes

> **Plan accuracy issue found:** Phase 4 changes `message.py` handler to read only `payload.get("snr")` (lowercase), but the LetsMesh **message** normalizer (`letsmesh_normalizer.py:160`) still outputs `normalized_payload["SNR"]` (uppercase). Phase 3 only fixes the **advertisement** normalizer. An additional task (Phase 3.5) is included below to normalize the message normalizer output to lowercase `"snr"`, consistent with Decision #2.

---

## Phase 1: Database Schema

- [x] **1.1** Add `path_len: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)` to `EventObserver` model in `src/meshcore_hub/common/models/event_observer.py`
- [x] **1.2** Add `path_len: Optional[int] = None` parameter to `add_event_observer()` signature
- [x] **1.3** Include `path_len=path_len` in `sqlite_insert().values()` call
- [x] **1.4** Generate Alembic migration: `meshcore-hub db revision --autogenerate -m "add path_len to event_observers"`
- [x] **1.5** Review and adjust migration file
- [x] **1.6** Run migration: `meshcore-hub db upgrade`

## Phase 2: API Utility & Schema

- [x] **2.1** Add `path_len: Optional[int] = Field(default=None, description="Hop count at this observer")` to `ObserverInfo` schema in `src/meshcore_hub/common/schemas/messages.py`
- [x] **2.2** Create `src/meshcore_hub/api/observer_utils.py` — move shared `_fetch_observers_for_events()` function
- [x] **2.3** Update shared query to also select `EventObserver.path_len`
- [x] **2.4** Include `path_len=row.path_len` in `ObserverInfo()` construction within the shared function
- [x] **2.5** Update `api/routes/messages.py` — remove local `_fetch_observers_for_events`, import from `observer_utils`; also remove local `_get_tag_name` if it becomes unused
- [x] **2.6** Update `api/routes/advertisements.py` — same as 2.5
- [x] **2.7** Update `api/routes/trace_paths.py` — import and call `_fetch_observers_for_events(session, "trace", event_hashes)` for both list and detail endpoints; include `"observers"` key in response dicts
- [x] **2.8** Update `api/routes/telemetry.py` — same pattern as 2.7 with `"telemetry"` event type

## Phase 3: LetsMesh Normalizer — Advertisement SNR & Path

- [x] **3.1** In `src/meshcore_hub/collector/letsmesh_normalizer.py`, in `_build_letsmesh_advertisement_payload()`, add SNR extraction after `normalized_payload` dict initialization (~line 574): `snr = self._parse_float(payload.get("SNR"))`, fallback to `payload.get("snr")`, store as `normalized_payload["snr"]` (lowercase)
- [x] **3.2** Add `path_len = self._parse_path_length(payload.get("path"))` extraction, store as `normalized_payload["path_len"]`
- [x] **3.3** Return the updated `normalized_payload` (already returned at line 627)

## Phase 3.5: LetsMesh Normalizer — Message SNR Casing Fix

> **Accuracy fix:** Not in original plan. Required to prevent SNR data loss for LetsMesh-routed messages after Phase 4 removes the uppercase fallback.

- [x] **3.5.1** In `src/meshcore_hub/collector/letsmesh_normalizer.py`, change line 160: `normalized_payload["SNR"]` → `normalized_payload["snr"]` (lowercase, per Decision #2)

## Phase 4: Collector Handlers

- [x] **4.1** `src/meshcore_hub/collector/handlers/message.py` — change line 78: `payload.get("SNR") or payload.get("snr")` → `payload.get("snr")`
- [x] **4.2** `message.py` — pass `path_len=path_len` to all 3 `add_event_observer()` call sites (lines 124, 158, 178)
- [x] **4.3** `src/meshcore_hub/collector/handlers/advertisement.py` — add extraction: `snr = payload.get("snr")` and `path_len = payload.get("path_len")`
- [x] **4.4** `advertisement.py` — pass `snr=snr, path_len=path_len` to all 3 `add_event_observer()` call sites (lines 120, 182, 203); replace current `snr=None`
- [x] **4.5** `src/meshcore_hub/collector/handlers/trace.py` — add extraction: `snr = payload.get("snr")`
- [x] **4.6** `trace.py` — pass `snr=snr, path_len=path_len` to all 3 `add_event_observer()` call sites (lines 74, 106, 126); replace current `snr=None`
- [x] **4.7** `src/meshcore_hub/collector/handlers/telemetry.py` — add extraction: `snr = payload.get("snr")` and `path_len = payload.get("path_len")`
- [x] **4.8** `telemetry.py` — pass `snr=snr, path_len=path_len` to all 3 `add_event_observer()` call sites (lines 87, 133, 154); replace current `snr=None`

## Phase 5: Frontend Components

- [x] **5.1** Remove dead `receiverIcons()` function from `src/meshcore_hub/web/static/js/spa/components.js` (lines 444-452)
- [x] **5.2** Add `observerDetailRow(observers, eventProperties)` component to `components.js`:
  - Renders expandable sub-table with columns: Observer (name/link), SNR (formatted dB), Path (formatted hops), Received (relative time)
  - `eventProperties` param for event-level context (e.g., trace `snr_values`)
  - Toggle helper: click event row to show/hide `.observer-detail` row
- [x] **5.3** Add `observerIcons(observers)` component — count badge with tooltip listing observer names
- [x] **5.4** Add `.observer-detail` expandable row styles to `src/meshcore_hub/web/static/css/app.css`:
  - Indented, compact sub-table styling
  - CSS transition for smooth expand/collapse (max-height animation)
  - Responsive: desktop table vs mobile card layout

## Phase 6: Frontend Pages

- [x] **6.1** Update `src/meshcore_hub/web/static/js/spa/pages/messages.js`:
  - Replace satellite dish icon rendering with observer count badge (clickable to expand)
  - Add expandable detail row showing per-observer: name, SNR, path_len, observed_at
  - Update both mobile card view (~line 206) and desktop table view (~line 255)
- [x] **6.2** Update `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`:
  - Same pattern as messages
  - Update both mobile card view (~line 99) and desktop table view (~line 135)

## Phase 7: Tests

- [x] **7.1** `tests/test_collector/test_letsmesh_normalizer.py` — test type 4 packet extracts `snr` (lowercase) and `path_len` from envelope
- [x] **7.2** `tests/test_collector/test_letsmesh_normalizer.py` — test both `"SNR"` and `"snr"` input casing normalizes to lowercase `"snr"` output
- [x] **7.3** `tests/test_collector/test_letsmesh_normalizer.py` — test message payload also outputs lowercase `"snr"` (verifies Phase 3.5 fix)
- [x] **7.4** `tests/test_collector/test_handlers/test_advertisement.py` — test handler with `snr` and `path_len` in payload → stored in `event_observers`
- [x] **7.5** `tests/test_collector/test_handlers/test_message.py` — test handler passes `path_len` to `add_event_observer()`
- [x] **7.6** `tests/test_collector/test_handlers/test_message.py` — fix casing: `"SNR": 15.5` → `"snr": 15.5` (line 21) and `"SNR": 8.5` → `"snr": 8.5` (line 102)
- [x] **7.7** `tests/test_collector/test_handlers/test_trace.py` — test handler with envelope `snr`/`path_len` → stored in `event_observers`
- [x] **7.8** `tests/test_collector/test_handlers/test_telemetry.py` — test handler with envelope `snr`/`path_len` → stored in `event_observers`
- [x] **7.9** `tests/test_common/test_models.py` — test `add_event_observer()` accepts and stores `path_len`
- [x] **7.10** `tests/test_common/test_models.py` — test backwards compatibility (`path_len=None` is default)
- [x] **7.11** `tests/test_api/test_trace_paths.py` — test `observers` list is populated (query returns data)
- [x] **7.12** `tests/test_api/test_telemetry.py` — test `observers` list is populated (query returns data)
- [x] **7.13** Run targeted tests: `pytest tests/test_collector/ -v`
- [x] **7.14** Run targeted tests: `pytest tests/test_api/ -v`
- [x] **7.15** Run targeted tests: `pytest tests/test_common/ -v`
- [x] **7.16** Run quality checks: `pre-commit run --all-files`

## Phase 8: Documentation

- [x] **8.1** Update `SCHEMAS.md` — document that `SNR` and `path` are LetsMesh envelope fields available on all packet types
- [x] **8.2** Update `SCHEMAS.md` — update `ObserverInfo` description to include `path_len`
- [x] **8.3** Update `AGENTS.md` — update `event_observers` table description to include `path_len` column

---

## File Change Summary

| # | File | Action | Phase(s) |
|---|------|--------|----------|
| 1 | `common/models/event_observer.py` | Modify | 1 |
| 2 | `alembic/versions/*.py` | Create | 1 |
| 3 | `common/schemas/messages.py` | Modify | 2 |
| 4 | `api/observer_utils.py` | Create | 2 |
| 5 | `api/routes/messages.py` | Modify | 2 |
| 6 | `api/routes/advertisements.py` | Modify | 2 |
| 7 | `api/routes/trace_paths.py` | Modify | 2 |
| 8 | `api/routes/telemetry.py` | Modify | 2 |
| 9 | `collector/letsmesh_normalizer.py` | Modify | 3, 3.5 |
| 10 | `collector/handlers/message.py` | Modify | 4 |
| 11 | `collector/handlers/advertisement.py` | Modify | 4 |
| 12 | `collector/handlers/trace.py` | Modify | 4 |
| 13 | `collector/handlers/telemetry.py` | Modify | 4 |
| 14 | `web/static/js/spa/components.js` | Modify | 5 |
| 15 | `web/static/css/app.css` | Modify | 5 |
| 16 | `web/static/js/spa/pages/messages.js` | Modify | 6 |
| 17 | `web/static/js/spa/pages/advertisements.js` | Modify | 6 |
| 18 | `SCHEMAS.md` | Modify | 8 |
| 19 | `AGENTS.md` | Modify | 8 |
