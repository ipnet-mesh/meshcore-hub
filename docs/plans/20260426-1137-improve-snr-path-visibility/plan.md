# Observer Detail Rows — Implementation Plan

**Date:** 2026-04-26
**Status:** Approved

## Decisions

1. **No backfill** — Historical data unchanged. Per-observer `path_len` only captured for new events.
2. **Canonical case: lowercase `snr`** — All code normalizes SNR references to lowercase.
3. **Trace observer pattern** — Per-observer `path_len` tracks the observer's hop count to the event source.

## Terminology

The original research used outdated names. This plan uses the correct codebase terminology:

| Old Reference | Actual Codebase |
|---------------|-----------------|
| `event_receivers` | `event_observers` |
| `add_event_receiver()` | `add_event_observer()` |
| `_fetch_receivers_for_events()` | `_fetch_observers_for_events()` |
| `ReceiverInfo` | `ObserverInfo` |
| `receivers` (API field) | `observers` |

## Verified Current State

### Database (`event_observers` table)

```
event_observers
├── id                UUID PK
├── event_type        String(20)
├── event_hash        String(32)
├── observer_node_id  FK → nodes.id
├── snr               Float (nullable)
├── observed_at       DateTime
├── created_at        DateTime
└── updated_at        DateTime
```

**Missing:** `path_len` column.

### Per-Event vs Per-Observer Fields

| Field | Scope | Rationale |
|-------|-------|-----------|
| `snr` | **Per-observer** | Signal strength differs by observer location |
| `path_len` | **Per-observer** | Hop count differs by observer position in mesh topology |
| `observed_at` | **Per-observer** | Each observer sees the event at a different time |
| `snr_values` (trace) | **Per-event only** | Per-hop SNR along the trace path |
| `hop_count` (trace) | **Per-event only** | Total hops in the trace |

### Handler Payload Extraction

| Handler | SNR extraction | path_len extraction |
|---------|---------------|-------------------|
| `message.py` | `payload.get("SNR") or payload.get("snr")` | `payload.get("path_len")` |
| `advertisement.py` | None | None |
| `trace.py` | None | `payload.get("path_len")` |
| `telemetry.py` | None | None |

Each handler has exactly 3 `add_event_observer()` call sites:
1. Duplicate path (existing event)
2. First observer (new event)
3. Race condition recovery

All call sites need `path_len` parameter.

### LetsMesh Normalizer

`_build_letsmesh_advertisement_payload()` (handles decoded packet type 4) does NOT extract envelope `SNR` or `path`. The message payload method already does (lines 143-160). **Note:** The message method outputs `normalized_payload["SNR"]` (uppercase) at line 160, which contradicts Decision #2. This must be changed to lowercase `"snr"` alongside the advertisement fix.

### API Routes

| Route | Populates `observers`? | Notes |
|-------|----------------------|-------|
| `api/routes/messages.py` | Yes | Uses `_fetch_observers_for_events()` |
| `api/routes/advertisements.py` | Yes | Uses `_fetch_observers_for_events()` |
| `api/routes/trace_paths.py` | No — returns `[]` | Schema has field but never queries |
| `api/routes/telemetry.py` | No — returns `[]` | Same issue |

`_fetch_observers_for_events()` is duplicated identically in `messages.py` and `advertisements.py`.

### Frontend

- **`components.js:444` `receiverIcons()`** — Dead code. Uses wrong property names (`receiver_node_name` / `receiver_node_public_key`). No page imports it.
- **`messages.js` and `advertisements.js`** — Render satellite dish icons with correct property names (`recv.tag_name`, `recv.name`, `recv.public_key`) but display name-only tooltips. Per-observer SNR/path_len is returned by API but never displayed.
- **No trace_paths.js or telemetry.js frontend pages exist.**
- **No expandable/collapsible row patterns** exist anywhere in the SPA.

### Schema (`ObserverInfo`)

```python
class ObserverInfo(BaseModel):
    node_id: str
    public_key: str
    name: Optional[str]
    tag_name: Optional[str]
    snr: Optional[float]
    observed_at: datetime
```

**Missing:** `path_len` field.

---

## Implementation Plan

### Phase 1: Database Schema — Add `path_len` to `event_observers`

**File:** `src/meshcore_hub/common/models/event_observer.py`

- Add column: `path_len: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)`
- Update `add_event_observer()` signature to accept `path_len: Optional[int] = None`
- Include `path_len` in `sqlite_insert().values()` call

**Migration:**
```bash
source .venv/bin/activate
meshcore-hub db revision --autogenerate -m "add path_len to event_observers"
meshcore-hub db upgrade
```

### Phase 2: API Utility & Schema

**New file:** `src/meshcore_hub/api/observer_utils.py`

Move `_fetch_observers_for_events()` into a shared module. Update the query to also select `EventObserver.path_len`.

