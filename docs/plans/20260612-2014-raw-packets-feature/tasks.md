# Tasks: Raw Packets — Capture, Store, and Browse Decoded Wire Packets

> Generated from `plan.md` on 2026-06-12

## 1. Database Model & Migration

- [x] 1.1 Create `RawPacket` SQLAlchemy model
  - [x] 1.1.1 Create `RawPacket` class in `src/meshcore_hub/common/models/raw_packet.py` following the `Advertisement` pattern (`Base`, `UUIDMixin`, `TimestampMixin`)
  - [x] 1.1.2 Fields: `observer_node_id` (FK `nodes.id`, `ondelete="SET NULL"`, nullable), `packet_hash` (String(32), nullable), `raw_hex` (Text, nullable), `packet_type` (Integer, nullable), `payload_type` (Integer, nullable), `event_type` (String(50), nullable), `channel_idx` (Integer, nullable), `source_pubkey_prefix` (String(12), nullable), `route_type` (String(20), nullable), `path_len` (Integer, nullable), `snr` (Float, nullable), `decoded` (JSON, nullable), `received_at` (DateTime(tz), default `utc_now`)
  - [x] 1.1.3 Single-column indexes on `received_at`, `event_type`, `packet_hash`, `channel_idx`, `source_pubkey_prefix`, `observer_node_id`
  - [x] 1.1.4 Composite indexes `(event_type, received_at)`, `(channel_idx, received_at)`, `(source_pubkey_prefix, received_at)` for the "filter then sort by newest" pattern
  - [x] 1.1.5 Add `__repr__`
  - [x] 1.1.6 Export `RawPacket` from `models/__init__.py`

- [x] 1.2 Generate Alembic migration
  - [x] 1.2.1 Run `meshcore-hub db revision --autogenerate -m "add raw_packets table"`
  - [x] 1.2.2 Review generated migration: all columns, FK, and every index (single + composite) present
  - [x] 1.2.3 Test migration: `meshcore-hub db upgrade` and verify table + indexes created

- [x] 1.3 Write unit tests for the model
  - [x] 1.3.1 Test `RawPacket` instantiation and defaults (`received_at`, timestamps)
  - [x] 1.3.2 Test nullable columns accept `None`
  - [x] 1.3.3 Test index presence via table metadata

## 2. Collector Capture & Capture Flag

- [x] 2.1 Add `raw_packet_capture_enabled` setting
  - [x] 2.1.1 Add `raw_packet_capture_enabled: bool` to `CollectorSettings` in `config.py` (env `RAW_PACKET_CAPTURE_ENABLED`, default `false`), following the `data_retention_enabled` convention
  - [x] 2.1.2 Thread through `create_subscriber()` and `run_collector()` to `Subscriber.__init__`
  - [x] 2.1.3 Store as `self._raw_packet_capture_enabled`; log capture state at startup

- [x] 2.2 Create the raw-packet handler
  - [x] 2.2.1 Create `src/meshcore_hub/collector/handlers/raw_packet.py` with `store_raw_packet(...)`
  - [x] 2.2.2 Find-or-create observer node from the topic public key (follow `handlers/event_log.py:34-50`), update `last_seen`
  - [x] 2.2.3 Derive `channel_idx = int(channelHash, 16)` via `_extract_letsmesh_decoder_channel_hash`
  - [x] 2.2.4 Derive `source_pubkey_prefix` from decoder `sourceHash` / `senderPublicKey` via `_normalize_pubkey_prefix`
  - [x] 2.2.5 Insert exactly one `RawPacket` row (no dedup); keep the transaction minimal (single insert + observer upsert, no extra reads)

- [x] 2.3 Wire the capture hook into the subscriber
  - [x] 2.3.1 Refactor `_normalize_letsmesh_event` / `_handle_mqtt_message` so the decode already performed during normalization is reused for capture (return/expose `decoded_packet` + resolved `event_type`)
  - [x] 2.3.2 In `_handle_mqtt_message`, short-circuit on `self._raw_packet_capture_enabled` (saves the insert, not the decode)
  - [x] 2.3.3 When enabled and feed is `packets`, call `store_raw_packet` before/independent of structured dispatch
  - [x] 2.3.4 Wrap capture in try/except so it never blocks event dispatch
  - [x] 2.3.5 Ensure `status` / `internal` feeds produce no raw rows

