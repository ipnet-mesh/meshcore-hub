# Channel Model: Database-Backed Decrypt Keys with Permission-Based Visibility

## Summary

Add a `Channel` database model to replace the `COLLECTOR_CHANNEL_KEYS` environment variable entirely. Channels store their name, secret key, computed channel hash, and a **visibility/permission level** (`public`, `member`, `operator`, `admin`). The collector loads keys from the database at startup and periodically refreshes them without restart. The web dashboard and API enforce permission-based visibility: "public" channels are visible to everyone (including logged-out users), "member" channels only to authenticated members, and so on.

A new **Channels page** in the web dashboard presents channels as cards (desktop and mobile), each showing a **QR code** for easy joining (`meshcore://channel/add?name=...&key=...`). The page is always visible regardless of OIDC status. When OIDC is enabled, admin users see inline channel management (add/edit/delete) and non-admin users see read-only cards filtered by their role. When OIDC is disabled, all channels are `public` by default, no admin UI is shown, and channels can only be configured via the seed mechanism.

## Background & Motivation

### Current State

Channel decryption keys flow through the system as follows:

1. `COLLECTOR_CHANNEL_KEYS` env var (comma/space-separated hex strings, e.g. `"MyChannel=ABC123...,Other=DEF456..."`)
2. Parsed by `CollectorSettings.collector_channel_keys_list` into a `list[str]` (`config.py:185-193`)
3. Passed to `create_subscriber(channel_keys=...)` and then `LetsMeshPacketDecoder(channel_keys=...)` (`subscriber.py:88-90`)
4. The decoder builds a `MeshCoreKeyStore` with `add_channel_secrets()` and uses it to decrypt GroupText (type 5) packets via the `meshcoredecoder` library (`letsmesh_decoder.py:63-68`)
5. Built-in keys (`Public`, `test`) are always included via `BUILTIN_CHANNEL_KEYS` (`letsmesh_decoder.py:32-35`)
6. The web app independently builds channel labels via `_build_channel_labels()` in `web/app.py:171-185`, reading the same env var to create a decoder instance just for label resolution

### Problems

- **Restart required**: Adding or changing a channel key requires editing `.env` and restarting the collector process.
- **No permission model**: All channels are visible to all users. There is no way to restrict sensitive channels (e.g., operator-only coordination channels) from public view.
- **No API/CLI management**: There is no way to add/remove channel keys at runtime.
- **No audit trail**: Keys exist only in config; there is no record of when a key was added or by whom.
- **Duplicated decoder construction**: The web app builds its own `LetsMeshPacketDecoder` just to resolve channel labels (`web/app.py:179-182`). With a database source, both collector and web can query the same `channels` table.
- **No user-facing channel info**: Users cannot discover available channels, see their names, or get QR codes to join them from their devices.

### Why Now

The collector already queries the database for cleanup and event persistence. The web app already has a QR code library (`qrcodejs`) loaded globally and used on the node detail page (`node-detail.js:361-374`) with the `meshcore://` URL scheme. The API proxy already has a role-based access control framework (`_build_endpoint_access` / `check_api_access` in `web/app.py:68-161`). Making channels a first-class database entity unblocks permission-based message filtering, a channels management page, and QR code distribution.

## Goals

- Introduce a `Channel` SQLAlchemy model with name, key, channel hash, **visibility/permission level**, and enabled flag
- Replace `COLLECTOR_CHANNEL_KEYS` env var entirely with database-backed channels
- Have the collector load keys from the `channels` table at startup and refresh periodically (no restart)
- Enforce permission-based visibility in messages view and dashboard: only show messages on channels the user has access to
- Provide a **Channels page** (`/channels`) that is always visible (with or without OIDC)
- When OIDC is enabled: show admin-only inline channel management; filter channel visibility by user role
- When OIDC is disabled: show all (public-only) channels read-only; channels configured only via seed
- Provide CLI commands and API endpoints for channel CRUD
- Support seeding channels from YAML (visibility defaults to `public`; no visibility field in seed data)
- Remove `COLLECTOR_CHANNEL_KEYS` and related config plumbing

## Non-Goals

- Changing the `meshcoredecoder` library or the decryption logic itself
- Storing node-specific private keys (this is about channel shared secrets)
- Encrypting channel keys at rest in the database
- End-to-end encryption or per-user channel access control beyond the role-based visibility model
- Filtering messages at the collector level (the collector decrypts all channels; filtering is done at the API/web layer)
- Admin UI for channels when OIDC is disabled (seed-only configuration)