```python
def _fetch_observers_for_events(
    session: DbSession,
    event_type: str,
    event_hashes: list[str],
) -> dict[str, list[ObserverInfo]]:
```

The query selects: `EventObserver.event_hash`, `EventObserver.snr`, `EventObserver.path_len`, `EventObserver.observed_at`, `Node.id`, `Node.public_key`, `Node.name`. Also fetches `NodeTag` name tags.

**Schema update:** `src/meshcore_hub/common/schemas/messages.py`

Add to `ObserverInfo`:
```python
path_len: Optional[int] = Field(default=None, description="Hop count at this observer")
```

**Route updates:**

| File | Change |
|------|--------|
| `api/routes/messages.py` | Remove local `_fetch_observers_for_events`, import from `observer_utils` |
| `api/routes/advertisements.py` | Same |
| `api/routes/trace_paths.py` | Import and call `_fetch_observers_for_events(session, "trace", event_hashes)` to populate `observers` |
| `api/routes/telemetry.py` | Import and call `_fetch_observers_for_events(session, "telemetry", event_hashes)` to populate `observers` |

### Phase 3: LetsMesh Normalizer — Extract Envelope SNR & Path for Advertisements

**File:** `src/meshcore_hub/collector/letsmesh_normalizer.py`

In `_build_letsmesh_advertisement_payload()`, add after the `normalized_payload` dict initialization (line 574):

```python
snr = self._parse_float(payload.get("SNR"))
if snr is None:
    snr = self._parse_float(payload.get("snr"))
if snr is not None:
    normalized_payload["snr"] = snr

path_len = self._parse_path_length(payload.get("path"))
if path_len is not None:
    normalized_payload["path_len"] = path_len
```

This follows the same pattern used in `_build_letsmesh_message_payload()` (lines 143-160), with the key difference being lowercase `"snr"` output.

> **Inaccuracy corrected (review 2026-04-26):** The message normalizer at line 160 outputs `normalized_payload["SNR"]` (uppercase). Phase 4 below removes the handler's uppercase fallback (`payload.get("SNR") or ...`). Without also fixing the normalizer output, LetsMesh-routed messages would lose SNR data. The change below is added to enforce Decision #2 (canonical lowercase `snr`) consistently.

In `_build_letsmesh_message_payload()`, change line 160:
```python
# Before:
normalized_payload["SNR"] = snr
# After:
normalized_payload["snr"] = snr
```

### Phase 4: Collector Handlers — Pass SNR & path_len

**File:** `src/meshcore_hub/collector/handlers/message.py`

- Change line 78: `payload.get("SNR") or payload.get("snr")` → `payload.get("snr")`
- `path_len` is already extracted (line 75) — just pass it to all 3 `add_event_observer()` call sites (lines 124, 158, 178)

**File:** `src/meshcore_hub/collector/handlers/advertisement.py`

- Add extraction: `snr = payload.get("snr")`
- Add extraction: `path_len = payload.get("path_len")`
- Pass both to all 3 `add_event_observer()` call sites (lines 120, 182, 203)

**File:** `src/meshcore_hub/collector/handlers/trace.py`

- Add extraction: `snr = payload.get("snr")`
- `path_len` is already extracted (line 38) — pass both to all 3 `add_event_observer()` call sites (lines 74, 106, 126)

**File:** `src/meshcore_hub/collector/handlers/telemetry.py`

- Add extraction: `snr = payload.get("snr")`
- Add extraction: `path_len = payload.get("path_len")`
- Pass both to all 3 `add_event_observer()` call sites (lines 87, 133, 154)

### Phase 5: Frontend Components

**File:** `src/meshcore_hub/web/static/js/spa/components.js`

- **Remove** dead `receiverIcons()` function (lines 444-452) — uses wrong property names, no page imports it
- **Add** `observerDetailRow(observers, eventProperties)` component:
  - Renders an expandable sub-table below the event row
  - Observer columns:
    - **Observer** — `tag_name || name || truncateKey(public_key, 12)`, linked to `/nodes/${public_key}`
    - **SNR** — Formatted as "X.X dB" or "—" if null
    - **Path** — Formatted as "N hops" or "—" if null
    - **Received** — Relative time via `formatRelativeTime(observed_at)`
  - `eventProperties` parameter for event-level context (e.g., trace `snr_values`)
  - Toggle helper: click event row to show/hide `.observer-detail` row below it
- **Add** `observerIcons(observers)` — count badge with tooltip listing observer names

**File:** `src/meshcore_hub/web/static/css/app.css`

- `.observer-detail` expandable row styles (indented, compact sub-table)
- CSS transition for smooth expand/collapse (max-height animation)
- Responsive: desktop table vs mobile card layout

### Phase 6: Frontend Pages