- [x] 2.4 Write collector tests
  - [x] 2.4.1 Capture writes one row per packet (enabled)
  - [x] 2.4.2 One row per observer for the same `packet_hash` (no dedup)
  - [x] 2.4.3 `channel_idx` / `source_pubkey_prefix` derivation correct
  - [x] 2.4.4 `status` / `internal` feeds write no raw rows
  - [x] 2.4.5 Capture disabled writes no rows while structured handlers still run
  - [x] 2.4.6 Capture failure is logged and does not interrupt event handling

## 3. Retention & Config

- [x] 3.1 Add `RAW_PACKET_RETENTION_DAYS` setting
  - [x] 3.1.1 Add `raw_packet_retention_days: int` to `CollectorSettings` near `data_retention_*`, defaulting to `data_retention_days` when unset
  - [x] 3.1.2 Thread through `create_subscriber()` / `run_collector()` and the cleanup scheduler

- [x] 3.2 Extend cleanup for raw packets
  - [x] 3.2.1 Add a `raw_packets_deleted` counter to `CleanupStats` (`__init__` + `__repr__`)
  - [x] 3.2.2 Add per-table retention override to `_cleanup_table` (or a dedicated call) so `raw_packets` uses `RAW_PACKET_RETENTION_DAYS` independently
  - [x] 3.2.3 Add the `RawPacket` cleanup step to `cleanup_old_data`; include in `total_deleted`
  - [x] 3.2.4 Ensure cleanup runs regardless of `raw_packet_capture_enabled` (so existing rows drain when capture is off)
  - [x] 3.2.5 Add `RawPacket.observer_node_id` to `_observer_node_id_union()` so raw-packet-only observers keep `is_observer`

- [x] 3.3 Write retention tests
  - [x] 3.3.1 Raw packets older than `RAW_PACKET_RETENTION_DAYS` are deleted; stat reported
  - [x] 3.3.2 Default falls back to global `DATA_RETENTION_DAYS` when unset
  - [x] 3.3.3 A node observing only raw packets keeps `is_observer=true` until those packets are pruned

## 4. Schemas & API

- [x] 4.1 Create Pydantic schemas
  - [x] 4.1.1 Add `RawPacketRead` / `RawPacketList` (mirror `AdvertisementRead` / `AdvertisementList`)
  - [x] 4.1.2 `RawPacketRead` includes a `redacted: bool` field

- [x] 4.2 Create the packets route module
  - [x] 4.2.1 Create `src/meshcore_hub/api/routes/raw_packets.py` with `RequireRead`, `DbSession`
  - [x] 4.2.2 Add `_packets_key_builder(request)` folding `resolve_user_role(request) or "anonymous"` into the key (per `messages.py:30`)
  - [x] 4.2.3 Decorate list with `@cached("packets", key_builder=_packets_key_builder)` using the default `redis_cache_ttl`
  - [x] 4.2.4 Define `VALID_PACKET_SORT_COLUMNS = {"time", "event_type", "packet_type", "snr", "path_len"}`, default `time`/`desc`
  - [x] 4.2.5 Register router in `api/routes/__init__.py` with `prefix="/packets"`, `tags=["Packets"]`

- [x] 4.3 Implement `GET /packets` filtering
  - [x] 4.3.1 `search` — `ilike` over `packet_hash`, `raw_hex`, observer name/public key
  - [x] 4.3.2 `event_type` (comma-separated), `packet_type` (comma-separated)
  - [x] 4.3.3 `channel_idx` (single)
  - [x] 4.3.4 `route_type` (comma-separated; `all`/`none`/`""` disables — match `/advertisements`)
  - [x] 4.3.5 `public_key` / `pubkey_prefix` → `source_pubkey_prefix`
  - [x] 4.3.6 `observed_by` (list) → observer public keys
  - [x] 4.3.7 `decryptable` (bool) — only packets whose `decoded` has decrypted text
  - [x] 4.3.8 `min_snr` / `max_snr`, `min_path_len` / `max_path_len`
  - [x] 4.3.9 `redacted` (bool) — include only / exclude redacted rows
  - [x] 4.3.10 `since` / `until` on `received_at`; `sort` / `order`; `limit` (1–100, default 50) / `offset`
  - [x] 4.3.11 Observer hydration via `aliased(Node)` + `selectinload(Node.tags)` (per `advertisements.py`)
  - [x] 4.3.12 Require `search` to combine with a narrowing window (default `since`) so the unindexed substring scan runs against a bounded set