## Requirements

### Functional Requirements

- **FR-1**: A `Channel` database model with fields:
  - `id` (UUID primary key)
  - `name` (String(100), unique, non-empty)
  - `key_hex` (String(64), uppercase hex, unique — supports both AES-128 and AES-256 keys)
  - `channel_hash` (String(2), computed: first byte of SHA-256 of `key_hex`)
  - `visibility` (Enum: `public`, `member`, `operator`, `admin`; default `public`)
  - `enabled` (Boolean, default `true`)
  - `created_at`, `updated_at` (timestamps)
- **FR-2**: On startup, the collector queries all `Channel` rows where `enabled=true`, merges them with the hardcoded built-in keys (`Public`, `test` — both always available to the decoder), and builds the `MeshCoreKeyStore`. The `Public` built-in key always has `visibility=public` and cannot be overridden. The `test` built-in key is always loaded into the decoder for decryption, **but** test channel messages are **discarded by the normalizer by default** — they are only stored when a `test` channel row exists in the DB with `enabled=true` (added by an admin via CLI/API/seed). This replaces the `COLLECTOR_INCLUDE_TEST_CHANNEL` env var.
- **FR-3**: The collector periodically refreshes its key store from the database (configurable interval, default 5 minutes).
- **FR-4**: **Permission-based message visibility**: The API `/messages` endpoint accepts the user's role context (via OIDC X-User-Roles header from the web proxy, or API key auth for direct calls) and filters channel messages so that:
  - No OIDC / OIDC disabled: all channel messages visible (all channels are `public` in this mode)
  - Logged-out (OIDC enabled): only messages on `public` channels
  - `member` role: messages on `public` + `member` channels
  - `operator` role: messages on `public` + `member` + `operator` channels
  - `admin` role: all messages (all channels)
  - Direct messages (non-channel) remain governed by existing read access rules.
- **FR-4b**: **Dashboard channel activity filtering**: The `/dashboard/stats` and `/dashboard/message-activity` endpoints filter channel-related data by the same role-based visibility rules as `/messages`. Channel message counts, channel-specific message lists, and activity charts only include data from channels visible to the requesting user.
- **FR-5**: The dashboard and messages page channel filter dropdowns only show channels visible to the current user's role. When OIDC is disabled, all channels appear.
- **FR-6**: **Channels page** (`/channels`) -- always visible regardless of OIDC status:
  - **OIDC disabled**: Read-only card grid showing all channels (all `public`). No add/edit/delete UI. No visibility badges.
  - **OIDC enabled, no auth**: Read-only cards showing only `public` channels.
  - **OIDC enabled, logged in**: Read-only cards showing channels up to the user's role level, with visibility badges.
  - **OIDC enabled, admin**: Full management -- "Add Channel" button, edit/delete buttons per card, visibility select in forms.
  - Card layout (responsive, works on desktop and mobile)
  - Each card shows: channel name, channel hash, visibility badge (if OIDC enabled), QR code, enabled status
  - QR code format: `meshcore://channel/add?name=<encoded_name>&key=<key_hex>`
  - Card shows masked key (first/last 4 chars) with a reveal toggle for admins
- **FR-7**: **Admin inline channel management** (OIDC enabled + admin role only): Add/edit/delete channels via modal dialogs (following the tag editor pattern in `node-detail.js`). Only the `admin` role can perform these operations. This is not available when OIDC is disabled.
- **FR-8**: CLI commands: `meshcore-hub collector channel list`, `channel add --name X --key HEX --visibility public`, `channel remove --name X`, `channel enable/disable --name X`.
- **FR-9**: API endpoints:
  - `GET /channels` -- list channels; filtered by user role visibility when OIDC enabled; returns all public channels when OIDC disabled
  - `POST /channels` -- create (admin only, OIDC required)
  - `PUT /channels/{id}` -- update (admin only, OIDC required)
  - `DELETE /channels/{id}` -- delete (admin only, OIDC required)
  - The web proxy (`_build_endpoint_access`) guards mutations behind the `admin` role; `GET` is `_OPEN`
