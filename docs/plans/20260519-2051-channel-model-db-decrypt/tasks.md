# Tasks: Channel Model — Database-Backed Decrypt Keys with Permission-Based Visibility

> Generated from `plan.md` on 2026-05-19

## 1. Database Schema & Migration

- [ ] 1.1 Create `Channel` SQLAlchemy model
  - [ ] 1.1.1 Define `ChannelVisibility` enum (`public`, `member`, `operator`, `admin`)
  - [ ] 1.1.2 Create `Channel` class in `src/meshcore_hub/common/models/channel.py` (fields: `id`, `name`, `key_hex`, `channel_hash`, `visibility`, `enabled`, `created_at`, `updated_at`)
  - [ ] 1.1.3 `key_hex` must be `String(64)` (supports AES-128 and AES-256 keys)
  - [ ] 1.1.4 `channel_hash` must be `String(2)` (first byte of SHA-256 of `key_hex`, uppercase hex)
  - [ ] 1.1.5 `name` must be `String(100)`, unique, non-nullable
  - [ ] 1.1.6 Export `Channel`, `ChannelVisibility` from `models/__init__.py`

- [ ] 1.2 Generate Alembic migration
  - [ ] 1.2.1 Run `meshcore-hub db revision --autogenerate -m "add channels table"`
  - [ ] 1.2.2 Review generated migration for correctness (unique constraints on `name` and `key_hex`)
  - [ ] 1.2.3 Test migration: `meshcore-hub db upgrade` and verify table creation

- [ ] 1.3 Create Pydantic schemas
  - [ ] 1.3.1 Create `src/meshcore_hub/common/schemas/channels.py` with `ChannelCreate`, `ChannelRead`, `ChannelUpdate`, `ChannelList`
  - [ ] 1.3.2 `ChannelCreate`: validate `name`, `key_hex` (uppercase hex, 32 or 64 chars), optional `visibility` (default `public`), optional `enabled` (default `true`)
  - [ ] 1.3.3 `ChannelRead`: include `id`, `name`, `channel_hash`, `visibility`, `enabled`, `created_at`, `updated_at`, but NOT `key_hex` (mask first/last 4 chars for read)
  - [ ] 1.3.4 `ChannelUpdate`: all fields optional except `name` immutable
  - [ ] 1.3.5 Add `masked_key` computed property on `ChannelRead` (e.g. `"ABCD...EF01"`)

- [ ] 1.4 Write unit tests for the model and schemas
  - [ ] 1.4.1 Test `Channel` model instantiation and defaults
  - [ ] 1.4.2 Test unique constraint enforcement on `name` and `key_hex`
  - [ ] 1.4.3 Test `ChannelCreate` schema validation (valid keys, invalid keys, name length)
  - [ ] 1.4.4 Test `ChannelRead.masked_key` formatting

## 2. Decoder Reload Support

- [ ] 2.1 Add `reload_keys()` method to `LetsMeshPacketDecoder`
  - [ ] 2.1.1 Add `threading.Lock` (`_state_lock`) to the decoder class
  - [ ] 2.1.2 Implement `reload_keys(channel_keys: list[str])` — normalize new keys, rebuild `MeshCoreKeyStore`, update `_channel_names_by_hash`
  - [ ] 2.1.3 Preserve the decode cache (`_decode_cache`) across reloads
  - [ ] 2.1.4 Use `_state_lock` for atomic swap of `_key_store` and `_channel_names_by_hash` (hold lock only during swap, not during key normalization/KeyStore construction)
  - [ ] 2.1.5 Update `channel_labels_by_index()` and `resolve_channel_name()` to use `_state_lock` when reading shared state

- [ ] 2.2 Write unit tests for reload behavior
  - [ ] 2.2.1 Test that reload with new keys enables decryption of messages on the new channel
  - [ ] 2.2.2 Test that decode cache persists across reloads
  - [ ] 2.2.3 Test thread safety: concurrent decode reads while reload is in progress (mock/threading test)

## 3. Collector DB Key Loading & Refresh