- [x] 4.4 Implement channel-visibility redaction
  - [x] 4.4.1 Compute the visible channel-index set once via `get_visible_channel_indices` (Public idx 17 always visible)
  - [x] 4.4.2 Non-channel packets (`channel_idx IS NULL`) returned in full
  - [x] 4.4.3 Visible channel packets returned in full incl. `raw_hex` and `decoded`
  - [x] 4.4.4 Channel packets above the role: set `redacted=true`, null `raw_hex` / `decoded` / decoded text; keep hash/type/channel/path/snr/observer/timing
  - [x] 4.4.5 Do not pre-filter the SQL by visibility (rows returned but redacted) so pagination counts stay stable across roles

- [x] 4.5 Implement `GET /packets/{id}`
  - [x] 4.5.1 Single-row fetch with observer hydration
  - [x] 4.5.2 Apply the same redaction rules; 404 when not found

- [x] 4.6 Web proxy access
  - [x] 4.6.1 Add `"v1/packets": { "GET": _OPEN }` to `_build_endpoint_access()` in `web/app.py`

- [x] 4.7 Write API tests
  - [x] 4.7.1 Each filter narrows results correctly
  - [x] 4.7.2 Sort whitelist + pagination (count stable across roles)
  - [x] 4.7.3 Low role viewing a member-channel packet → `redacted=true`, null `raw_hex`/`decoded`
  - [x] 4.7.4 Non-channel packets never redacted; Public (17) always visible
  - [x] 4.7.5 Cache key differs by role (no cross-role leakage of redacted content)

## 5. Web Packets Page

- [x] 5.1 Add `FEATURE_PACKETS` feature flag
  - [x] 5.1.1 Add `feature_packets: bool` to `WebSettings` (default `False`, env `FEATURE_PACKETS`)
  - [x] 5.1.2 Add `"packets": self.feature_packets` to the `features` property (no OIDC gate)

- [x] 5.2 Create the Packets page module
  - [x] 5.2.1 Create `src/meshcore_hub/web/static/js/spa/pages/packets.js` (lit-html), modelled on `advertisements.js`
  - [x] 5.2.2 Desktop layout: `hidden lg:block` zebra `<table>` with `sortableTableHeader` columns
  - [x] 5.2.3 Mobile layout: `lg:hidden` stacked-card list with `mobileSortSelect`
  - [x] 5.2.4 Filter controls: search box, event-type chips/dropdown, channel dropdown (visible channels only), observer multi-select, route-type toggle, time-range picker
  - [x] 5.2.5 Collapsible "advanced" panel: `packet_type`, SNR range, path-len range, `decryptable`, `redacted`
  - [x] 5.2.6 Pagination + per-row lock badge when `redacted=true`

- [x] 5.3 Wire routing, icon, and nav
  - [x] 5.3.1 Add lazy import entry and `router.addRoute('/packets', pageHandler(pages.packets))` guarded by `features.packets` in `app.js`
  - [x] 5.3.2 Add a packets `updatePageTitle` case
  - [x] 5.3.3 Add a packets icon function to `icons.js` (imported by `app.js`, `home.js`, `packets.js`)
  - [x] 5.3.4 Add nav entry **immediately after Messages** on all three surfaces (guarded by `features.packets`): `spa.html` sidebar/mobile `<li>`, `app.js` dynamic nav, `home.js` hero card grid
  - [x] 5.3.5 Reorder `home.js` hero cards so **Map precedes Members** (canonical order `Dashboard → Nodes → Advertisements → Channels → Messages → Packets → Map → Members`)
  - [x] 5.3.6 Add `--color-packets` (light + dark), `.nav-icon-packets`, and the `.navbar .menu li:has(.nav-icon-packets)` accent in `app.css`

- [x] 5.4 i18n
  - [x] 5.4.1 Add keys to `en.json`: `entities.packets`, `entities.packet`, filter labels, redacted-badge label
  - [x] 5.4.2 Add the same keys to `nl.json`
  - [x] 5.4.3 Add i18n key tests if the suite covers them