- **FR-10**: Channel seeding from `${SEED_HOME}/channels.yaml` via `meshcore-hub collector seed`. Seed format does not include a `visibility` field -- seeded channels always get `visibility=public`. This is the only way to configure channels when OIDC is disabled.
- **FR-11**: `COLLECTOR_CHANNEL_KEYS` env var and related config (`collector_channel_keys`, `collector_channel_keys_list`) are removed. Migration guide documents the removal.
- **FR-12**: The web app's `_build_channel_labels()` in `web/app.py` is updated to query the `channels` table from the shared database instead of re-parsing the env var.
- **FR-13**: The `FEATURE_CHANNELS` feature flag controls page visibility. It does not depend on OIDC being enabled (unlike `feature_members` which requires OIDC). The page is available to all users when the flag is `true`.

### Technical Requirements

- **TR-1**: New model `Channel` in `src/meshcore_hub/common/models/channel.py`, exported from `models/__init__.py`.
- **TR-2**: Alembic migration to create the `channels` table.
- **TR-3**: Pydantic schemas for channel CRUD in `src/meshcore_hub/common/schemas/channels.py`.
- **TR-4**: `LetsMeshPacketDecoder.reload_keys(channel_keys: list[str])` method that rebuilds `MeshCoreKeyStore` and `_channel_names_by_hash` without discarding the decode cache. Thread-safe via atomic reference swap.
- **TR-5**: `Subscriber` gains a `_start_channel_refresh_scheduler()` method following the cleanup scheduler pattern (`subscriber.py:245-357`). Uses `DatabaseManager.async_session()` to query channels.
- **TR-6**: Message filtering at the API layer: the `/messages` route resolves the user's highest role, queries `channels` table for visible channel hashes, then filters channel messages. Filtering logic:
  - OIDC disabled (no auth roles): no filtering — all channels treated as `public`.
  - OIDC enabled: query DB for all channel hashes up to the user's visibility level. The query filter is: `(message_type != 'channel') OR (channel_idx IN (visible_hashes_as_ints)) OR (channel_idx NOT IN (all_known_hashes_as_ints))`. This shows direct messages always, channels at/below the user's visibility level, and unknown channels (treated as `public`). No pre-filtering means channels visible in the filter dropdown may differ from visible messages, but the `<10 channel count makes this negligible.
- **TR-7**: New SPA page module `src/meshcore_hub/web/static/js/spa/pages/channels.js` with card layout, QR code generation (reusing the `QRCode` library from `qrcodejs`), and admin modal editors.
- **TR-8**: Navigation placement: **All navigation surfaces** use the order `Messages → Channels → Members → Map`:
  - `spa.html` desktop sidebar and mobile menu: insert Channels `<li>` between Messages and Members
  - `app.js` dynamic nav: insert Channels `if (features.channels)` block between Messages and Members blocks
  - `home.js` hero card grid: insert Channels `renderNavCard()` between Messages and Members cards
  - Add CSS custom property `--color-channels` in `app.css` for hero card accent color
- **TR-9**: `FEATURE_CHANNELS` feature flag in `WebSettings` (default `true`), registered in the `features` property. Unlike `feature_members`, it does not gate on `oidc_enabled`.
- **TR-10**: The `channel_labels` config passed to the web frontend via `/config` endpoint stays in its current format (`{str(channel_idx): label}`). It is built from the `channels` DB table instead of parsing `COLLECTOR_CHANNEL_KEYS`, using a synchronous SQLAlchemy engine (SQLite allows concurrent reads). The existing `getChannelLabelsMap()` function in `components.js` continues to work unchanged. Channel visibility is fetched separately by the Channels page via `/api/v1/channels` — it does not go through the `/config` endpoint.
- **TR-11**: Remove `COLLECTOR_CHANNEL_KEYS` and `COLLECTOR_INCLUDE_TEST_CHANNEL` from `CollectorSettings`, remove `collector_channel_keys_list` property, remove `_parse_decoder_key_entries()` from `web/app.py`.
- **TR-12**: i18n keys for channel-related UI strings added to `en.json` and documented in `docs/i18n.md`.
- **TR-13**: Web proxy access mapping in `_build_endpoint_access()` updated:
  - `"v1/channels": { "GET": _OPEN }` -- anyone can list
  - `"v1/channels/": { "POST": frozenset({role_admin}), "PUT": frozenset({role_admin}), "DELETE": frozenset({role_admin}) }` -- admin-only mutations
- **TR-14**: `CHANNEL_REFRESH_INTERVAL_SECONDS` env var added to `CollectorSettings` (default `300`). Not in `WebSettings`.

## Implementation Plan

### Phase 1: Channel Model & Migration

- Create `src/meshcore_hub/common/models/channel.py`:
  ```python
  class ChannelVisibility(str, Enum):
      PUBLIC = "public"
      MEMBER = "member"
      OPERATOR = "operator"
      ADMIN = "admin"

  class Channel(Base, UUIDMixin, TimestampMixin):
      __tablename__ = "channels"
      name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
      key_hex: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
      channel_hash: Mapped[str] = mapped_column(String(2), nullable=False)
      visibility: Mapped[str] = mapped_column(String(20), default="public")
      enabled: Mapped[bool] = mapped_column(Boolean, default=True)
  ```
- Export from `models/__init__.py`
- Generate Alembic migration: `meshcore-hub db revision --autogenerate -m "add channels table"`
- Unit tests for the model

### Phase 2: Decoder Reload Support

- Add `reload_keys(channel_keys: list[str])` to `LetsMeshPacketDecoder`
- Normalize new key list, rebuild `MeshCoreKeyStore`, update `_channel_names_by_hash`
- Preserve decode cache across reloads
- **Thread safety**: Add a `threading.Lock` (`_state_lock`) to guard access to `_key_store` and `_channel_names_by_hash`. The MQTT message callback thread reads these during decode; the refresh thread writes during reload. Lock is only held during the atomic swap (not during key normalization/KeyStore construction).
- Unit tests for reload behavior

### Phase 3: Collector DB Key Loading & Refresh

- On startup (`Subscriber.__init__` or `start()`), query `Channel` table for `enabled=true` rows via `self.db.session_scope()`
- Merge DB channels with the hardcoded built-in keys (`Public`, `test` — both always available to the decoder). The `test` key is always loaded into the decoder but test messages are discarded unless a DB row exists (see FR-2).
- The `_include_test_channel` flag moves from env var to a DB query: `self.db.async_session()->query(Channel).filter(name="test", enabled=True).first() is not None`. Evaluated once at startup and on refresh.
- Add `_start_channel_refresh_scheduler()` to `Subscriber`, following the cleanup scheduler pattern (`subscriber.py:245-357`)
- Add `channel_refresh_interval_seconds` field to `CollectorSettings` (env var `CHANNEL_REFRESH_INTERVAL_SECONDS`, default `300`)
- Pass interval to `Subscriber.__init__` alongside other scheduler params (cleanup_enabled, cleanup_retention_days, etc.)
- Remove `channel_keys` parameter from `Subscriber.__init__`, `create_subscriber()`, and `run_collector()`
- Remove `COLLECTOR_CHANNEL_KEYS` from `CollectorSettings` and related parsing
- Integration tests

### Phase 4: API Endpoints & Message Filtering

- Create `src/meshcore_hub/common/schemas/channels.py`: `ChannelCreate`, `ChannelRead`, `ChannelUpdate`, `ChannelList`
- Create `src/meshcore_hub/api/routes/channels.py`:
  - `GET /channels` -- list channels, filtered by user role. When no OIDC roles are present (OIDC disabled or not logged in), returns only `public` channels
  - `POST /channels` -- create (admin only, uses `RequireAdmin` dependency on API side)
  - `PUT /channels/{id}` -- update (admin only)
  - `DELETE /channels/{id}` -- delete (admin only)
- Add role-aware message filtering to `GET /messages`:
  - Resolve user's highest role from auth context (X-User-Roles header or API key)
  - When no roles available (OIDC disabled): no filtering (all channels visible)
  - When OIDC enabled: query visible channel hashes from `channels` table based on role hierarchy (role → visibility levels up to that role)
  - Channel hash to channel_idx conversion: `channel_idx = int(channel_hash, 16)` (both are 0-255)
  - Query filter: `(message_type != 'channel') OR (channel_idx IN (visible_idxs)) OR (channel_idx NOT IN (all_known_idxs))`
  - Unknown channel hashes (not in DB) are treated as `public` and pass through the third clause
- Add role-aware channel filtering to `GET /dashboard/stats` and `/dashboard/message-activity`:
  - Resolve user's highest role from auth context
  - Filter channel counts and channel activity lists by visible channels using the same visibility logic as `/messages`
  - When OIDC disabled: show all channels
- Update `_build_channel_labels()` in `web/app.py` to query DB using a synchronous SQLAlchemy engine against the shared SQLite database. This is safe because SQLite allows concurrent readers. The function is called once at startup; results are stored in `app.state.channel_labels`. The existing format (`{str(channel_idx): label}`) is preserved.
- Add entries to `_build_endpoint_access()`:
  - `"v1/channels": { "GET": _OPEN }`
  - `"v1/channels/": { "POST": frozenset({role_admin}), "PUT": frozenset({role_admin}), "DELETE": frozenset({role_admin}) }`
- Register router in `api/routes/__init__.py`
- Tests for all endpoints and filtering

### Phase 5: CLI Commands

- Add `channel` subgroup to collector CLI in `cli.py`
- `meshcore-hub collector channel list` -- name, masked key, hash, visibility, enabled
- `meshcore-hub collector channel add --name NAME --key HEX --visibility public`
- `meshcore-hub collector channel remove --name NAME`
- `meshcore-hub collector channel enable/disable --name NAME`
- Remove `channel_keys` and `include_test_channel` params from `_run_collector_service()`
- Tests for each command

### Phase 6: Web Dashboard -- Channels Page

- Create `src/meshcore_hub/web/static/js/spa/pages/channels.js`:
  - Fetch `/api/v1/channels` (API returns only channels the user can see)
  - Render responsive card grid (DaisyUI `card` component)
  - Each card: channel name, channel hash badge, visibility badge (OIDC only), QR code, masked key
  - QR code: `meshcore://channel/add?name=<encoded>&key=<hex>` using `QRCode` library
  - **OIDC disabled**: read-only cards, no visibility badges, no add/edit/delete controls
  - **OIDC enabled, admin**: "Add Channel" button, edit/delete buttons per card
  - **OIDC enabled, non-admin**: read-only cards filtered by role
  - Add/edit modal (following tag editor pattern from `node-detail.js`): name, key (hex), visibility select, enabled toggle -- only rendered when `hasRole('admin')`
  - Delete confirmation modal (following `tagDeleteModal` pattern)
  - Use `getConfig().oidc_enabled` to conditionally show/hide admin controls and visibility badges