- [ ] 3.1 Update `Subscriber` to load keys from database on startup
  - [ ] 3.1.1 Query all `enabled=true` channels from DB via `self.db.session_scope()`
  - [ ] 3.1.2 Merge DB channels with hardcoded built-in keys (`Public`, `test` — always loaded into decoder)
  - [ ] 3.1.3 Move `_include_test_channel` from env var to DB query: check if `Channel(name="test", enabled=True)` row exists
  - [ ] 3.1.4 Pass merged key list to decoder (replacing old `channel_keys` constructor param)

- [ ] 3.2 Update `letsmesh_normalizer.py` test channel filter
  - [ ] 3.2.1 Replace env-var-based `_include_test_channel` check with DB lookup in the normalizer
  - [ ] 3.2.2 Test messages are always decrypted (key in decoder), but discarded by normalizer unless DB row exists

- [ ] 3.3 Add `_start_channel_refresh_scheduler()` to `Subscriber`
  - [ ] 3.3.1 Follow the cleanup scheduler pattern (`subscriber.py:245-357`): daemon thread + async session
  - [ ] 3.3.2 Query enabled channels from DB on each cycle
  - [ ] 3.3.3 Call `decoder.reload_keys()` with updated key list
  - [ ] 3.3.4 Handle graceful shutdown (stop event)

- [ ] 3.4 Add `CHANNEL_REFRESH_INTERVAL_SECONDS` to `CollectorSettings`
  - [ ] 3.4.1 Add field to `CollectorSettings` in `config.py` (default `300`, env var `CHANNEL_REFRESH_INTERVAL_SECONDS`)
  - [ ] 3.4.2 Pass interval to `Subscriber.__init__` alongside other scheduler params

- [ ] 3.5 Remove `channel_keys` from collector plumbing
  - [ ] 3.5.1 Remove `channel_keys` param from `Subscriber.__init__`, `create_subscriber()`, `run_collector()`
  - [ ] 3.5.2 Remove `COLLECTOR_CHANNEL_KEYS` from `CollectorSettings`
  - [ ] 3.5.3 Remove `collector_channel_keys_list` property from `CollectorSettings`
  - [ ] 3.5.4 Remove `COLLECTOR_INCLUDE_TEST_CHANNEL` from `CollectorSettings`

- [ ] 3.6 Write integration tests
  - [ ] 3.6.1 Test that collector loads keys from DB on startup
  - [ ] 3.6.2 Test that collector refreshes keys on schedule
  - [ ] 3.6.3 Test that test channel messages are discarded when no DB row exists
  - [ ] 3.6.4 Test that test channel messages are stored when DB row with `enabled=true` exists

## 4. API Endpoints & Message Filtering

- [ ] 4.1 Create API routes for channels
  - [ ] 4.1.1 Create `src/meshcore_hub/api/routes/channels.py`
  - [ ] 4.1.2 Implement `GET /channels` — list channels filtered by user role visibility; when no OIDC roles, return only `public` channels
  - [ ] 4.1.3 Implement `POST /channels` — create channel (admin only)
  - [ ] 4.1.4 Implement `PUT /channels/{id}` — update channel (admin only, `name` immutable)
  - [ ] 4.1.5 Implement `DELETE /channels/{id}` — delete channel (admin only)
  - [ ] 4.1.6 Register router in `api/routes/__init__.py`

- [ ] 4.2 Add role-aware message filtering to `GET /messages`
  - [ ] 4.2.1 Resolve user's highest role from auth context (X-User-Roles header or API key)
  - [ ] 4.2.2 When no roles available (OIDC disabled): no filtering (all channels treated as public)
  - [ ] 4.2.3 When OIDC enabled: query visible channel hashes from `channels` table based on role hierarchy
  - [ ] 4.2.4 Build visibility set: compute `channel_idx = int(channel_hash, 16)` for each visible channel
  - [ ] 4.2.5 Build full known set: all `channel_idx` values from all channels in DB (for "unknown = public" clause)
  - [ ] 4.2.6 Apply three-clause filter: `(message_type != 'channel') OR (channel_idx IN (visible_idxs)) OR (channel_idx NOT IN (all_known_idxs))`

