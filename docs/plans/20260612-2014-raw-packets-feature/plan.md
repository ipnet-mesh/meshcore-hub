# Raw Packets: Capture, Store, and Browse Decoded Wire Packets

## Summary

Add a first-class **Raw Packets** feature that captures every inbound MeshCore
packet exactly as it arrives over the LetsMesh `packets` feed, independent of how
the collector later classifies it. Today the collector decodes each packet and
routes it to a structured handler (advertisement, message, trace, telemetry,
contact); the original on-air bytes are then discarded for everything that
matches a structured handler, and only unclassified leftovers reach the
`events_log` table. There is no complete, searchable record of raw traffic.

This plan introduces a `raw_packets` table populated **unconditionally** at
ingest from the already-decoded packet, a `/packets` API with rich filtering and
channel-visibility-aware redaction, and a new SPA **Packets** page (disabled by
default) for display/search/filter. The structured tables remain derived views,
linkable back to raw packets by `packet_hash`.

## Background & Motivation

### Current State

1. The collector subscribes to three LetsMesh upload feeds
   (`subscriber.py:512`): `<prefix>/+/+/packets`, `/status`, `/internal`.
2. Each `packets` payload carries the on-air packet as hex in `payload["raw"]`.
3. `LetsMeshNormalizer._normalize_letsmesh_event` (`letsmesh_normalizer.py:23`)
   decodes the packet once via `LetsMeshPacketDecoder.decode_payload`
   (`letsmesh_decoder.py:219`) and classifies it into an event type: message,
   advertisement, trace, contact, telemetry, path/status, or the catch-all
   `letsmesh_packet`.
4. The normalized event is dispatched to a handler (`subscriber.py:213`).
   Structured handlers (`handlers/__init__.py:26-31`) extract specific columns
   into their own tables and **drop** the raw hex. Only unmatched/informational
   events fall through to `handle_event_log`, which stores the full payload JSON
   (raw hex included) in `events_log`.

### Problems

- **Lossy capture**: The most interesting packets (adverts, channel messages,
  traces, telemetry) are parsed and their raw form is not retained. The raw
  record only survives for the packets that *don't* map to a structured handler.
- **No raw browse/search**: Operators debugging the mesh (decode failures,
  unexpected packet types, path/SNR anomalies) have no way to view or filter the
  actual wire packets.
- **No per-observer record**: Structured tables dedupe by event hash across
  observers; there is no one-row-per-reception log of what each observer heard.

### Why Now

The decoder already runs on every packet and already attempts decryption with the
DB-backed channel key store (`letsmesh_decoder.py:240`). The channel-visibility
machinery (`channel_visibility.py`) and API-key auth (`auth.py`) already exist and
are used by the messages feed. Capturing the raw packet is therefore a cheap
addition that reuses the existing decode, key store, and visibility model — no new
crypto and no second decode.

## Goals

- Introduce a `RawPacket` SQLAlchemy model capturing every `packets`-feed packet,
  one row per observer reception (no dedup).
- Persist the raw hex, classification, decoded summary, channel index, source
  identity, and link metadata (`packet_hash`) at ingest, reusing the decode the
  normalizer already performs.
- Add a separate `RAW_PACKET_RETENTION_DAYS` knob (defaulting to the global
  retention default) and wire `raw_packets` into the existing cleanup scheduler.
- Provide a `/packets` API with filtering, sorting, and pagination consistent
  with `/advertisements` and `/messages`.
- Apply channel-visibility rules to channel-message packets: packets on channels
  above the user's role are returned as **metadata-only with the payload
  redacted** (not hidden); `raw_hex` is returned in full for any non-redacted
  packet.
- Provide a SPA **Packets** page behind a feature flag that is **off by default**.

## Non-Goals

- Capturing the `status` / `internal` feeds (they carry station housekeeping, not
  on-air packets — see Requirements). These already land in `events_log`.