- **Navigation ordering** -- Channels appears **after Messages and before Members** in all navigation surfaces:
  - `spa.html` desktop sidebar and mobile menu: insert Channels `<li>` between Messages and Members
  - `app.js` dynamic nav (`renderNavItems()`): insert Channels `if (features.channels !== false)` block between Messages and Members blocks
  - `home.js` hero card grid: insert Channels `renderNavCard()` between Messages and Members cards
  - Add CSS custom property `--color-channels` in `app.css` for hero card accent color
- **Icon**: Use the existing `iconChannel` SVG function from `icons.js` (hash/# icon, already defined at `icons.js:77-79`). Import it in `channels.js`, `home.js`, `app.js`, and use it inline in `spa.html` nav links.
- Register route in `app.js`: `router.addRoute('/channels', pageHandler(pages.channels))`
  - No OIDC dependency in route registration (unlike members which gates on `features.members`)
- Add `FEATURE_CHANNELS` feature flag to `WebSettings` -- does NOT gate on `oidc_enabled`:
  ```python
  feature_channels: bool = Field(default=True, description="Enable the /channels page")
  # In features property:
  "channels": self.feature_channels,  # no oidc_enabled guard
  ```
- Add page title handling in `updatePageTitle()` in `app.js`
- Add i18n keys to `en.json` (including `entities.channels`, `entities.channel`) and update `docs/i18n.md`
- Tests in `tests/test_web/`

### Phase 7: Seeding, Config Cleanup & Docs

- Add `channels.yaml` support to seed importer in `cli.py`
  - Shorthand format: `name: HEX` — value is a hex string, treated as the channel key
  - Expanded format: `name: { key: HEX, enabled: true }` — value is a dict
  - The parser distinguishes by type: `str` → shorthand (treat value as `key_hex`), `dict` → expanded (read `key` and optional `enabled` fields)
  - No `visibility` field in seed format — always defaults to `public`
  - This is the primary configuration path when OIDC is disabled
- Remove `COLLECTOR_CHANNEL_KEYS` and `COLLECTOR_INCLUDE_TEST_CHANNEL` from:
  - `CollectorSettings` in `config.py`
  - `collector_channel_keys_list` property
  - `_parse_decoder_key_entries()` in `web/app.py`
  - `_run_collector_service()` in `cli.py`
  - `Subscriber.__init__`, `create_subscriber()`, `run_collector()` signatures
  - `AGENTS.md` env var list
  - `.env.example` (lines 204 and 208)
- Update `docs/seeding.md` with channels.yaml documentation (emphasize: visibility always `public`, admin-only channels require OIDC + API/CLI)
- Update `docs/upgrading.md` with migration guide:
  - Run `meshcore-hub db upgrade`
  - Convert any `COLLECTOR_CHANNEL_KEYS` values to `channels.yaml` seed file or DB rows via CLI
  - Remove env var from `.env`
  - Note: existing seeded channels will be `public` visibility
- Update `AGENTS.md` with new model, page, feature flag, and API routes
- Update `SCHEMAS.md` if channel event schemas are affected

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-05-19

### Resolutions

- **Nav ordering**: All navigation surfaces use `Messages → Channels → Members → Map` (not `Messages → Channels → Map → Members`). Updated TR-8 and Phase 6.
- **`key_hex` column size**: Changed from `String(32)` to `String(64)` to support both AES-128 and AES-256 keys. Updated FR-1 and Phase 1 model.
- **Frontend config format**: `channel_labels` stays as `{str(idx): label}` — unchanged format. Channels page fetches visibility from `/api/v1/channels` directly. Updated TR-10.
- **`_build_channel_labels()` sync approach**: Uses a synchronous SQLAlchemy engine for a one-time startup query against the shared SQLite database (safe because SQLite allows concurrent readers). Updated Phase 4.
- **Dashboard channel filtering**: Yes, dashboard channel activity is filtered by role visibility (consistent with `/messages`). Added FR-4b and updated Phase 4.
- **Thread safety**: Specified `threading.Lock` (`_state_lock`) on decoder for atomic swap between MQTT callback and refresh threads. Updated Phase 2.
- **`CHANNEL_REFRESH_INTERVAL_SECONDS`**: Added as `CollectorSettings` field (not `WebSettings`). Added TR-14 and updated Phase 3.
- **Message filtering logic**: Changed from simple `IN (...)` to three-clause filter: direct messages always visible, known channels filtered by visibility, unknown channels treated as `public`. Updated TR-6 and Phase 4.
- **Seed format**: Parser distinguishes shorthand (`str` → key_hex) vs expanded (`dict` → read `key` and optional `enabled`). No `visibility` field. Clarified in Phase 7.

### Remaining Action Items

- **QR code URL format**: The `meshcore://channel/add?name=...&key=...` scheme is proposed by analogy with the existing contact QR. Confirm with MeshCore app devs whether this scheme is supported or planned. (Baked into plan as-is; QR codes work if/when app supports them.)
- **Test channel excluded by default**: `test` built-in key always loaded into decoder (for decryption), but normalizer discards test messages unless a `Channel` row with `name="test"` and `enabled=true` exists in DB. NOT created automatically — admin must explicitly add it. Replaces `COLLECTOR_INCLUDE_TEST_CHANNEL`. Updated FR-2 and Phase 3.
- **Existing test updates**: Tests that reference `channel_labels["17"] == "Public"` etc. must continue to pass. Since format is unchanged, they should, but verify during Phase 4.

## References

- `src/meshcore_hub/collector/letsmesh_decoder.py` -- decoder with static key init, `BUILTIN_CHANNEL_KEYS`, `channel_labels_by_index()`
- `src/meshcore_hub/collector/subscriber.py` -- subscriber with cleanup scheduler pattern (thread + async session) to follow
- `src/meshcore_hub/common/models/node_tag.py` -- model pattern (UUIDMixin, TimestampMixin)
- `src/meshcore_hub/common/config.py:141-193` -- current `COLLECTOR_CHANNEL_KEYS` config (to be removed)
- `src/meshcore_hub/web/app.py:68-161` -- `_build_endpoint_access()` and `check_api_access()` for proxy auth guards
- `src/meshcore_hub/web/app.py:164-185` -- `_build_channel_labels()` (to be updated to query DB)
- `src/meshcore_hub/web/static/js/spa/pages/node-detail.js:361-374` -- QR code pattern using `QRCode` library and `meshcore://` scheme
- `src/meshcore_hub/web/static/js/spa/pages/node-detail.js:25-71` -- modal dialog patterns for tag edit/delete
- `src/meshcore_hub/api/auth.py` -- auth dependencies (`RequireRead`, `RequireAdmin`, `require_operator_or_admin`)
- `src/meshcore_hub/web/static/js/spa/components.js` -- `hasRole()`, `getChannelLabelsMap()`, `resolveChannelLabel()`