- [ ] 4.3 Add role-aware channel filtering to dashboard endpoints
  - [ ] 4.3.1 Resolve user's highest role from auth context (same logic as `/messages`)
  - [ ] 4.3.2 Filter `GET /dashboard/stats` channel message counts by visible channels
  - [ ] 4.3.3 Filter `GET /dashboard/message-activity` channel activity lists by visible channels
  - [ ] 4.3.4 When OIDC disabled: show all channels (no filtering)

- [ ] 4.4 Update `_build_channel_labels()` in `web/app.py`
  - [ ] 4.4.1 Replace env-var parsing with database query using a synchronous SQLAlchemy engine
  - [ ] 4.4.2 Maintain existing format: `{str(channel_idx): label}`
  - [ ] 4.4.3 Include both built-in `Public` and all `enabled=true` channels from DB
  - [ ] 4.4.4 Remove `_parse_decoder_key_entries()` helper function

- [ ] 4.5 Update web proxy `_build_endpoint_access()`
  - [ ] 4.5.1 Add `"v1/channels": { "GET": _OPEN }` — anyone can list (filtering is server-side)
  - [ ] 4.5.2 Add `"v1/channels/": { "POST": frozenset({role_admin}), "PUT": frozenset({role_admin}), "DELETE": frozenset({role_admin}) }` — admin-only mutations
  - [ ] 4.5.3 Verify longest-prefix matching: `v1/channels/` takes precedence for POST/PUT/DELETE over `v1/channels`

- [ ] 4.6 Write tests for API endpoints and filtering
  - [ ] 4.6.1 Test `GET /channels` returns only public channels when no auth
  - [ ] 4.6.2 Test `GET /channels` returns appropriate channels per role
  - [ ] 4.6.3 Test `POST/PUT/DELETE /channels` restricted to admin only
  - [ ] 4.6.4 Test message filtering: only visible channel messages returned per role
  - [ ] 4.6.5 Test message filtering: unknown channels pass through (treated as public)
  - [ ] 4.6.6 Test message filtering: direct messages always visible
  - [ ] 4.6.7 Test dashboard channel counts filtered by role
  - [ ] 4.6.8 Verify existing tests referencing `channel_labels["17"] == "Public"` still pass

## 5. CLI Commands

- [ ] 5.1 Add `channel` subgroup to collector CLI
  - [ ] 5.1.1 Create `channel` Click group in `src/meshcore_hub/collector/cli.py`
  - [ ] 5.1.2 Implement `meshcore-hub collector channel list` — table output: name, masked key, hash, visibility, enabled
  - [ ] 5.1.3 Implement `meshcore-hub collector channel add --name NAME --key HEX --visibility public` — create channel row
  - [ ] 5.1.4 Implement `meshcore-hub collector channel remove --name NAME` — delete channel by name
  - [ ] 5.1.5 Implement `meshcore-hub collector channel enable --name NAME` — set `enabled=true`
  - [ ] 5.1.6 Implement `meshcore-hub collector channel disable --name NAME` — set `enabled=false`
  - [ ] 5.1.7 Remove `channel_keys` and `include_test_channel` params from `_run_collector_service()`

- [ ] 5.2 Write tests for CLI commands
  - [ ] 5.2.1 Test `channel list` output format
  - [ ] 5.2.2 Test `channel add` creates row with correct fields and `channel_hash` computed
  - [ ] 5.2.3 Test `channel add` rejects invalid keys (non-hex, wrong length)
  - [ ] 5.2.4 Test `channel add` rejects duplicate names
  - [ ] 5.2.5 Test `channel remove` deletes row
  - [ ] 5.2.6 Test `channel enable/disable` toggles `enabled` flag
  - [ ] 5.2.7 Test that old `--channel-keys` option is removed (CLI help output)

## 6. Web Dashboard — Channels Page

- [ ] 6.1 Add `FEATURE_CHANNELS` feature flag
  - [ ] 6.1.1 Add `feature_channels: bool` to `WebSettings` (default `true`, env var `FEATURE_CHANNELS`)
  - [ ] 6.1.2 Add `"channels": self.feature_channels` to `features` property (NO `oidc_enabled` guard)
  - [ ] 6.1.3 Expose in `/config` endpoint response