- Deduplicating raw packets across observers (explicitly one row per reception).
- Changing the `meshcoredecoder` library or any decryption logic.
- Decrypting direct/contact (node-to-node ECDH) messages — the hub holds no node
  private keys; those remain ciphertext with no decoded text.
- Encrypting `raw_hex` at rest, or per-user (non-role) access control.
- Backfilling raw packets for traffic received before this feature ships.

## Requirements

### Functional Requirements

- **FR-1**: A `RawPacket` database model with fields:
  - `id` (UUID primary key)
  - `observer_node_id` (FK `nodes.id`, `ondelete=SET NULL`, nullable, indexed) —
    the receiving interface, resolved from the MQTT topic public key
  - `packet_hash` (String(32), nullable, indexed) — LetsMesh `hash`; links rows to
    structured-table records and groups multi-observer receptions
  - `raw_hex` (Text, nullable) — the on-air bytes from `payload["raw"]`
  - `packet_type` (Integer, nullable, indexed) — wire packet type
  - `payload_type` (Integer, nullable) — decoder payload type
  - `event_type` (String(50), nullable, indexed) — how the collector classified
    the packet (`advertisement`, `channel_msg_recv`, `contact_msg_recv`,
    `trace_data`, `telemetry_response`, `letsmesh_packet`, ...)
  - `channel_idx` (Integer, nullable, indexed) — `int(channelHash, 16)` for
    channel-message packets; drives visibility filtering. `NULL` for non-channel
    packets.
  - `source_pubkey_prefix` (String(12), nullable, indexed) — sender prefix derived
    from the decoder `sourceHash` / `senderPublicKey`, for efficient
    "packets from this node" filtering
  - `route_type` (String(20), nullable)
  - `path_len` (Integer, nullable)
  - `snr` (Float, nullable)
  - `decoded` (JSON, nullable) — decoder summary, so the detail view needs no
    re-decode
  - `received_at` (DateTime(tz), default `utc_now`, indexed)
  - `created_at`, `updated_at` (timestamps via `TimestampMixin`)
- **FR-2**: When capture is enabled (FR-13), for **every** message on the
  `packets` feed the collector writes exactly one `RawPacket` row, regardless of
  how the packet is subsequently classified or whether a structured handler also
  persists it. Capture happens before/independent of structured dispatch so the
  table is complete. When capture is disabled, no `RawPacket` rows are written and
  the structured handlers continue unchanged.
- **FR-3**: The `status` and `internal` feeds are **not** captured as raw packets
  (they carry no `raw` hex). No change to their existing `letsmesh_status` /
  `letsmesh_internal` handling.
- **FR-4**: No deduplication. If N observers report the same packet, N rows are
  stored (grouped by `packet_hash`).
- **FR-5**: `RawPacket` rows are subject to data-retention cleanup using a
  dedicated `RAW_PACKET_RETENTION_DAYS` setting, defaulting to the existing global
  `DATA_RETENTION_DAYS` value. Cleanup runs in the existing scheduler.
- **FR-6**: `GET /packets` lists raw packets with the following filters, all
  optional and combinable:
  - `search` (string) — `ilike` across `packet_hash`, `raw_hex`, and observer
    name/public key
  - `event_type` (string, comma-separated allowed) — classification filter
  - `packet_type` (int, comma-separated allowed) — wire type filter
  - `channel_idx` (int) — single channel filter
  - `route_type` (string, comma-separated; `all`/`none`/`""` disables) — same
    semantics as `/advertisements`
  - `public_key` / `pubkey_prefix` (string) — filter by `source_pubkey_prefix`
  - `observed_by` (list[str]) — filter by receiver node public keys
  - `decryptable` (bool) — only packets whose `decoded` contains decrypted text
    (vs ciphertext-only)
  - `min_snr` / `max_snr` (float) — SNR range
  - `min_path_len` / `max_path_len` (int) — hop-count range
  - `redacted` (bool) — include only / exclude redacted (metadata-only) rows
  - `since` / `until` (datetime) — `received_at` window
  - `sort` / `order` — `sort` in `VALID_PACKET_SORT_COLUMNS`, `order` in
    `asc`/`desc`
  - `limit` (1–100, default 50) / `offset` (>= 0)