**File:** `src/meshcore_hub/web/static/js/spa/pages/messages.js`

Replace current satellite dish icon rendering with:
- Observer count badge in the Receivers column (clickable to expand)
- Expandable detail row showing per-observer: name, SNR, path_len, observed_at
- Both desktop table (~line 255) and mobile card (~line 206) views

**File:** `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`

Same pattern as messages.
- Desktop table (~line 135)
- Mobile card (~line 99)

**Note:** No `trace_paths.js` frontend page exists. No frontend changes needed for trace paths — API changes in Phase 2 will surface observer data for future pages or API consumers.

### Phase 7: Tests

**`tests/test_collector/test_letsmesh_normalizer.py`**
- Test type 4 packet extracts `snr` (lowercase) and `path_len` from envelope
- Test both `"SNR"` and `"snr"` input casing normalizes to lowercase `"snr"` output
- Test message payload also outputs lowercase `"snr"` (verifies line 160 casing fix)

**`tests/test_collector/test_handlers/test_advertisement.py`**
- Test handler with `snr` and `path_len` in payload → stored in `event_observers`

**`tests/test_collector/test_handlers/test_message.py`**
- Test handler passes `path_len` to `add_event_observer()`
- Fix casing: change `"SNR": 15.5` → `"snr": 15.5` (line 21) and `"SNR": 8.5` → `"snr": 8.5` (line 102)

**`tests/test_collector/test_handlers/test_trace.py`**
- Test handler with envelope `snr`/`path_len` → stored in `event_observers`

**`tests/test_collector/test_handlers/test_telemetry.py`**
- Test handler with envelope `snr`/`path_len` → stored in `event_observers`

**`tests/test_common/test_models.py`**
- Test `add_event_observer()` accepts and stores `path_len`
- Test backwards compatibility (`path_len=None` is default)

**`tests/test_api/test_trace_paths.py`**
- Test `observers` list is populated (query returns data)

**`tests/test_api/test_telemetry.py`**
- Test `observers` list is populated (query returns data)

**Run commands:**
```bash
source .venv/bin/activate
pytest tests/test_collector/ -v
pytest tests/test_api/ -v
pytest tests/test_common/ -v
pre-commit run --all-files
```

### Phase 8: Documentation

**`SCHEMAS.md`:**
- Document that `SNR` and `path` are LetsMesh envelope fields available on all packet types
- Update `ObserverInfo` description to include `path_len`

**`AGENTS.md`:**
- Update `event_observers` table description to include `path_len` column

---

## File Change Summary

| # | File | Action | Phase |
|---|------|--------|-------|
| 1 | `common/models/event_observer.py` | Modify | 1 |
| 2 | `alembic/versions/*.py` | Create | 1 |
| 3 | `common/schemas/messages.py` | Modify | 2 |
| 4 | `api/observer_utils.py` | Create | 2 |
| 5 | `api/routes/messages.py` | Modify | 2 |
| 6 | `api/routes/advertisements.py` | Modify | 2 |
| 7 | `api/routes/trace_paths.py` | Modify | 2 |
| 8 | `api/routes/telemetry.py` | Modify | 2 |
| 9 | `collector/letsmesh_normalizer.py` | Modify | 3 |
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

---

## Source Files Reference

| File | Key Locations |
|------|--------------|
| `common/models/event_observer.py` | `EventObserver` model, `add_event_observer()` helper |
| `common/hash_utils.py` | Hash computation for deduplication |
| `common/schemas/messages.py` | `ObserverInfo`, `MessageRead`, `AdvertisementRead`, `TracePathRead`, `TelemetryRead` |
| `collector/letsmesh_normalizer.py` | `_build_letsmesh_advertisement_payload()` (line 544), `_build_letsmesh_message_payload()` (line 84) |
| `collector/handlers/advertisement.py` | 3x `add_event_observer()` at lines 120, 182, 203 |
| `collector/handlers/message.py` | 3x `add_event_observer()` at lines 124, 158, 178 |
| `collector/handlers/trace.py` | 3x `add_event_observer()` at lines 74, 106, 126 |
| `collector/handlers/telemetry.py` | 3x `add_event_observer()` at lines 87, 133, 154 |
| `api/routes/messages.py` | `_fetch_observers_for_events()` at line 28 |
| `api/routes/advertisements.py` | `_fetch_observers_for_events()` at line 42 |
| `api/routes/trace_paths.py` | Returns `[]` for observers |
| `api/routes/telemetry.py` | Returns `[]` for observers |
| `web/static/js/spa/components.js` | Dead `receiverIcons()` at line 444 |
| `web/static/js/spa/pages/messages.js` | Observer rendering at lines 206-216 (mobile), 255-267 (desktop) |
| `web/static/js/spa/pages/advertisements.js` | Observer rendering at lines 99-109 (mobile), 135-147 (desktop) |
