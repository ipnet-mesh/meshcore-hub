# Advertisement Frequency Investigation

**Date**: 2026-05-15
**Status**: Decisions made, ready for implementation

## Problem Statement

Advertisements appear too frequently on the advertisements page. MeshCore nodes are expected to advertise at 6+ hour intervals (repeaters default to 12-hour flood adverts), yet the hub shows advertisements as frequently as every 3 hours for some nodes.

## Research Findings

### How the Collector Identifies Advertisements

The collector identifies advertisements through a precise chain:

1. **MQTT subscription**: `{prefix}/+/+/packets` (only the `packets` feed type is processed for advertisements)
2. **Decoding**: The `meshcoredecoder` library decodes the raw packet hex and extracts the header, including **payload type** and **route type**
3. **Normalization**: `LetsMeshNormalizer._build_letsmesh_advertisement_payload()` maps **decoded payload type `4` (PAYLOAD_TYPE_ADVERT)** to the `advertisement` event type
4. **Persistence**: `handle_advertisement()` creates an `Advertisement` database record

The `status` and `internal` feed types are explicitly excluded from advertisement processing (they become `letsmesh_status` and `letsmesh_internal` event logs).

### Decoded Advert Payload Structure (Type 4)

The `meshcoredecoder` library decodes advert packets (type 4) into:

| Field | Type | Description |
|-------|------|-------------|
| `publicKey` | string (64 hex) | Ed25519 public key of advertising node |
| `timestamp` | uint32 | **Node's internal Unix timestamp** when the advert was generated |
| `signature` | string (128 hex) | Ed25519 signature |
| `appData.flags` | uint8 | Flags byte: bits 0-3 = device role, bit 4 = hasLocation, bit 5 = hasFeature1, bit 6 = hasFeature2, bit 7 = hasName |
| `appData.deviceRole` | int | 1=Chat, 2=Repeater, 3=RoomServer, 4=Sensor |
| `appData.location` | object | `{latitude, longitude}` if hasLocation flag set |
| `appData.batteryVoltage` | float | Battery voltage in V (if HasFeature1 flag) |
| `appData.name` | string | Node name (if hasName flag set) |

### Packet Header Route Types

The decoded packet header includes a `routeType` field that the normalizer currently **ignores**:

| Route Type | Value | Description |
|-----------|-------|-------------|
| `TransportFlood` | 0 | Repeater-forwarded flood advertisement |
| `Flood` | 1 | Original flood advertisement from source node |
| `Direct` | 2 | Direct/zero-hop advertisement (local broadcast) |
| `TransportDirect` | 3 | Repeater-forwarded direct message |

### Root Cause: Zero-Hop + Flood Adverts