- **FR-7**: `GET /packets/{id}` returns a single raw packet with its decoded
  summary, subject to the same visibility/redaction rules.
- **FR-8**: **Channel-visibility redaction**. Using the user's resolved role
  (`channel_visibility.resolve_user_role` + `get_visible_channel_indices`):
  - Non-channel packets (`channel_idx IS NULL`): returned in full.
  - Channel packets whose `channel_idx` is visible to the role: returned in full,
    including `raw_hex` and `decoded`.
  - Channel packets whose `channel_idx` is **above** the role's level: returned
    with `redacted=true` and `raw_hex`, `decoded`, and any decoded text nulled
    out. Non-sensitive metadata is retained: `packet_hash`, `packet_type`,
    `event_type`, `channel_idx`, `route_type`, `path_len`, `snr`,
    `observer`, `received_at`.
  - The built-in Public channel (idx 17) is always visible.
- **FR-9**: `raw_hex` is **always included** in the response for any non-redacted
  packet the user is permitted to see (no extra role gate beyond visibility).
- **FR-10**: A SPA **Packets** page at `/packets`, controlled by a
  `FEATURE_PACKETS` flag that defaults to **off**. The page provides:
  - text search box (`search`)
  - event-type chips / dropdown (`event_type`)
  - channel dropdown (`channel_idx`) showing only channels the role can see
  - observer multi-select (`observed_by`)
  - route-type toggle group (`route_type`)
  - time-range picker (`since` / `until`)
  - a collapsible "advanced" panel for `packet_type`, SNR range, path-len range,
    `decryptable`, `redacted`
  - **responsive layout matching the other list pages**: a zebra `<table>` on
    desktop (`hidden lg:block`) with `sortableTableHeader` columns, and a stacked
    **card** list on mobile (`lg:hidden`) with a `mobileSortSelect`
  - pagination
  - a per-row lock badge when `redacted=true`
- **FR-11**: A node-detail "packets from this node" view can reuse `/packets`
  with `pubkey_prefix` (out of scope to build the node-detail UI here, but the
  filter and index must support it).
- **FR-12**: Navigation entry points for the Packets page, all gated on
  `features.packets` (so they stay hidden while the flag is off by default),
  inserted **immediately after Messages** on every surface (i.e. `... → Messages →
  Packets → Map → Members ...`), consistently across all three:
  - **Homepage hero nav card** in `home.js` (`renderNavCard`) with a
    `--color-packets` accent
  - **Sidebar / mobile menu**: the dynamic nav in `app.js` and the static nav in
    `spa.html`
  - a matching page title in `updatePageTitle`
- **FR-13**: A **collector-side capture flag** `RAW_PACKET_CAPTURE_ENABLED`
  (default `false`) controls whether the collector writes `RawPacket` rows. It is
  independent of the web `FEATURE_PACKETS` flag (the collector and web are separate
  processes with separate settings), but Compose links them by default so a single
  source var drives both:
  `RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS:-false}`. When disabled, the
  collector performs no raw-packet inserts (eliminating the write-amplification
  cost) while normalization/structured handling is unaffected. Capture has no
  backfill, so the web page only shows packets captured while the flag was on.
  Retention cleanup of `raw_packets` runs regardless of this flag, so turning
  capture off lets existing rows drain via `RAW_PACKET_RETENTION_DAYS`.

### Technical Requirements

- **TR-1**: New model `RawPacket` in
  `src/meshcore_hub/common/models/raw_packet.py`, exported from
  `models/__init__.py`. Follows the `Advertisement` pattern (`UUIDMixin`,
  `TimestampMixin`). Single-column indexes: `received_at`, `event_type`,
  `packet_hash`, `channel_idx`, `source_pubkey_prefix`, `observer_node_id`.
  Composite indexes to serve the common "filter then sort by newest" pattern
  without a full scan + filesort: `(event_type, received_at)`,
  `(channel_idx, received_at)`, `(source_pubkey_prefix, received_at)`. See TR-17
  for the write-cost trade-off.