- [ ] 6.2 Create Channels page module
  - [ ] 6.2.1 Create `src/meshcore_hub/web/static/js/spa/pages/channels.js`
  - [ ] 6.2.2 Implement `render(container, params, router)` — fetch `/api/v1/channels`, render card grid
  - [ ] 6.2.3 Return a cleanup function if any resources are created
  - [ ] 6.2.4 Responsive card layout: DaisyUI `card` component, grid adapts to screen width

- [ ] 6.3 Channel card UI
  - [ ] 6.3.1 Card content: channel name, channel hash badge, visibility badge (OIDC only), QR code, masked key
  - [ ] 6.3.2 QR code generation: `new QRCode(canvas, { text: "meshcore://channel/add?name=<encoded>&key=<hex>" })` using existing `qrcodejs` library
  - [ ] 6.3.3 Masked key display: `{first4}...{last4}` with reveal toggle for admin users
  - [ ] 6.3.4 Visibility badge: colored badge (e.g., green=public, yellow=member, orange=operator, red=admin)
  - [ ] 6.3.5 Use `getConfig().oidc_enabled` to conditionally show admin controls and visibility badges

- [ ] 6.4 Admin inline channel management modals
  - [ ] 6.4.1 Add Channel modal (follow tag editor pattern from `node-detail.js:25-71`)
  - [ ] 6.4.2 Fields: name (text), key_hex (text, validated as hex), visibility (select: public/member/operator/admin), enabled (toggle)
  - [ ] 6.4.3 Edit Channel modal: pre-populate fields, name read-only
  - [ ] 6.4.4 Delete confirmation modal (follow `tagDeleteModal` pattern)
  - [ ] 6.4.5 All modal actions gated behind `hasRole('admin')` — only rendered when admin

- [ ] 6.5 Conditional rendering modes
  - [ ] 6.5.1 OIDC disabled: read-only cards, all channels public, no visibility badges, no add/edit/delete UI
  - [ ] 6.5.2 OIDC enabled, not logged in: read-only cards, only public channels shown
  - [ ] 6.5.3 OIDC enabled, non-admin: read-only cards, channels filtered by role, visibility badges shown
  - [ ] 6.5.4 OIDC enabled, admin: full management — "Add Channel" button, edit/delete per card, visibility select in forms

- [ ] 6.6 Update channel filter dropdowns across the SPA
  - [ ] 6.6.1 Dashboard channel filter: only show channels visible to user's role
  - [ ] 6.6.2 Messages page channel filter: only show channels visible to user's role
  - [ ] 6.6.3 When OIDC disabled, all channels appear in both dropdowns

- [ ] 6.7 Navigation placement — Channels between Messages and Members on all surfaces
  - [ ] 6.7.1 `spa.html` desktop sidebar: insert `<li>` for `/channels` with `iconChannel()` between Messages and Members
  - [ ] 6.7.2 `spa.html` mobile menu: insert `<li>` for `/channels` between Messages and Members
  - [ ] 6.7.3 `app.js` dynamic nav: insert `if (features.channels !== false)` block between Messages and Members blocks
  - [ ] 6.7.4 `app.js` route registration: `router.addRoute('/channels', pageHandler(pages.channels))` (no OIDC gate)
  - [ ] 6.7.5 `app.js` `updatePageTitle()`: add 'channels' case
  - [ ] 6.7.6 `home.js` hero card grid: insert `renderNavCard()` for Channels between Messages and Members
  - [ ] 6.7.7 Add `--color-channels` CSS custom property in `app.css` for hero card accent color
  - [ ] 6.7.8 Import `iconChannel` from `icons.js` in `channels.js`, `home.js`, `app.js`; use inline in `spa.html`

- [ ] 6.8 i18n
  - [ ] 6.8.1 Add channel-related keys to `src/meshcore_hub/web/static/locales/en.json`:
    - `entities.channel`, `entities.channels`
    - `channels.title`, `channels.add_channel`, `channels.edit_channel`, `channels.delete_channel`
    - `channels.name_label`, `channels.key_label`, `channels.visibility_label`, `channels.enabled_label`
    - `channels.channel_hash_label`, `channels.qr_code_label`
    - `channels.visibility_public`, `channels.visibility_member`, `channels.visibility_operator`, `channels.visibility_admin`
    - `common.no_entity_found` for channels (composed pattern)
  - [ ] 6.8.2 Add tests for new i18n keys in `tests/test_common/test_i18n.py`
  - [ ] 6.8.3 Update `docs/i18n.md` with new keys and usage context