MeshCore has **two distinct advertisement mechanisms** ([source: MeshCore FAQ](https://github.com/meshcore-dev/MeshCore/blob/main/docs/faq.md)):

| Advert Type | CLI Command | Default Interval | Route Type | Behavior |
|-------------|-------------|-----------------|------------|----------|
| **Zero-hop (local)** | `set advert.interval {minutes}` | Varies by device | `Direct` (0x02) | Broadcast to nearby nodes only, not forwarded |
| **Flood** | `set flood.advert.interval {hours}` | 12 hours (repeaters) | `Flood` (0x01) → forwarded as `TransportFlood` (0x00) | Broadcast and repeated by all repeaters |

**Both types have payload type 4.** The current normalizer does not differentiate between them.

#### Frequency Analysis

For a node with typical settings:
- Zero-hop interval: 240 minutes (4 hours) — common for companion nodes with auto-advert enabled
- Flood interval: 12 hours (default for repeaters)

The observer captures both over the air, creating advertisement records at the **combined** rate. With both active, the observed interval is approximately every 3-4 hours, explaining the reported behavior.

Additionally, **flood adverts are forwarded by repeaters** as `TransportFlood`. If the same flood arrives via different paths >120 seconds apart (unlikely for local mesh but possible for large networks), duplicate records are created.

### Current Deduplication

Advertisements are deduplicated using `compute_advertisement_hash()`:

```
MD5(public_key | name | adv_type | flags | time_bucket)
```

Where `time_bucket` rounds `received_at` down to the nearest **120-second** window.

- **Same content + same node within 2 minutes**: Deduplicated (same hash)
- **Same content + same node after 2 minutes**: New record (different bucket)
- **Different content (e.g., name change)**: New record regardless of timing
- **Multi-observer**: When deduplicated, additional observers are recorded in the `event_observers` junction table with per-observer SNR/path_len

### Available But Unused Data

The decoded advert payload includes a `timestamp` field — the **node's own Unix timestamp** when it generated the advert. This field is:
- Decoded by `meshcoredecoder` and available in `decoded_payload.timestamp`
- **Not extracted** by the normalizer's `_build_letsmesh_advertisement_payload()`
- **Not stored** in the `Advertisement` model

This timestamp could be used to:
- Detect relayed/delayed advertisements (node timestamp << received_at)
- Compute true advertisement intervals per node
- Distinguish original adverts from rebroadcasts (same node timestamp, different received_at)

## Decision: Adopt Options A + C + D

All three options are complementary and will be implemented together:

- **Option A** — Store route type on the `Advertisement` model, expose in API/UI, default to showing only flood adverts
- **Option C** — Use the node's advert `timestamp` for deduplication time bucketing instead of `received_at`, and store it as `advert_timestamp` on the model
- **Option D** — Increase deduplication bucket from 120s to 300s (5 minutes) for both advertisements and telemetry

Option B (skip zero-hop at ingestion) is rejected — preserving all data is preferable.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Include `route_type` in dedup hash? | **No** | Zero-hop and flood adverts from same node have different timestamps; edge case of identical content+timestamp is practically impossible. Simpler hash preferred. |
| Validate advert_timestamp? | **Yes: ±4h from `received_at`** | Node clocks without GPS may be wrong (0, far future, etc.). If advert_timestamp differs by >4 hours from `received_at`, fall back to `received_at` for dedup bucketing. Raw timestamp is always stored for diagnosis. |
| Dashboard metrics scope? | **All flood-only** | `total_advertisements`, `advertisements_24h`, `advertisements_7d`, `recent_advertisements`, and `/activity` endpoint all count flood-only (plus NULL for historical records). Consistent with default UI filter. |
| Telemetry bucket change? | **Yes, also 300s** | Apply consistent 5-minute bucketing to `compute_telemetry_hash()` alongside advertisements. |
| Route type in UI? | **Separate column** | Add a 5th "Type" column to the table with a route type badge. Mobile cards show badge inline next to node name. |

### Combined Design

#### 1. Normalizer Changes (`letsmesh_normalizer.py`)

Extract two additional fields from the decoded packet in `_build_letsmesh_advertisement_payload()`:

- `route_type` — from the top-level `routeType` field in the decoded packet (values: 0, 1, 2, 3)
- `advert_timestamp` — from `decoded_payload.timestamp` (uint32 Unix timestamp from the node)

Map route type values to canonical strings:

| routeType | Stored Value | Label |
|-----------|-------------|-------|
| 0 | `transport_flood` | Flood (relayed) |
| 1 | `flood` | Flood (original) |
| 2 | `direct` | Zero-hop (local) |
| 3 | `transport_direct` | Direct (relayed) |

Both fields are added to `normalized_payload` and passed through to the handler.

#### 2. Deduplication Changes (`hash_utils.py`)

Update `compute_advertisement_hash()` to:

- Accept an optional `advert_timestamp` parameter (datetime from the node's timestamp)
- Use `advert_timestamp` for time bucketing when provided, falling back to `received_at`
- Increase default `bucket_seconds` from 120 to **300** (5 minutes)
- Fix existing docstring bug: docstring says default is 30, actual is 120 (correct to 300)

Also update `compute_telemetry_hash()` to increase `bucket_seconds` default from 120 to 300 for consistency.

#### 3. Advert Timestamp Validation (`handlers/advertisement.py`)

Before using `advert_timestamp` for dedup bucketing, validate it:

```
delta = abs(advert_timestamp - received_at_datetime)
if delta > timedelta(hours=4):
    advert_timestamp_for_hash = None  # fall back to received_at
else:
    advert_timestamp_for_hash = advert_timestamp_datetime
```

Raw `advert_timestamp` is always stored on the model regardless of validation, so operators can diagnose clock skew.

#### 4. Database Model Changes (`models/advertisement.py`)

Add two new nullable columns to the `Advertisement` model:

- `route_type: Mapped[str | None]` — canonical route type string (`"flood"`, `"transport_flood"`, `"direct"`, `"transport_direct"`)
- `advert_timestamp: Mapped[datetime | None]` — node's own timestamp from the decoded advert payload (stored as timezone-aware UTC)

Both nullable to maintain backward compatibility with existing records.

#### 5. Handler Changes (`handlers/advertisement.py`)

- Extract `route_type` and `advert_timestamp` from the normalized payload
- Validate `advert_timestamp` (±4h window vs `received_at`); if invalid, use `received_at` for dedup bucketing, still store raw value
- Convert valid `advert_timestamp` (uint32 epoch) to `datetime` with `datetime.fromtimestamp(ts, tz=timezone.utc)`
- Pass validated `advert_timestamp` to `compute_advertisement_hash()` for time bucketing
- Store `route_type` and `advert_timestamp` on the `Advertisement` record

#### 6. API Changes (`api/routes/advertisements.py`)

Add `route_type` query parameter to `GET /api/v1/advertisements`:

- Accept comma-separated values: e.g. `flood,transport_flood`
- Default: `flood,transport_flood` — excludes zero-hop (direct) adverts by default
- SQL: `WHERE route_type IN ('flood', 'transport_flood') OR route_type IS NULL` (NULL included for historical records)
- Pass empty string to show all route types (no WHERE clause on route_type)
- `route_type=none` or `route_type=all` as alternate ways to disable filter

Add `route_type` and `advert_timestamp` to the `AdvertisementRead` schema.

Add `route_type` to the single-advert `GET /{advertisement_id}` response schema.

#### 7. Dashboard Changes (`routes/dashboard.py`)

All advertisement metrics in `/stats` switch to flood-only:

| Metric | Change |
|--------|--------|
| `total_advertisements` | Count only `route_type IN ('flood', 'transport_flood') OR route_type IS NULL` |
| `advertisements_24h` | Same filter + `received_at >= 24h ago` |
| `advertisements_7d` | Same filter + `received_at >= 7d ago` |
| `recent_advertisements` (last 10) | Same filter |

The `/activity` endpoint also applies the flood-only filter.

`NULL` route types are included in all dashboard counts to avoid hiding historical data.

#### 8. Frontend Changes (`pages/advertisements.js`)

**Route type filter dropdown:**
- Options: "Flood & Relay" (default, `?route_type=flood,transport_flood`), "All" (no filter), "Zero-hop only" (`?route_type=direct`)
- Added to the filter card alongside existing search and observer filters

**Route type column:**
- Add a 5th column "Type" between "Public Key" and "Time" in the table
- Display as colored badge: `flood`/`transport_flood` (blue), `direct` (green), NULL (gray "Unknown")
- Mobile cards: badge shown inline next to node name

**i18n keys needed in `en.json`:**
```
"advertisements": {
    "filter_route_type_label": "Advert Type",
    "route_type_all": "All",
    "route_type_flood": "Flood & Relay",
    "route_type_direct": "Zero-hop only",
    "route_type_unknown": "Unknown",
    "col_route_type": "Type",
    ...
}
```

#### 9. Existing Data Migration

Existing `Advertisement` records will have `route_type=NULL` and `advert_timestamp=NULL`. All API and dashboard filters that default to flood-only must include `WHERE route_type IS NULL` to avoid hiding historical data. A future cleanup could backfill these from stored `event_hash` patterns or decoded payload logs, but this is not required for initial implementation.

### Deduplication Behavior (After Change)

| Scenario | Before | After |
|----------|--------|-------|
| Same node, same content, same flood, 2 observers <2min apart | Deduplicated (1 record, 2 observers) | Deduplicated (1 record, 2 observers) |
| Same node, same content, same flood, 2 observers 3min apart | **2 records** (different 120s buckets) | Deduplicated (same node timestamp, 5min bucket) |
| Same node, zero-hop at T, flood at T+4h | 2 records | 2 records (different node timestamps, 4h apart) |
| Same node, flood original + flood relayed 30s later | Deduplicated | Deduplicated (same node timestamp) |
| Same node, content changed (name update) | 2 records | 2 records (different hash) |
| Node with broken clock (timestamp off by 2 days) | N/A (no advert_timestamp) | Uses `received_at` for bucketing (validation rejects timestamp), raw value still stored |

## Affected Files

| File | Change |
|------|--------|
| `src/meshcore_hub/common/models/advertisement.py` | Add `route_type` and `advert_timestamp` columns |
| `src/meshcore_hub/common/hash_utils.py` | Add `advert_timestamp` parameter, increase buckets to 300s (adv + telemetry), fix docstring |
| `src/meshcore_hub/collector/letsmesh_normalizer.py` | Extract `routeType` and `timestamp` from decoded packet |
| `src/meshcore_hub/collector/handlers/advertisement.py` | Pass route type + advert timestamp, validate ±4h, use for dedup |
| `src/meshcore_hub/common/schemas/messages.py` | Add `route_type` and `advert_timestamp` to `AdvertisementRead` |
| `src/meshcore_hub/api/routes/advertisements.py` | Add `route_type` filter parameter, update base query and single-advert endpoint |
| `src/meshcore_hub/api/routes/dashboard.py` | Apply flood-only filter to all ad counts and activity endpoint |
| `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` | Add route type filter dropdown + 5th "Type" column |
| `src/meshcore_hub/web/static/locales/en.json` | Add route type filter labels and column header |
| `alembic/versions/` | Migration for `route_type` + `advert_timestamp` columns |
| `docs/upgrading.md` | Document new fields, default filter behavior, telemetry bucket change |
| `docs/i18n.md` | Document new `advertisements.*` translation keys |
| `SCHEMAS.md` | Update advertisement schema with `route_type` and `advert_timestamp` |
| `tests/test_collector/test_letsmesh_normalizer.py` | Verify `route_type` and `advert_timestamp` extraction |
| `tests/test_common/test_hash_utils.py` | Verify new hash behavior with advert_timestamp, bucket changes |
| `tests/test_api/test_advertisements.py` | Verify `route_type` filter parameter |
| `tests/test_web/` | Verify `route_type` and `advert_timestamp` in `AdvertisementRead` responses |