- **TR-2**: Alembic migration to create the `raw_packets` table, datestamped per
  convention (`alembic/versions/2026XXXX_XXXX_add_raw_packets.py`).
- **TR-3**: New handler `src/meshcore_hub/collector/handlers/raw_packet.py`
  exposing `store_raw_packet(...)`. It performs the find-or-create observer node
  pattern used by `handle_event_log` (`handlers/event_log.py:34-50`) and inserts a
  `RawPacket` row. It does not dedup.
- **TR-4**: Capture hook in `Subscriber._handle_mqtt_message`
  (`subscriber.py:189`), guarded by `self._raw_packet_capture_enabled` (a cheap
  boolean short-circuit when disabled — note it saves the insert, not the decode,
  which normalization performs regardless). When capture is enabled and the parsed
  feed is `packets`, call
  `store_raw_packet` with the raw payload, the decoder output already produced by
  the normalizer, the resolved `event_type`, and the observer public key. To avoid
  decoding twice, `_normalize_letsmesh_event` is refactored to also return (or the
  subscriber to reuse) the `decoded_packet` and `event_type`; capture uses that
  single decode. Capture failures are logged and never block event dispatch.
- **TR-5**: Channel index and source identity are derived at capture time:
  `channel_idx = int(channelHash, 16)` from
  `_extract_letsmesh_decoder_channel_hash`; `source_pubkey_prefix` from the
  decoder `sourceHash` / `senderPublicKey` via the existing
  `_normalize_pubkey_prefix` helper.
- **TR-6**: `RAW_PACKET_RETENTION_DAYS` config field added to `CollectorSettings`
  in `config.py` (alongside `data_retention_*` at `config.py:118`), defaulting to
  the value of `data_retention_days`. Threaded through `create_subscriber` /
  `run_collector` like the other cleanup params.
- **TR-6a**: `raw_packet_capture_enabled` (`RAW_PACKET_CAPTURE_ENABLED`) bool field
  added to `CollectorSettings`, default `false`, following the
  `data_retention_enabled` / `node_cleanup_enabled` convention. Threaded through
  `create_subscriber` / `run_collector` to `Subscriber.__init__` and stored as
  `self._raw_packet_capture_enabled` for the TR-4 guard. The collector logs the
  capture state at startup. Compose wires it on the **collector** service as
  `RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS:-false}` (in `docker-compose.yml`
  and any prod/traefik overrides); `FEATURE_PACKETS=${FEATURE_PACKETS:-false}`
  stays on the web service. Both env vars added to `.env.example`.
- **TR-7**: `collector/cleanup.py` gains a `raw_packets_deleted` stat and a cleanup
  step for `RawPacket`. Because `_cleanup_table` (`cleanup.py:185`) deletes by
  `created_at < cutoff` with a single retention value, add support for a per-table
  retention override (or a dedicated call) so `raw_packets` can use
  `RAW_PACKET_RETENTION_DAYS` independently of `DATA_RETENTION_DAYS`. The override
  falls back to `DATA_RETENTION_DAYS` when `RAW_PACKET_RETENTION_DAYS` is unset.
  Add `RawPacket.observer_node_id` to the observer union in
  `_observer_node_id_union()` (`cleanup.py:124`) so a node that appears only as a
  raw-packet observer still counts as an observer, and `recompute_observer_flags`
  does not clear its `is_observer` flag while it has live raw packets.
- **TR-8**: Pydantic schemas `RawPacketRead` / `RawPacketList` in
  `src/meshcore_hub/common/schemas/` (mirroring `messages.py`
  `AdvertisementRead`/`AdvertisementList`). `RawPacketRead` includes a
  `redacted: bool` field.