## 7. Seeding, Config Cleanup & Docs

- [ ] 7.1 Add `channels.yaml` seed support
  - [ ] 7.1.1 Add channels seeding to `seed` command in `src/meshcore_hub/collector/cli.py`
  - [ ] 7.1.2 Read `${SEED_HOME}/channels.yaml`
  - [ ] 7.1.3 Parse shorthand format: `name: HEX` — value is `str`, treated as `key_hex`
  - [ ] 7.1.4 Parse expanded format: `name: { key: HEX, enabled: true }` — value is `dict`
  - [ ] 7.1.5 Parser distinguishes by type: `isinstance(value, str)` vs `isinstance(value, dict)`
  - [ ] 7.1.6 No `visibility` field — always defaults to `public`
  - [ ] 7.1.7 Upsert logic: update existing channel by `name`, insert new ones; never delete

- [ ] 7.2 Remove `COLLECTOR_CHANNEL_KEYS` and `COLLECTOR_INCLUDE_TEST_CHANNEL` from all files
  - [ ] 7.2.1 `src/meshcore_hub/common/config.py` — `CollectorSettings`
  - [ ] 7.2.2 `src/meshcore_hub/web/app.py` — `_parse_decoder_key_entries()`, `_build_channel_labels()`
  - [ ] 7.2.3 `src/meshcore_hub/collector/cli.py` — `_run_collector_service()`
  - [ ] 7.2.4 `src/meshcore_hub/collector/subscriber.py` — `Subscriber.__init__`, `create_subscriber()`, `run_collector()`
  - [ ] 7.2.5 `.env.example` — lines 204, 208
  - [ ] 7.2.6 `AGENTS.md` — env var list

- [ ] 7.3 Update documentation
  - [ ] 7.3.1 Update `docs/seeding.md` with `channels.yaml` format, examples, and note that visibility is always `public`
  - [ ] 7.3.2 Update `docs/upgrading.md` with migration guide:
    - Run `meshcore-hub db upgrade`
    - Convert `COLLECTOR_CHANNEL_KEYS` values to `channels.yaml` or DB rows via CLI
    - Remove env var from `.env`
    - Note all seeded channels are `public`
  - [ ] 7.3.3 Update `AGENTS.md`: add `Channel` model to model list, `FEATURE_CHANNELS` to feature flags, `/channels` to API routes
  - [ ] 7.3.4 Update `SCHEMAS.md` if channel event schemas are affected
  - [ ] 7.3.5 Create example `channels.yaml` in `example/seed/channels.yaml`

## 8. Verification

- [ ] 8.1 Code quality
  - [ ] 8.1.1 Run `pre-commit run --all-files` and fix all issues
  - [ ] 8.1.2 Ensure no `except ValueError, TypeError:` patterns (use parenthesized tuples)

- [ ] 8.2 Component tests
  - [ ] 8.2.1 Run `pytest tests/test_collector/` for collector-side changes
  - [ ] 8.2.2 Run `pytest tests/test_api/` for API endpoints and message filtering
  - [ ] 8.2.3 Run `pytest tests/test_web/` for web dashboard changes
  - [ ] 8.2.4 Run `pytest tests/test_common/` for model and schema changes
  - [ ] 8.2.5 Run `pytest tests/test_common/test_i18n.py` for i18n keys
  - [ ] 8.2.6 Run full `pytest` to verify no regressions

- [ ] 8.3 Manual verification
  - [ ] 8.3.1 Start collector with empty channels table — verify only `Public` channel messages decrypted and stored
  - [ ] 8.3.2 Add a channel via CLI — verify collector picks it up at next refresh without restart
  - [ ] 8.3.3 Seed channels from `channels.yaml` — verify rows created with `visibility=public`
  - [ ] 8.3.4 Verify dashboard loads without errors and no features are lost
  - [ ] 8.3.5 Verify Channels page renders correctly in all modes (OIDC disabled, logged out, admin)
  - [ ] 8.3.6 Verify message filtering by role (different roles see different channel messages)
  - [ ] 8.3.7 Verify QR code renders on channel cards
