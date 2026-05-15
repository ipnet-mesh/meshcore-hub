# Advertisement Frequency — Task List

**Plan**: [plan.md](./plan.md)

## Implementation Order

Tasks are ordered by dependency. Each task depends on the previous ones being complete unless noted.

---

### Phase 1: Data Layer

- [x] **T1. Normalizer: extract route_type and advert_timestamp**
  - File: `src/meshcore_hub/collector/letsmesh_normalizer.py`
  - Extract `routeType` from decoded packet header, map to canonical string (`transport_flood`, `flood`, `direct`, `transport_direct`)
  - Extract `timestamp` from `decoded_payload.timestamp` as `advert_timestamp`
  - Add both to `normalized_payload` in `_build_letsmesh_advertisement_payload()`
  - Tests: `tests/test_collector/test_letsmesh_normalizer.py`

- [x] **T2. Hash utils: advert_timestamp parameter + 300s buckets**
  - File: `src/meshcore_hub/common/hash_utils.py`
  - Add optional `advert_timestamp` parameter to `compute_advertisement_hash()`
  - Use `advert_timestamp` for time bucketing when provided, fall back to `received_at`
  - Increase `bucket_seconds` default from 120 to 300 for `compute_advertisement_hash()`
  - Increase `bucket_seconds` default from 120 to 300 for `compute_telemetry_hash()`
  - Fix docstring (currently says default is 30, correct to 300)
  - Tests: `tests/test_common/test_hash_utils.py`

- [x] **T3. Database model: add route_type and advert_timestamp columns**
  - File: `src/meshcore_hub/common/models/advertisement.py`
  - Add `route_type: Mapped[str | None]` column (nullable)
  - Add `advert_timestamp: Mapped[datetime | None]` column (nullable)
  - Both nullable for backward compatibility with existing records

- [x] **T4. Alembic migration**
  - Migration: `alembic/versions/20260515_1920_add_route_type_advert_timestamp.py`
  - Adds `route_type` (VARCHAR(20), nullable) and `advert_timestamp` (DATETIME timezone, nullable)

- [x] **T5. Handler: pass route_type + advert_timestamp, validate ±4h**
  - File: `src/meshcore_hub/collector/handlers/advertisement.py`
  - Extract `route_type` and `advert_timestamp` from normalized payload
  - Validate `advert_timestamp`: if `abs(advert_timestamp - received_at) > 4h`, use `None` for hash bucketing
  - Convert `advert_timestamp` from uint32 epoch to `datetime` with `datetime.fromtimestamp(ts, tz=timezone.utc)`
  - Pass validated timestamp to `compute_advertisement_hash()`
  - Store `route_type` and `advert_timestamp` on `Advertisement` record
  - Tests: `tests/test_collector/test_handlers/test_advertisement.py`

---

### Phase 2: API

- [x] **T6. Schema: add route_type and advert_timestamp to AdvertisementRead**
  - File: `src/meshcore_hub/common/schemas/messages.py`
  - Add `route_type: Optional[str] = None` to `AdvertisementRead`
  - Add `advert_timestamp: Optional[datetime] = None` to `AdvertisementRead`

- [x] **T7. API: route_type filter on advertisements endpoint**
  - File: `src/meshcore_hub/api/routes/advertisements.py`
  - Add `route_type` query parameter to `GET /api/v1/advertisements`
  - Accept comma-separated values (e.g. `flood,transport_flood`)
  - Default: `flood,transport_flood`
  - SQL filter: `WHERE route_type IN (...) OR route_type IS NULL`
  - Support `all`, `none`, or empty string to disable filter
  - Add `route_type` and `advert_timestamp` to single-advert `GET /{advertisement_id}` response
  - Tests: `tests/test_api/test_advertisements.py`

- [x] **T8. Dashboard: flood-only filter on all ad metrics**
  - File: `src/meshcore_hub/api/routes/dashboard.py`
  - Apply `route_type IN ('flood', 'transport_flood') OR route_type IS NULL` to:
    - `total_advertisements`
    - `advertisements_24h`
    - `advertisements_7d`
    - `recent_advertisements`
  - Apply same filter to `/activity` endpoint
  - Tests: `tests/test_api/test_dashboard.py`

---

### Phase 3: Frontend

- [x] **T9. i18n: add route type translation keys**
  - File: `src/meshcore_hub/web/static/locales/en.json`
  - Add keys: `advertisements.filter_route_type_label`, `advertisements.route_type_all`, `advertisements.route_type_flood`, `advertisements.route_type_direct`, `advertisements.route_type_unknown`, `advertisements.col_route_type`
  - File: `docs/i18n.md` — document new keys

- [x] **T10. Advertisements page: route type filter + Type column**
  - File: `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`
  - Add route type dropdown to filter card: "Flood & Relay" (default), "All", "Zero-hop only"
  - Add 5th "Type" column between "Public Key" and "Time"
  - Colored badges: `flood`/`transport_flood` (blue), `direct` (green), NULL (gray "Unknown")
  - Mobile cards: badge inline next to node name
  - Pass `route_type` query parameter to API calls

---

### Phase 4: Documentation

- [x] **T11. Update documentation**
  - `docs/upgrading.md` — document new fields, default filter behavior, telemetry bucket change (120→300s)
  - `SCHEMAS.md` — update advertisement schema with `route_type` and `advert_timestamp` fields

---

### Phase 5: Verification

- [x] **T12. Run tests and quality checks**
  - `pytest tests/` — 726 passed, 22 skipped (E2E)
  - `pre-commit run --all-files` — all hooks passed (black, flake8, mypy)