- **TR-9**: New route module `src/meshcore_hub/api/routes/raw_packets.py`,
  registered in `api/routes/__init__.py` with `prefix="/packets"`, `tags=["Packets"]`.
  Uses `RequireRead`, `DbSession`, and `@cached("packets",
  key_builder=_packets_key_builder)`. `_packets_key_builder` includes the resolved
  role (`resolve_user_role(request) or "anonymous"`) in the cache key — exactly
  like `messages.py:30` — so role-redacted responses are **never** served across
  roles. TTL uses the default `redis_cache_ttl` setting (`REDIS_CACHE_TTL`, default
  30s); no dedicated TTL var. `VALID_PACKET_SORT_COLUMNS =
  {"time", "event_type", "packet_type", "snr", "path_len"}`, default `time`/`desc`.
  Observer hydration follows the `aliased(Node)` + `selectinload(Node.tags)` pattern
  in `advertisements.py`.
- **TR-10**: The route applies redaction (FR-8) after fetching rows: compute the
  visible channel-index set once via `get_visible_channel_indices`, then for each
  channel-message row above the level, null the sensitive fields and set
  `redacted=true`. The SQL query is **not** pre-filtered by visibility (rows are
  returned but redacted), so pagination counts are stable across roles.
- **TR-11**: Web proxy access in `web/app.py` `_build_endpoint_access()`:
  `"v1/packets": { "GET": _OPEN }` (read gated only by `RequireRead` /
  channel-visibility redaction, consistent with `v1/messages` and
  `v1/advertisements`).
- **TR-12**: `FEATURE_PACKETS` feature flag in `WebSettings` (`config.py:397`),
  **default `False`**, registered in the `features` property (`config.py:428`) as
  `"packets": self.feature_packets` (no OIDC gate).
- **TR-13**: New SPA page module
  `src/meshcore_hub/web/static/js/spa/pages/packets.js` (lit-html), modelled on
  `pages/advertisements.js`, including its **responsive layout**: a `hidden
  lg:block` zebra `<table>` with `sortableTableHeader` on desktop and a
  `lg:hidden` stacked-card list with `mobileSortSelect` on mobile. Wire into
  `app.js`: lazy import entry, route
  `router.addRoute('/packets', pageHandler(pages.packets))` guarded by
  `features.packets`, dynamic nav item (`items.push`), and page title
  (`updatePageTitle`). Renders the `redacted` lock badge.
- **TR-13a**: Add the Packets entry to **all three nav surfaces**, each guarded by
  `features.packets` and inserted immediately **after the Messages entry** (before
  Map): the static `spa.html` sidebar/mobile `<li>` (`{% if features.packets %}`),
  the dynamic `app.js` nav (`items.push`), and the `home.js` hero card grid
  (`renderNavCard`).
- **TR-13b**: Correct the `home.js` hero-card order to match the sidebar/dynamic
  nav: it currently renders **Members before Map**; reorder to **Map before
  Members** so every surface follows the canonical order `Dashboard → Nodes →
  Advertisements → Channels → Messages → Packets → Map → Members`. Add a packets
  icon function to `icons.js` (imported by `app.js`, `home.js`, and `packets.js`).
  Add `--color-packets` (light + dark blocks), a `.nav-icon-packets` rule, and the
  `.navbar .menu li:has(.nav-icon-packets)` accent in `app.css`.
- **TR-14**: i18n keys for packets UI strings (including `entities.packets`,
  `entities.packet`, filter labels, and the redacted badge) added to **both**
  locale files — `en.json` and `nl.json` — and documented per the existing i18n
  docs.