- [x] 5.5 Build & web tests
  - [x] 5.5.1 Run `node build.js` to rebuild the SPA bundle
  - [x] 5.5.2 Test nav/route hidden when `FEATURE_PACKETS` is off
  - [x] 5.5.3 Test list render and redacted lock badge

## 6. Docs, Env & Compose

- [x] 6.1 Config & compose wiring
  - [x] 6.1.1 `.env.example`: add `RAW_PACKET_RETENTION_DAYS` and `RAW_PACKET_CAPTURE_ENABLED` near `DATA_RETENTION_DAYS` (commented; note retention default = `DATA_RETENTION_DAYS`, capture default = `false`)
  - [x] 6.1.2 `.env.example`: add `# FEATURE_PACKETS=false` to the feature-flags block with a note that Compose derives capture from it
  - [x] 6.1.3 `docker-compose.yml`: add `RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS:-false}` to the collector service env
  - [x] 6.1.4 `docker-compose.yml`: add `FEATURE_PACKETS=${FEATURE_PACKETS:-false}` to the web service env
  - [x] 6.1.5 Apply the same env additions to prod/traefik compose overrides

- [x] 6.2 Reference docs
  - [x] 6.2.1 `AGENTS.md`: add `RawPacket` model, `/packets` route, `FEATURE_PACKETS`, `RAW_PACKET_CAPTURE_ENABLED`, `RAW_PACKET_RETENTION_DAYS`
  - [x] 6.2.2 `SCHEMAS.md`: add the `raw_packets` table and the `RawPacketRead` shape
  - [x] 6.2.3 `docs/letsmesh.md`: note raw capture is `packets`-feed only and channel-restricted packets are returned metadata-only/redacted

- [x] 6.3 `docs/upgrading.md` v0.13.0 section
  - [x] 6.3.1 Add a new `## v0.13.0` section at the top (above `v0.12.0`)
  - [x] 6.3.2 Step: run `meshcore-hub db upgrade` to create `raw_packets`
  - [x] 6.3.3 Document new optional env vars and defaults: `FEATURE_PACKETS` (false), `RAW_PACKET_CAPTURE_ENABLED` (Compose-derived from `FEATURE_PACKETS`, false), `RAW_PACKET_RETENTION_DAYS` (= `DATA_RETENTION_DAYS`)
  - [x] 6.3.4 Explain the capture↔page split and no-backfill behaviour
  - [x] 6.3.5 Note `raw_packets` grows fastest; recommend tuning `RAW_PACKET_RETENTION_DAYS`; disabling capture drains via retention
  - [x] 6.3.6 Note `/packets` Redis caching is role-aware and honours `REDIS_CACHE_TTL`

## 7. Verification

- [x] 7.1 Code quality
  - [x] 7.1.1 Run `pre-commit run --all-files` and fix all issues

- [x] 7.2 Component tests
  - [x] 7.2.1 `pytest tests/test_common/` (model)
  - [x] 7.2.2 `pytest tests/test_collector/` (capture, flag, retention)
  - [x] 7.2.3 `pytest tests/test_api/` (filters, redaction, role-aware cache)
  - [x] 7.2.4 `pytest tests/test_web/` (flag-gated nav/route, render)
  - [x] 7.2.5 Full `pytest` to verify no regressions

- [x] 7.3 Manual verification
  - [x] 7.3.1 With `RAW_PACKET_CAPTURE_ENABLED=false` (default), confirm no `raw_packets` rows are written and structured handlers still work
  - [x] 7.3.2 Enable capture, confirm one row per packet per observer with correct `event_type` / `channel_idx` / `source_pubkey_prefix`
  - [x] 7.3.3 With `FEATURE_PACKETS=true`, confirm the Packets page and nav appear after Messages on sidebar, mobile menu, and home page; Map precedes Members
  - [x] 7.3.4 Verify desktop table / mobile card layouts and all filters
  - [x] 7.3.5 Verify redaction: a low-privilege role sees restricted-channel packets as metadata-only with a lock badge; raw_hex absent
  - [x] 7.3.6 Verify retention prunes old raw packets per `RAW_PACKET_RETENTION_DAYS` and the table drains after disabling capture