- **TR-15**: `node build.js` rebuild of the SPA bundle after frontend changes.
- **TR-16**: Documentation updates:
  - `AGENTS.md` — new model, API route, `FEATURE_PACKETS`,
    `RAW_PACKET_RETENTION_DAYS`.
  - `SCHEMAS.md` — the `raw_packets` table and the `RawPacketRead` shape.
  - `.env.example` — add `RAW_PACKET_RETENTION_DAYS` and
    `RAW_PACKET_CAPTURE_ENABLED` near `DATA_RETENTION_DAYS` (commented, noting the
    retention default = `DATA_RETENTION_DAYS` and capture default = `false`), and
    `# FEATURE_PACKETS=false` in the feature-flags block, with a comment that
    Compose derives `RAW_PACKET_CAPTURE_ENABLED` from `FEATURE_PACKETS`.
  - `docker-compose.yml` (+ prod/traefik overrides) — `RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS:-false}`
    on the collector service; `FEATURE_PACKETS=${FEATURE_PACKETS:-false}` on the
    web service.
  - `docs/upgrading.md` — add a new **`## v0.13.0`** section at the top (above
    `v0.12.0`) with the upgrade steps (see TR-18).
  - `docs/letsmesh.md` — already covered in Phase 6.
- **TR-17**: **Performance / indexing.** The `raw_packets` table is the
  highest-volume table in the system (one row per packet per observer), so:
  - The composite indexes in TR-1 cover the dominant query shapes (filter by
    `event_type` / `channel_idx` / `source_pubkey_prefix`, sorted by
    `received_at DESC`). Do **not** add further composite indexes speculatively —
    each one is paid on every insert in the hot ingest path.
  - `search` is an unanchored `ilike '%term%'` over `raw_hex` / `packet_hash` and
    **cannot use an index** (full scan). The route should require it to combine
    with a narrowing filter (a `since` default window) so substring search runs
    against a bounded row set; document this limitation. Hash lookups should use a
    prefix (`ilike 'abc%'`) where possible so the `packet_hash` index applies.
  - Pagination uses an exact `COUNT(*)` over the filtered subquery (matching the
    other list routes); on a large table this is the most expensive part of the
    request. Accept it for parity now; note approximate/capped counts as a possible
    follow-up if it becomes a hotspot.
  - **Write amplification:** capture adds one `INSERT` per packet to the ingest
    path. SQLite is single-writer, so this competes with the structured handlers'
    writes already happening per packet. The capture handler must keep its
    transaction minimal (single insert + observer upsert, no extra reads) and must
    not hold the session longer than needed. The separate (and typically shorter)
    `RAW_PACKET_RETENTION_DAYS` is the primary mechanism keeping the table — and
    its index size — bounded.
- **TR-18**: `docs/upgrading.md` **v0.13.0** section content:
  - Run `meshcore-hub db upgrade` to create the `raw_packets` table.
  - New optional env vars, all safe to omit: `FEATURE_PACKETS` (defaults to
    `false` — Packets page and nav hidden until enabled), `RAW_PACKET_CAPTURE_ENABLED`
    (collector capture; Compose derives it from `FEATURE_PACKETS`, default `false`),
    and `RAW_PACKET_RETENTION_DAYS` (defaults to `DATA_RETENTION_DAYS`).
  - Explain the capture↔page split: setting `FEATURE_PACKETS=true` enables both
    capture and the page via the Compose wiring; advanced operators can set the two
    independently. No backfill — only packets captured after enabling appear.
  - Note the `raw_packets` table grows fastest of all; recommend tuning
    `RAW_PACKET_RETENTION_DAYS` for busy meshes / constrained storage, and that
    disabling capture lets it drain via retention.
  - Note Redis caching of `/packets` is role-aware and honours the existing
    `REDIS_CACHE_TTL`.

## Implementation Plan

### Phase 1: Model & Migration

- Create `src/meshcore_hub/common/models/raw_packet.py` with the fields in FR-1 /
  TR-1, following the `Advertisement` model.
- Export `RawPacket` from `models/__init__.py`.
- Generate the Alembic migration for the `raw_packets` table with all indexes.
- Unit tests for the model (column presence, defaults, indexes).

### Phase 2: Capture at Ingest

- Add `store_raw_packet(...)` in
  `src/meshcore_hub/collector/handlers/raw_packet.py` (find-or-create observer
  node, derive `channel_idx` and `source_pubkey_prefix`, insert one row, no dedup).
- Refactor `_normalize_letsmesh_event` / `_handle_mqtt_message` so the single
  decode performed during normalization is reused for capture (return or expose
  `decoded_packet` + resolved `event_type`).
- Add `raw_packet_capture_enabled` to `CollectorSettings`, thread it to
  `Subscriber` as `self._raw_packet_capture_enabled`, and guard the capture hook
  on it (log the state at startup).
- Call `store_raw_packet` for the `packets` feed only (when capture is enabled),
  before/independent of structured dispatch. Wrap in try/except so capture never
  blocks event handling.
- Tests: capture writes one row per packet; one row per observer for the same
  hash; `channel_idx` / `source_pubkey_prefix` derivation; status/internal feeds
  produce no raw rows; **capture disabled writes no rows while structured handlers
  still run**.

### Phase 3: Retention & Config

- Add `RAW_PACKET_RETENTION_DAYS` to `CollectorSettings`, defaulting to
  `data_retention_days`.
- Thread the value through `create_subscriber` / `run_collector` and the cleanup
  scheduler.
- Extend `cleanup.py` with a `raw_packets_deleted` stat and a `RawPacket` cleanup
  step using the dedicated retention value (per-table retention override on
  `_cleanup_table`, or a dedicated call).
- Add `RawPacket.observer_node_id` to `_observer_node_id_union()` so raw-packet-only
  observers retain their `is_observer` flag in `recompute_observer_flags`.
- Tests: raw packets older than `RAW_PACKET_RETENTION_DAYS` are deleted; default
  falls back to the global retention value; stat is reported; a node observing
  only raw packets keeps `is_observer=true` until those packets are pruned.

### Phase 4: Schemas & API

- Add `RawPacketRead` / `RawPacketList` schemas (with `redacted: bool`).
- Create `api/routes/raw_packets.py`:
  - `GET /packets` with all filters in FR-6, sort whitelist, pagination, observer
    hydration, and `@cached("packets", key_builder=_packets_key_builder)` — the
    key builder folds the resolved role into the cache key (TR-9) so redacted
    responses don't leak across roles; default TTL.
  - `GET /packets/{id}`.
  - Redaction pass (FR-8) using `get_visible_channel_indices`; `raw_hex` always
    present for non-redacted rows (FR-9).
- Register the router in `api/routes/__init__.py` (`prefix="/packets"`).
- Add `"v1/packets": { "GET": _OPEN }` to `_build_endpoint_access()`.
- Tests: each filter; sort/pagination; redaction for a low role viewing a
  member-channel packet (`redacted=true`, null `raw_hex`/`decoded`); non-channel
  packets never redacted; Public (17) always visible.

### Phase 5: Web Packets Page

- Add `FEATURE_PACKETS` to `WebSettings` (default `False`) and the `features` map.
- Create `pages/packets.js` (lit-html) modelled on `advertisements.js`, with the
  **desktop zebra table (`hidden lg:block`) + mobile stacked cards (`lg:hidden`)**
  responsive split using `sortableTableHeader` / `mobileSortSelect`: search box,
  event-type and channel filters, observer multi-select, route-type toggle,
  time-range picker, collapsible advanced filters (`packet_type`, SNR range,
  path-len range, `decryptable`, `redacted`), pagination, and a `redacted` lock
  badge.
- Wire `app.js`: lazy import, route guarded by `features.packets`, page title,
  i18n keys; add a packets icon function in `icons.js`.
- Add the Packets nav entry after Messages on **all three surfaces** (guarded by
  `features.packets`): `spa.html` sidebar/mobile `<li>`, `app.js` dynamic nav, and
  the `home.js` hero card grid (`renderNavCard`).
- Reorder the `home.js` hero cards so **Map precedes Members**, matching the
  sidebar/dynamic nav (TR-13b).
- Add `--color-packets` (light + dark), `.nav-icon-packets`, and the navbar
  `:has(.nav-icon-packets)` accent in `app.css`.
- Add i18n strings to `en.json` (incl. `entities.packets`, `entities.packet`) and
  locale stubs.
- `node build.js` to rebuild the bundle.
- Tests in the web test suite (nav/route hidden when the flag is off, list render,
  redacted badge).

### Phase 6: Docs

- Update `AGENTS.md` (model, route, `FEATURE_PACKETS`, `RAW_PACKET_RETENTION_DAYS`).
- Update `SCHEMAS.md` with the `raw_packets` table and `RawPacketRead`.
- Update `.env.example`: add `RAW_PACKET_RETENTION_DAYS` (commented, near
  `DATA_RETENTION_DAYS`, noting the `DATA_RETENTION_DAYS` default) and
  `# FEATURE_PACKETS=false` in the feature-flags block.
- Add a new `## v0.13.0` section to `docs/upgrading.md` (above `v0.12.0`) with the
  TR-18 content: `db upgrade`, the two new optional env vars and their defaults,
  the no-backfill / table-growth note, and the role-aware cache note.
- Update `docs/letsmesh.md` to note raw-packet capture is `packets`-feed only and
  that channel-restricted packets are returned metadata-only/redacted.
- Confirm `entities.packets` / `entities.packet` and filter labels exist in both
  `en.json` and `nl.json`.

## Open Decisions (Resolved)

- **Retention**: separate `RAW_PACKET_RETENTION_DAYS`, default = global
  `DATA_RETENTION_DAYS`. (Resolved.)
- **Feeds**: `packets` only; `status`/`internal` excluded (no `raw` hex).
  (Resolved.)
- **Dedup**: none — one row per observer reception. (Resolved.)
- **Feature flag**: `FEATURE_PACKETS` defaults to **off**. (Resolved.)
- **Restricted channel packets**: shown as metadata-only with payload redacted
  (`redacted=true`, null `raw_hex`/`decoded`), not hidden. (Resolved.)
- **`raw_hex` exposure**: always returned for non-redacted, visible packets.
  (Resolved.)

## Review

**Status**: Draft — pending review.

## References

- `src/meshcore_hub/collector/subscriber.py:189` — `_handle_mqtt_message` (capture
  hook site); `:512` — feed subscriptions
- `src/meshcore_hub/collector/letsmesh_normalizer.py:23` —
  `_normalize_letsmesh_event` (single-decode + classification to reuse)
- `src/meshcore_hub/collector/letsmesh_decoder.py:219` — `decode_payload`;
  `:174` — channel hash computation
- `src/meshcore_hub/collector/handlers/event_log.py:34-50` — find-or-create
  observer node pattern to follow in the raw-packet handler
- `src/meshcore_hub/collector/handlers/__init__.py:26-37` — handler registration /
  structured vs informational split
- `src/meshcore_hub/common/models/advertisement.py` — model pattern (UUIDMixin,
  TimestampMixin, indexes)
- `src/meshcore_hub/collector/cleanup.py:54,185` — `cleanup_old_data` /
  `_cleanup_table` (retention to extend for per-table override)
- `src/meshcore_hub/common/config.py:118-135` — data-retention settings; `:397-448`
  — feature flags and the `features` map
- `src/meshcore_hub/api/routes/advertisements.py` — list/detail route pattern
  (aliased node joins, observer hydration, sort whitelist, pagination, `@cached`)
- `src/meshcore_hub/api/routes/messages.py:53,83-106` — `channel_idx` filter and
  channel-visibility filtering to mirror
- `src/meshcore_hub/api/channel_visibility.py` — `resolve_user_role`,
  `get_visible_channel_indices`, `get_all_known_channel_indices`
- `src/meshcore_hub/api/auth.py:52,145` — `require_read` / `RequireRead`
- `src/meshcore_hub/web/app.py:68-129` — `_build_endpoint_access()` proxy access map
- `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` — SPA list page to
  model `packets.js` on
- `src/meshcore_hub/web/static/js/spa/app.js:21,64-99,161` — lazy import map, route
  registration, nav, page titles
