# Upgrading MeshCore Hub

This guide covers upgrading from a previous MeshCore Hub release to the current version. Check the relevant version section below before upgrading.

## v0.16.0

### Route Health Monitoring

A new **Routes** page lets operators define monitored multi-hop mesh routes (an ordered list of two or more nodes) and track each one's health. A background evaluator on the collector matches captured packet paths against each route's configured node sequence within a configurable time window and rolls the result up into a traffic-light **quality** band (`clear` / `marginal` / `failing` / `unknown`) plus a **state** (`healthy` / `unhealthy` / `no_coverage`). Routes carry the same role-based visibility levels as channels (`community` / `member` / `operator` / `admin`), can be scoped to specific observers, and are matched in both directions by default (`reversible`). Define them via `routes.yaml` in `SEED_HOME` (see [seeding.md → Routes](seeding.md#routes)) or the `/api/v1/routes` API; see [routes.md](routes.md) for the feature overview.

**On by default** and non-breaking — the page renders and the evaluator runs with no configuration. Hide the page with `FEATURE_ROUTES=false`; stop the evaluator with `ROUTE_EVALUATOR_INTERVAL_SECONDS=0`.

**Database migration required:**

```
meshcore-hub db upgrade
```

This creates five tables — `routes`, `route_nodes`, `route_observers`, `route_results`, `packet_path_hops` — and backfills `packet_path_hops` from existing `raw_packets.decoded`. Route health therefore relies on **Raw Packet Capture** being enabled (`FEATURE_PACKETS=true`, the default) so packet paths continue to be captured. The migration runs automatically on Docker startup; the schema change is additive and safe on both SQLite and Postgres.

**New optional environment variables (all safe to omit):**

| Variable                            | Default | Description                                                                                          |
| ----------------------------------- | ------- | ---------------------------------------------------------------------------------------------------- |
| `FEATURE_ROUTES`                    | `true`  | Show the `/routes` page and nav entry. On by default.                                                |
| `ROUTE_EVALUATOR_INTERVAL_SECONDS`  | `60`    | Collector background evaluator cadence in seconds. `0` disables the evaluator (cards stay `unknown`). |

### Observer Ingestion Filters (allow/deny remote observers)

Remote observers contribute to the Hub by publishing decoded packets to your MQTT broker, and anyone with broker access can do so. You can now restrict which observers are ingested by their public key with two new **optional** collector variables:

| Variable | Default | Description |
| --- | --- | --- |
| `OBSERVER_ALLOWLIST` | _(none)_ | Comma-separated observer public keys (or prefixes) permitted to ingest. If set, only matching observers are accepted and `OBSERVER_DENYLIST` is ignored. |
| `OBSERVER_DENYLIST` | _(none)_ | Comma-separated observer public keys (or prefixes) blocked from ingesting. Applies only when `OBSERVER_ALLOWLIST` is unset. |

- **Non-breaking:** both default to empty, which preserves the existing accept-all behaviour. No action is required to keep current behaviour.
- The allowlist **takes precedence** over the denylist, and matching is **case-insensitive prefix** matching (a full 64-char key or a shorter prefix both work).
- A blocked observer's packets are dropped at ingest, **before** any decode or database write — nothing is persisted or forwarded for them.

In Docker Compose, set `OBSERVER_ALLOWLIST` / `OBSERVER_DENYLIST` in your `.env`; they are wired into the collector service. See [configuration.md → Observer Ingestion Filters](configuration.md#observer-ingestion-filters) and [observer.md](observer.md).

## v0.15.0

### Spam Detection (score, hide, and toggle likely-spam messages)

Each message is now scored for spam likelihood **at ingest** and the score is stored on the row. Likely-spam messages are **hidden by default** on the Messages page, with a "show potential spam" toggle to reveal them. Nothing is ever dropped — scoring is purely additive and the display layer filters on the stored score, so the feature is fully reversible. Scoring runs on both SQLite and PostgreSQL.

The scorer combines two windowed signals over a sliding time window: a **path signal** (joint count of the same origin-side path prefix + normalised sender) and a **name signal** (count of the same normalised sender, after stripping a trailing digit/space suffix so rotating `bob1`/`bob2`/`Bob 3` collapse to `bob`). When the path is too short to be useful — including the **zero-hop case** where an observer sits right next to the sender — the name signal stands on its own at full weight, so local/zero-hop spam can still be flagged. A background sweep re-scores recent rows with hindsight (a symmetric window) so the leading edge of a burst is caught once its peers arrive.

**On by default.** After upgrading, the collector scores new messages and the API hides likely-spam from the Messages page automatically — operators get protection without any configuration. To opt out, set `FEATURE_SPAM_DETECTION=false` and recreate the `collector`, `api`, and `web` services. Existing messages ingested before the upgrade keep null scores and are never hidden (no backfill), so only newly-ingested traffic is affected.

**Database migration required:**

```
meshcore-hub db upgrade
```

This adds three nullable columns to the `messages` table — `path_prefix`, `sender_normalized`, `spam_score` — plus two composite indexes (`ix_messages_path_prefix_received_at`, `ix_messages_sender_normalized_received_at`). The migration is batch-mode and runs on both SQLite and Postgres. On Docker deployments it runs automatically on startup. **No backfill:** only messages ingested *after* enabling are scored; historical rows keep null scores and are never hidden.

**New optional environment variables (all safe to omit):**

| Variable                  | Default | Description                                                                                                                  |
| ------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `FEATURE_SPAM_DETECTION`  | `true`  | The single operator switch. Shows the "show potential spam" toggle on the Messages page. In Compose this **derives** the backend `SPAM_DETECTION_ENABLED` for the collector and api. Set to `false` to opt out. |
| `SPAM_DETECTION_ENABLED`  | `true`  | Backend operational switch read by the collector (scoring + sweep) and api (hide-filter). In Compose derived from `FEATURE_SPAM_DETECTION`; set directly only when running without Compose. |
| `SPAM_SCORE_THRESHOLD`    | `0.65`  | Score at/above which a message is treated as likely spam — hidden by default in the API, logged at WARNING by the collector. Read by collector + api. |

**Scoring tuning (collector only; consulted only when detection is enabled):**

| Variable                        | Default | Description                                                        |
| ------------------------------- | ------- | ------------------------------------------------------------------ |
| `SPAM_WINDOW_SECONDS`           | `300`   | Sliding window for the frequency counts                            |
| `SPAM_PATH_HOPS`                | `3`     | Leading origin-side hops that form the path prefix                 |
| `SPAM_MIN_PATH_HOPS`            | `3`     | Minimum `path_len` before the path signal applies                  |
| `SPAM_PATH_THRESHOLD`           | `6`     | Joint path+sender count that saturates the path signal             |
| `SPAM_NAME_THRESHOLD`           | `10`    | Sender count that saturates the name signal                        |
| `SPAM_WEIGHT_PATH`              | `0.75`  | Weight of the path signal                                          |
| `SPAM_WEIGHT_NAME`              | `0.25`  | Weight of the name signal                                          |
| `SPAM_RESCORE_INTERVAL_SECONDS` | `120`   | Background re-scoring sweep cadence (`0` disables the sweep)       |

**Feature ↔ backend split:** the UI toggle is served by the `web` app while scoring runs in the `collector` and the hide-filter in the `api` — separate processes with separate settings. Docker Compose links them: `FEATURE_SPAM_DETECTION` (default `true`) drives scoring + sweep on the collector, the hide-filter on the api (both via `SPAM_DETECTION_ENABLED=${FEATURE_SPAM_DETECTION}`), and the toggle in the web UI. Operators running the processes directly can set `SPAM_DETECTION_ENABLED` independently.

**API:** message endpoints gain a `spam_score` field and an `include_spam` query parameter. By default the API hides rows scoring at/above `SPAM_SCORE_THRESHOLD`; `include_spam=true` returns them (rows with a null score — i.e. ingested before the upgrade, or while the feature was opted out — are always shown). With the feature opted out the filter is a no-op.

The feature is on by default and all variables are passed through `docker-compose.yml` automatically — no configuration is needed to adopt it. To opt out, set `FEATURE_SPAM_DETECTION=false` in your `.env` and recreate the `collector`, `api`, and `web` services.

### Docker Compose `pull_policy` removed from base

A `pull_policy: daily` that had been added to the five hub services (`collector`, `api`, `web`, `migrate`, `seed`) in the base `docker-compose.yml` has been removed. It caused `up` to pull the published image over a freshly built local image in development, clobbering local builds.

- **Base** (`docker-compose.yml`) now sets **no** `pull_policy`, falling back to Compose's default `missing` (pull only when the image is absent).
- **Dev** (`docker-compose.dev.yml`) sets `pull_policy: build` on all five hub services, so `make build && make up` always (re)builds from local source and never pulls.
- **Prod** (`docker-compose.prod.yml`) is unchanged and inherits the default `missing` policy.

**No action required** beyond pulling the updated compose files. **Production note:** image refreshes are no longer automatic on `up` — to move prod to a newer published image run `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull` followed by `up -d`.

## v0.14.0

### Optional PostgreSQL Backend

MeshCore Hub can now run on **PostgreSQL** as an alternative to the default SQLite database. SQLite remains the zero-config default — Postgres is entirely opt-in and **no action is required** to keep using SQLite. Switch to Postgres to scale writes and run the stack across multiple hosts (SQLite's file locking does not work over network filesystems and caps you at a single host).

> [!NOTE]
> As of v0.14, SQLite is **deprecated** in favour of PostgreSQL. SQLite continues to work as the default, but support will be removed in a future release (at least 3 months out). Existing SQLite deployments can migrate with the command below.

For the **backend setup reference** — the `DATABASE_*` environment variables, the bundled Docker `postgres` profile, production role/database provisioning, managed/external Postgres (`DATABASE_URL`), and schema-per-instance (`search_path`) isolation for multiple instances sharing one cluster — see [database.md](database.md). The remainder of this section covers the upgrade-time migration of live SQLite data into Postgres.

#### Migrating an existing SQLite database to Postgres

Downtime is required while writers are stopped; the source SQLite file is never modified.

1. **Back up first.** Copy your `meshcore.db` (or back up the `hub_data` volume — see [Backup & Restore](maintenance.md)).
2. **Stop the writers** (collector and api):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml stop collector api
   ```
3. **Bring up Postgres** and create the schema:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile postgres up -d postgres
   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile postgres run --rm migrate
   ```
   `migrate` runs `db upgrade` against Postgres, creating the schema, all tables (with correct native types — `boolean`, `json`, `timestamptz`), and stamping `alembic_version`.
4. **Copy the data** with the built-in command:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile postgres \
     run --rm migrate meshcore-hub db migrate-to-postgres
   ```
   It defaults the source to `sqlite:///{DATA_HOME}/collector/meshcore.db` and the target to your configured `DATABASE_*` connection. It copies every table in foreign-key order through the ORM (so SQLite's dynamically typed values are converted correctly — `0/1` → `boolean`, JSON text → `json`, naive datetimes → UTC `timestamptz`), then prints a per-table source-vs-target row-count reconciliation and fails on any mismatch. Use `--dry-run` to preview counts first, and `--truncate` to overwrite a non-empty target.
5. **Start the stack on Postgres** with `DATABASE_BACKEND=postgres` set (see [database.md](database.md) for the env vars and `postgres` compose profile).

> **Managed Postgres / non-superuser roles:** the migration disables foreign-key triggers during the copy via `session_replication_role = replica`, which requires a superuser. When the target role is not a superuser (typical for managed Postgres), the command automatically falls back to copying in parent-first order instead. Pass `--no-replication-role` to force the fallback explicitly.

### Dashboard Chart Fix (Postgres)

After enabling Postgres, the dashboard charts (activity, message-activity, node-count) may render as flat zeros. This is a known issue caused by a dialect mismatch in the date-bucketing query — `func.date()` returns a `str` on SQLite but a `datetime.date` on Postgres, causing the dict lookup to miss. A fix normalizes the key to a canonical `"%Y-%m-%d"` string and pins the Postgres session timezone to UTC.

The fix takes effect **after one `REDIS_CACHE_TTL_DASHBOARD` period** (default 30 seconds) — stale all-zero cached responses expire automatically. For operators who have configured a substantially longer TTL, either wait one TTL period or flush the three dashboard cache key prefixes:

```bash
redis-cli -h <redis-host> DEL \
  "$(echo -n 'hub:dashboard:activity*' | xargs redis-cli KEYS)" \
  "$(echo -n 'hub:dashboard:message-activity*' | xargs redis-cli KEYS)" \
  "$(echo -n 'hub:dashboard:node-count*' | xargs redis-cli KEYS)"
```

No database migration or configuration change is required — the fix is automatic.

## v0.13.0

### Raw Packets (capture, browse, and search wire packets)

A new **Raw Packets** feature captures every inbound MeshCore packet exactly as it arrives over the LetsMesh `packets` feed into a dedicated `raw_packets` table, independent of how the collector later classifies it. A new `/packets` API and a SPA **Packets** page (table on desktop, cards on mobile) let operators browse, filter, and search the raw traffic.

**Database migration required:**

```
meshcore-hub db upgrade
```

This creates the `raw_packets` table and its indexes. On Docker deployments the migration runs automatically on startup.

**New optional environment variables (all safe to omit):**

| Variable                     | Default                | Description                                                                                  |
| ---------------------------- | ---------------------- | -------------------------------------------------------------------------------------------- |
| `FEATURE_PACKETS`            | `true`                 | Show the Packets page and nav entry. On by default.                                           |
| `RAW_PACKET_CAPTURE_ENABLED` | `false`                | Collector-side capture of raw packets. In Compose this is **derived from `FEATURE_PACKETS`**. |
| `RAW_PACKET_RETENTION_DAYS`  | `7`                    | Days to retain raw packets, independent of the global retention window.                       |

**Capture ↔ page split:** capture runs in the collector while the page is served by the web app — two separate processes with separate settings. Docker Compose links them: setting `FEATURE_PACKETS=true` enables **both** capture (`RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS}` on the collector) and the page. Advanced operators running the processes directly can set the two flags independently.

**No backfill:** only packets captured *after* enabling appear — historical traffic is not reconstructed.

**Storage:** `raw_packets` grows fastest of all tables (one row per packet per observer). On busy meshes or constrained storage, lower `RAW_PACKET_RETENTION_DAYS`. Retention cleanup runs regardless of whether capture is currently enabled, so turning capture off lets existing rows drain. Restricted-channel packets are stored in full but returned **metadata-only (redacted)** to roles that cannot see the channel.

**Caching:** `/packets` responses are cached in Redis (when enabled) using a **role-aware** cache key and honour the existing `REDIS_CACHE_TTL`, so redacted responses are never served across roles.

The `advertisements` and `messages` tables gain a nullable `packet_hash` column (added by the same `db upgrade`) so each event can link to its captured raw packets. When `FEATURE_PACKETS` is on, the entire Adverts/Messages list row links to that transmission's deduplicated packet-detail page (see below). Only events ingested while capture was enabled carry the hash (no backfill), so non-capturing rows are not clickable.

**On by default:** as of v0.13.0 `FEATURE_PACKETS` defaults to `true` (was `false`). To keep the page hidden and capture off, set `FEATURE_PACKETS=false`.

### Finer-Grained Packet Classification

Packets the collector previously could not categorise were all emitted as a single `letsmesh_packet` event. They are now classified by their MeshCore payload type — `req`, `response`, `ack`, `encrypted_direct`, `encrypted_channel`, `grp_data`, `anon_req`, `multipart`, `control`, `raw_custom`, plus `advert`/`path`/`trace` for malformed variants. `letsmesh_packet` remains only as a safety net for packets whose payload type can't be resolved.

**Action only if you consume `event_type`:** any external webhook filter, saved query, or dashboard keyed on `letsmesh_packet` should be updated to the specific type(s) it cares about. No database migration or config change is involved.

### Deduplicated Packet Detail & Node Path Lookup

The Packets experience is now centred on a **deduplicated packet-detail page** (`/packets/hash/:hash`, backed by `GET /api/v1/packet-groups`): one entry per `packet_hash`, listing every observer reception with its SNR and full routing path. Each hop renders as a **path-hash badge**; clicking a badge opens a popover that looks up the node(s) whose public key starts with that 1–3 byte hex prefix (via the new `pubkey_prefix` query param on `GET /api/v1/nodes`) and links to each node's detail page, capped at 8 with a link through to the prefix-filtered Nodes page.

Adverts and Messages list rows (desktop and mobile) now link **directly** to this packet-detail page instead of a filtered packet list. The old per-row packet icon, the inline observer-expansion row, and the `/packets` packet-hash filter chip have been removed; the observer-count column remains.

**Defaults changed in this release:**

- `FEATURE_PACKETS` now defaults to `true` (page on, and capture on in Compose).
- `RAW_PACKET_RETENTION_DAYS` now defaults to `7` days, independent of `DATA_RETENTION_DAYS` (previously fell back to it). Lower it on busy meshes or constrained storage.

Because raw packets are pruned after 7 days, opening an old advert/message's packet link may 404 once the underlying packets have been cleaned up; the detail page now shows a friendly "Packet not found — it may have been cleaned up due to data retention" message instead of a generic error.

**No migration or action required** beyond the defaults above; override either variable in your `.env` to restore prior behaviour.

### System Announcement Banner & Maintenance Mode

Two new operator-only web settings, both applied at startup (set the variable, then restart the `web` service):

| Variable              | Default | Description                                                                                                   |
| --------------------- | ------- | ------------------------------------------------------------------------------------------------------------- |
| `SYSTEM_ANNOUNCEMENT` | _(none)_ | Markdown system notice shown as a **non-dismissable** banner above the existing `NETWORK_ANNOUNCEMENT` banner. |
| `SYSTEM_MAINTENANCE`  | `false` | Maintenance mode: nav shows only Home, the profile menu is hidden, and every page renders a maintenance notice. |

**`SYSTEM_ANNOUNCEMENT`** stacks above `NETWORK_ANNOUNCEMENT` (order: navbar → system → network). Unlike the network banner it has no close button and cannot be dismissed — it stays until you unset the variable and restart. Use it for downtime/maintenance windows and alerts. Markdown (bold, italic, links, inline code) is supported, same as `NETWORK_ANNOUNCEMENT`.

**`SYSTEM_MAINTENANCE=true`** disables almost all site functionality so that the dashboard makes **no backend API calls**. This lets you take the API service and database offline for upgrades/maintenance while leaving the `web` component running to show users a friendly "Site Under Maintenance" page (site logo, name, and a translatable message). Set it before maintenance, restart `web`, and unset it (or `false`) + restart when done.

**No migration or action required** — both variables are optional and default to off. They are passed through in `docker-compose.yml` automatically; just add them to your `.env`.

## v0.12.0

### Multi-Worker API (`API_WORKERS`)

The API can now run multiple worker processes in a single container for multi-core concurrency, controlled by a new `API_WORKERS` environment variable (default `1`, unchanged behaviour). Each worker is an independent process sharing one listening socket.

**New environment variable:**

| Variable      | Default | Description                                                         |
| ------------- | ------- | ------------------------------------------------------------------- |
| `API_WORKERS` | `1`     | Number of API worker processes (increase for multi-core concurrency) |

**No action required to upgrade** — the default of `1` preserves the previous single-process behaviour. To use it, set `API_WORKERS` in your `.env` and recreate the `api` service.

**Important:** with more than one worker, configuration must come from **environment variables** — CLI flags passed to `meshcore-hub api` are not propagated to forked worker processes. Docker Compose deployments already configure everything via env, so they are unaffected. Enabling Redis (`REDIS_ENABLED=true`) is recommended so all workers share one response cache.

While on SQLite, all workers share the same database file on the same host (WAL mode allows concurrent reads alongside the collector's single writer). Writes do not scale and this does not extend across multiple hosts; switch `DATABASE_URL` to PostgreSQL to scale beyond a single host. See [Scaling the API](deployment.md#scaling-the-api) for details.

### Read-Path Query Optimisations

Several read-heavy endpoints had their query patterns optimised (node `is_observer` filtering, dashboard node-count history, message/dashboard sender-name resolution, and consolidation of the `dashboard/stats` count queries into conditional aggregates). These are internal performance improvements with no API or configuration changes — responses are unchanged. The `is_observer` change ships an Alembic migration that is applied automatically on startup (Docker) or via `meshcore-hub db upgrade`.

### Dashboard Navigation Responsiveness

The web dashboard now cancels in-flight API requests when you navigate between pages. Previously, rapidly switching pages could leave slow requests (such as the homepage statistics) running in the background, holding connections and delaying the page you actually opened. This is a front-end behaviour fix only — no configuration or action is required.

### Optional Redis API Cache

A new optional Redis-backed caching layer reduces database load for read-heavy API endpoints (nodes, advertisements, messages, channels, dashboard). Redis is entirely optional — the API works identically without it.

**New optional dependency:** `redis[hiredis]` is installed automatically with `pip install -e .`. No manual action needed.

**New environment variables:**

| Variable                    | Default     | Description                                                      |
| --------------------------- | ----------- | ---------------------------------------------------------------- |
| `REDIS_ENABLED`             | `false`     | Enable Redis API response caching                                |
| `REDIS_HOST`                | `localhost` | Redis server host (`redis` in Docker)                            |
| `REDIS_PORT`                | `6379`      | Redis server port                                                |
| `REDIS_DB`                  | `0`         | Redis database number                                            |
| `REDIS_PASSWORD`            | _(none)_    | Redis password (optional)                                        |
| `REDIS_KEY_PREFIX`          | `hub`       | Cache key prefix (change per instance for multi-instance setups) |
| `REDIS_CACHE_TTL`           | `30`        | Default cache TTL in seconds                                     |
| `REDIS_CACHE_TTL_DASHBOARD` | `30`        | Cache TTL for dashboard endpoints                                |

**Docker Compose:** Redis is available via the `cache` profile:

```bash
docker compose --profile cache up    # Start with bundled Redis
docker compose --profile core up     # Start without Redis (default)
```

`REDIS_ENABLED` defaults to `false` everywhere (code and Docker Compose). Cache TTL defaults to 30 seconds (matching the web dashboard auto-refresh interval).

## v0.11.0

### Radio Config Split Into Individual Environment Variables

The single `NETWORK_RADIO_CONFIG` comma-delimited environment variable has been replaced with six individual variables. The legacy variable and its `from_config_string` parsing have been removed entirely. Each variable defaults to the EU/UK Narrow profile when unset.

Frequency, bandwidth, and TX power are now configured as raw numbers without unit suffixes. Units (`MHz`, `kHz`, `dBm`) are applied automatically on display.

**Migration example:**

Before:

```
NETWORK_RADIO_CONFIG=EU/UK Narrow,869.618MHz,62.5kHz,8,8,22dBm
```

After:

```
NETWORK_RADIO_PROFILE=EU/UK Narrow
NETWORK_RADIO_FREQUENCY=869.618
NETWORK_RADIO_BANDWIDTH=62.5
NETWORK_RADIO_SPREADING_FACTOR=8
NETWORK_RADIO_CODING_RATE=8
NETWORK_RADIO_TX_POWER=22
```

**Note:** Radio config is now "always on" with EU/UK Narrow defaults. To hide the radio config panel entirely, set `FEATURE_RADIO_CONFIG=false`.

### Channel Visibility Rename: "public" → "community"

The channel visibility level `"public"` has been renamed to `"community"` to avoid confusion with MeshCore's concept of public channels. All MeshCore channels are private (encrypted) in protocol terms, so "community" better reflects the access level.

The Alembic migration automatically updates existing `visibility='public'` rows to `visibility='community'`. No manual database changes are required.

API consumers that filter channels by `visibility=public` must update to `visibility=community`.

### Database-Backed Channel Keys

Channel decryption keys are now managed via the `channels` database table instead of the `COLLECTOR_CHANNEL_KEYS` environment variable. This enables runtime key management, permission-based visibility, and a Channels dashboard page.

**New database table: `channels`**

| Column                     | Type                   | Description                                   |
| -------------------------- | ---------------------- | --------------------------------------------- |
| `id`                       | `VARCHAR(36), PK`      | UUID primary key                              |
| `name`                     | `VARCHAR(100), UNIQUE` | Channel display name                          |
| `key_hex`                  | `VARCHAR(64), UNIQUE`  | Uppercase hex key (32 or 64 chars)            |
| `channel_hash`             | `VARCHAR(2)`           | First byte of SHA-256 of key                  |
| `visibility`               | `VARCHAR(20)`          | `community`, `member`, `operator`, or `admin` |
| `enabled`                  | `BOOLEAN`              | Whether the channel is active                 |
| `created_at`, `updated_at` | `DATETIME`             | Timestamps                                    |

**Removed environment variables:**

- `COLLECTOR_CHANNEL_KEYS` — replaced by database channels table
- `COLLECTOR_INCLUDE_TEST_CHANNEL` — replaced by presence of a `test` channel row in the database

**New environment variables:**

- `CHANNEL_REFRESH_INTERVAL_SECONDS` — seconds between key refresh (default: `300`)
- `FEATURE_CHANNELS` — enable/disable the /channels page (default: `true`)

**Migration steps:**

1. Run `meshcore-hub db upgrade` to create the `channels` table and update visibility values
2. Convert any `COLLECTOR_CHANNEL_KEYS` values to either:
   - A `channels.yaml` seed file in `SEED_HOME` (see `docs/seeding.md`)
   - Database rows via CLI: `meshcore-hub collector channel add --name X --key HEX`
3. Remove `COLLECTOR_CHANNEL_KEYS` and `COLLECTOR_INCLUDE_TEST_CHANNEL` from your `.env`
4. If you previously relied on test channel messages, add a test channel: `meshcore-hub collector channel add --name test --key 9CD8FCF22A47333B591D96A2B848B73F`

**Test channel behavior change:** Test channel messages (channel_idx 217) are now discarded by default unless a `test` channel row exists in the database with `enabled=true`. Previously this was controlled by `COLLECTOR_INCLUDE_TEST_CHANNEL`.

### Advertisement Route Type & Deduplication

Advertisement route type tracking and improved deduplication are included. New `route_type` and `advert_timestamp` columns are added to the `advertisements` table automatically by the migration. The API defaults to showing flood advertisements only. Deduplication uses a 5-minute bucket with node timestamps when available.

### Async SQLite Foreign Key Fix

The async SQLAlchemy engine now enables `PRAGMA foreign_keys=ON` for SQLite databases, matching the behavior of the sync engine. Previously, cascade deletes (`ondelete="CASCADE"`) were silently ignored when the collector deleted inactive nodes via the async engine, leaving orphaned rows in `user_profile_nodes`, `event_observers`, and `node_tags`.

**This is an automatic fix** — no configuration changes are required. The orphaned rows that may have accumulated in existing databases can be cleaned up with:

```bash
# Dry run to preview
meshcore-hub collector cleanup --node-cleanup --dry-run

# Live cleanup
meshcore-hub collector cleanup --node-cleanup
```

The collector's scheduled cleanup cycle now also runs orphan cleanup automatically after node deletion when `NODE_CLEANUP_ENABLED=true`.

### CLI Changes

The `meshcore-hub collector cleanup` command now accepts:

| Flag                  | Default | Description                                       |
| --------------------- | ------- | ------------------------------------------------- |
| `--node-cleanup`      | `false` | Also delete inactive nodes and orphaned relations |
| `--node-cleanup-days` | `30`    | Inactivity threshold for node deletion            |

## v0.10.0

This release introduces OIDC authentication, user profiles with node adoption, removes the Members system, replaces `role=infra` tags with adoption-based infrastructure detection, and replaces the admin tag editor with an inline editor on the node detail page.

### Breaking Changes

| Area                     | Before                                      | After                                                            |
| ------------------------ | ------------------------------------------- | ---------------------------------------------------------------- |
| Admin auth               | `WEB_ADMIN_ENABLED=true` (open access)      | OIDC/OAuth2 authentication via identity provider                 |
| Network Members          | `members` table + CRUD API + YAML seed      | Removed — replaced by `UserProfile` roles                        |
| Infrastructure detection | `role=infra` NodeTag                        | `user_profile_nodes` adoption records                            |
| Tag editing              | `/admin/node-tags` dedicated page           | Inline editor on node detail page                                |
| Tag API auth             | `RequireAdmin` (API key with open fallback) | `RequireOperatorOrAdmin` (OIDC role-based, always requires auth) |
| Admin UI                 | `/admin/` routes with SPA pages             | Removed entirely                                                 |
| Map API field            | `infra_center`                              | `adopted_center`                                                 |
| Map API field            | `is_infra` (on node objects)                | `is_adopted`                                                     |
| Prometheus label         | `role="infra"` / `role=""`                  | `adopted="true"` / `adopted="false"`                             |
| Profile endpoint         | `GET /api/v1/user/profile/{user_id}`        | `GET /api/v1/user/profile/{profile_id}` (UUID)                   |
| Node cleanup default     | 7 days                                      | 30 days                                                          |
| Python                   | 3.13                                        | 3.14                                                             |

### Removed API Endpoints

| Method   | Path                                    | Replacement                                       |
| -------- | --------------------------------------- | ------------------------------------------------- |
| `GET`    | `/nodes/{pk}/tags/{key}`                | Use `GET /nodes/{pk}` and filter tags client-side |
| `PUT`    | `/nodes/{pk}/tags/{key}/move`           | No replacement (delete + recreate)                |
| `POST`   | `/nodes/{pk}/tags/copy-to/{dest}`       | No replacement (create tags individually)         |
| `DELETE` | `/nodes/{pk}/tags` (bulk)               | No replacement (delete tags individually)         |
| `POST`   | `/api/v1/commands/send-message`         | Removed                                           |
| `POST`   | `/api/v1/commands/send-channel-message` | Removed                                           |
| `POST`   | `/api/v1/commands/send-advertisement`   | Removed                                           |
| All      | `/api/v1/members/*`                     | Use `/api/v1/user/profiles`                       |

### Removed Schemas

- `NodeTagMove`
- `NodeTagsCopyResult`

### Removed CLI Commands

- `meshcore-hub collector import-members`
- `--members` flag on `meshcore-hub collector truncate`

### Removed Files

- `src/meshcore_hub/web/static/js/spa/pages/admin/index.js`
- `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`
- `tests/test_web/test_admin.py`
- `seed/members.yaml`
- `example/seed/members.yaml`

### Upgrade Actions

1. **Set up an OIDC identity provider** (LogTo, Keycloak, etc.) and configure these environment variables:

   ```bash
   OIDC_ENABLED=true
   OIDC_CLIENT_ID=your-client-id
   OIDC_CLIENT_SECRET=your-client-secret
   OIDC_DISCOVERY_URL=https://your-idp.example.com/.well-known/openid-configuration
   OIDC_SESSION_SECRET=$(openssl rand -hex 32)
   ```

2. **Remove obsolete variables** from your `.env`:
   - `WEB_ADMIN_ENABLED` (replaced by `OIDC_ENABLED`)
   - `OIDC_ADMIN_ROLE` → renamed to `OIDC_ROLE_ADMIN`
   - `OIDC_MEMBER_ROLE` → renamed to `OIDC_ROLE_MEMBER`

3. **Remove `members.yaml`** from your seed directory (no longer used)

4. **Remove `member_id` tag keys** from `node_tags.yaml` (replaced by node adoption)

5. **Run database migration** — the migration:
   - Adds `roles` column to `user_profiles`
   - Creates `user_profiles` and `user_profile_nodes` tables (if not present)
   - Drops `members` table
   - Deletes obsolete `role=infra` and `member_id` tags from `node_tags`

6. **Update Prometheus alerting rules** that reference `role="infra"` to use `adopted="true"` (see `etc/prometheus/alerts.yml`)

7. **Update Grafana dashboards** that query `meshcore_node_last_seen_timestamp_seconds{role="infra"}` to use `adopted="true"`

8. **If you relied on the 7-day node cleanup default**, set it explicitly:
   ```bash
   NODE_CLEANUP_DAYS=7
   ```

### OIDC-Disabled Deployments

When `OIDC_ENABLED=false`:

- Tag writes require OIDC authentication → 401 on direct API access (tags are read-only via web UI)
- The inline tag editor is hidden on the node detail page
- `adopted_center` is always `null`, all nodes have `is_adopted: false`
- The map shows no "Infrastructure Only" filter, no legend — all nodes render as green markers
- The web proxy only allows GET access to known API endpoints; writes are blocked

### Tag Editor Authorization

Tag write endpoints now use `RequireOperatorOrAdmin` (OIDC role-based). The previous `RequireAdmin` had a fallback allowing open access when no admin key was configured. The new system always requires OIDC authentication:

- Operators can edit tags on their adopted nodes only
- Admins can edit tags on any node
- The admin API key no longer grants tag write access

### New Variables

| Variable             | Default    | Description                         |
| -------------------- | ---------- | ----------------------------------- |
| `OIDC_ROLE_ADMIN`    | `admin`    | IdP role name granting admin access |
| `OIDC_ROLE_OPERATOR` | `operator` | IdP role name for operator access   |
| `OIDC_ROLE_MEMBER`   | `member`   | IdP role name for member access     |

See `.env.example` for the full list of OIDC environment variables.

## v0.9.0

This release includes **breaking changes** to the MQTT broker, packet capture service, data ingestion pipeline, and public key handling.

### Overview of Changes

| Area             | Before                                    | After                                                                                                     |
| ---------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| MQTT broker      | Eclipse Mosquitto (TCP)                   | [meshcore-mqtt-broker](https://github.com/michaelhart/meshcore-mqtt-broker) (WebSocket, JWT auth)         |
| Packet capture   | Proprietary `interface-receiver` service  | [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) (LetsMesh Observer model) |
| Auth model       | MQTT username/password for publishing     | JWT signed by device hardware public key                                                                  |
| Collector MQTT   | Anonymous subscriber                      | Subscriber account (admin-level) with credentials                                                         |
| Decoder          | Node.js `meshcore-decoder` CLI subprocess | Native Python `meshcoredecoder` library                                                                   |
| Python           | 3.13                                      | 3.14                                                                                                      |
| DB columns       | `receiver_node_id`                        | `observer_node_id`                                                                                        |
| DB table         | `event_receivers`                         | `event_observers`                                                                                         |
| API commands     | `/api/v1/commands/*`                      | Removed                                                                                                   |
| Compose profiles | `receiver`, `sender`, `mock`              | `observer`                                                                                                |
| Compose files    | Single `docker-compose.yml`               | Base + environment overrides (`.dev.yml`, `.prod.yml`)                                                    |
| Container names  | `meshcore-*`                              | Parameterized via `COMPOSE_PROJECT_NAME` (default: `hub-*`)                                               |
| Volume names     | `meshcore_*`                              | Parameterized via `COMPOSE_PROJECT_NAME` (default: `hub_*`)                                               |
| Public key case  | Mixed (uppercase/lowercase)               | Normalized to **lowercase**                                                                               |

### Public Key Case Normalization

Previously, the tag importer stored `public_key` as lowercase while the LetsMesh packet normalizer stored it as UPPERCASE. This could create duplicate nodes for the same physical device — with tags linked to one node and mesh events linked to another.

An Alembic migration (`b1c2d3e4f5a6`) automatically:

1. Merges duplicate nodes (keeping the one with the earliest `first_seen`)
2. Re-points all foreign key references to the surviving node
3. Deletes the duplicate node
4. Normalizes all remaining `public_key` values to lowercase

**No manual action is required** — the migration runs as part of `meshcore-hub db upgrade` (or the `migrate` Docker Compose service).

### Step 1: Backup

**Do not skip this step.** Back up all data volumes before proceeding.

Back up the database volume. Volume names use the old `meshcore_*` prefix:

```bash
mkdir -p backup
docker run --rm -v meshcore_hub_data:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/meshcore_hub_data-$(date +%Y%m%d-%H%M%S).tar.gz -C / data
```

To restore from backup if needed:

```bash
# Extract the volume name from the backup filename
docker run --rm -v meshcore_hub_data:/data -v $(pwd)/backup:/backup \
  alpine sh -c "cd / && tar xzf /backup/meshcore_hub_data-YYYYMMDD-HHMMSS.tar.gz"
```

### Step 2: Stop and Remove Containers

Stop all services and remove orphaned containers from the old configuration:

```bash
docker compose --profile all down --remove-orphans
```

> **Important:** Do NOT use `--volumes` / `-v`. That would delete your database. The `--remove-orphans` flag cleans up old services (like `interface-receiver`, `interface-sender`) that no longer exist in the new compose file.

### Step 3: Rename Docker Volumes

Container and volume names are now parameterized via `COMPOSE_PROJECT_NAME`. The default is `hub`, so volumes are renamed from `meshcore_*` to `hub_*`.

First, check which volumes you have:

```bash
docker volume ls | grep meshcore
```

#### Volumes to migrate

These volumes always need migrating:

| Old Name            | New Name   |
| ------------------- | ---------- |
| `meshcore_hub_data` | `hub_data` |

> **Note:** `observer_data` and `mqtt_data` are new — they are created automatically on first run and do not need migrating.

#### Option A: Rename (Docker Engine 23.0+)

> **Note:** `docker volume rename` is not available in all Docker builds (e.g., Docker Desktop). If the command is not found, use Option B instead.

```bash
docker volume rename meshcore_hub_data hub_data
```

#### Option B: Copy (all Docker versions)

If `docker volume rename` is not available in your Docker build:

```bash
# Create new volume, copy data, remove old
docker volume create hub_data
docker run --rm -v meshcore_hub_data:/from -v hub_data:/to alpine sh -c "cp -a /from/. /to/"

# Verify the new volume has data, then remove old one
docker volume rm meshcore_hub_data
```

> **Note:** If any volumes show "in use", remove any stopped containers first: `docker rm -f <container_id>`.

> **Note:** If setting up a multi-instance deployment (e.g., `hub-prod`, `hub-beta`), use that project name instead of `hub`.

> **Note:** After migrating volumes, you may see warnings like `volume "hub_data" already exists but was not created by Docker Compose. Use \`external: true\` to use an existing volume`. This is safe to ignore — it appears because the volumes were created manually during migration rather than by Docker Compose. Fresh deployments will not see this warning.

### Step 4: Update Configuration Files

Download the latest configuration files:

```bash
# Download the base compose file and environment overrides
wget -O docker-compose.yml https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/docker-compose.yml
wget -O docker-compose.dev.yml https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/docker-compose.dev.yml
wget -O docker-compose.prod.yml https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/docker-compose.prod.yml

# Download the new .env.example for reference
wget -O .env.example https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/.env.example
```

Then compare your existing `.env` against the new `.env.example` and update it (see Step 5).

### Step 5: Migrate Your `.env` File

#### Variables to Remove

These variables no longer exist and should be removed from your `.env`:

```bash
# Removed: ingest mode is now always LetsMesh upload
COLLECTOR_INGEST_MODE=native

# Removed: decoder is now a native Python library, always enabled
COLLECTOR_LETSMESH_DECODER_ENABLED=true
COLLECTOR_LETSMESH_DECODER_COMMAND=meshcore-decoder
COLLECTOR_LETSMESH_DECODER_TIMEOUT_SECONDS=2.0

# Removed: serial baud is handled by meshcore-packet-capture
SERIAL_BAUD=115200

# Removed: sender service no longer exists
SERIAL_PORT_SENDER=/dev/ttyUSB1
NODE_ADDRESS_SENDER=

# Removed: device name/address now handled by meshcore-packet-capture
MESHCORE_DEVICE_NAME=
NODE_ADDRESS=

# Removed: contact cleanup was specific to the proprietary receiver
CONTACT_CLEANUP_ENABLED=true
CONTACT_CLEANUP_DAYS=7

# Removed: Mosquitto-specific ports
MQTT_EXTERNAL_PORT=1883
MQTT_WS_PORT=9001
```

#### Variables to Update

| Variable         | Old Value        | New Value           | Notes                                                                                                 |
| ---------------- | ---------------- | ------------------- | ----------------------------------------------------------------------------------------------------- |
| `MQTT_TRANSPORT` | `tcp`            | `websockets`        | Required by the new JWT-based broker                                                                  |
| `MQTT_WS_PATH`   | `/mqtt`          | `/`                 | New broker accepts connections on `/`                                                                 |
| `MQTT_USERNAME`  | (empty/optional) | Subscriber username | Now **required** for collector subscriber auth. Set to match your broker's `SUBSCRIBER_1` config.     |
| `MQTT_PASSWORD`  | (empty/optional) | Subscriber password | Now **required** for collector subscriber auth. Generate a secure password: `openssl rand -base64 32` |

> **Note:** The Python-level defaults for `MQTT_TRANSPORT` and `MQTT_WS_PATH` are now `websockets` and `/`, matching the Docker Compose and `.env.example` values. No additional configuration is needed for non-Docker users.

#### Variables to Add

```bash
# Docker Compose project name (container and volume prefix)
COMPOSE_PROJECT_NAME=hub

# JWT audience claim for packet capture authentication tokens
# Must match AUTH_EXPECTED_AUDIENCE on the broker
MQTT_TOKEN_AUDIENCE=mqtt.localhost

# IATA airport code for your observer location (required for packet capture)
# Use the 3-letter code for the nearest airport.
# Look up your code: https://www.iata.org/en/publications/directories/code-search/
PACKETCAPTURE_IATA=LOC
```

All other `PACKETCAPTURE_*` variables have sensible defaults in `docker-compose.yml` and only need to be set in `.env` if you want to override them. See `.env.example` for the full list.

### Step 6: Run Database Migration

The migration renames `receiver_node_id` → `observer_node_id` across all event tables, `event_receivers` → `event_observers`, and `received_at` → `observed_at` in the event observers table:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core run --rm migrate
```

This runs automatically as part of the `core` profile, but can also be run standalone with the `migrate` profile:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile migrate run --rm migrate
```

### Step 7: Start Services

#### With local MQTT broker (single-host deployment)

```bash
# Start everything including the MQTT broker
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mqtt --profile core up -d

# Or include packet capture on the same host
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mqtt --profile core --profile observer up -d
```

#### With external MQTT broker

```bash
# Start core services only (broker runs elsewhere)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core up -d
```

#### Verify

```bash
# Check all containers are running
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all ps

# Check collector connected to MQTT
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all logs collector | grep -i "connected to mqtt"

# Check the web dashboard
open http://localhost:8080
```

### Notes

#### JWT-Based Packet Capture Authentication

The new packet capture service ([meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture)) uses the LetsMesh Observer model:

- **No custom MQTT credentials needed for publishing.** Authentication is handled via JWT tokens signed by the capture device's hardware public key. The MQTT broker validates the JWT and authorizes publishing automatically.
- The collector connects as a **subscriber** to read all published events, including `/internal` topics. Configure `MQTT_USERNAME` and `MQTT_PASSWORD` to match the broker's subscriber account.

#### Production MQTT Configuration

In production, the MQTT WebSocket server should be hosted behind a TLS/SSL-terminated reverse proxy (e.g., Nginx Proxy Manager, Caddy, Traefik) under the `/mqtt` path. The proxy handles TLS termination and forwards plain WebSocket connections to the broker on port 1883.

**Local / development (default):**

```bash
MQTT_PORT=1883
MQTT_TRANSPORT=websockets
MQTT_WS_PATH=/
MQTT_TLS=false
MQTT_TOKEN_AUDIENCE=mqtt.localhost
```

**Production (behind reverse proxy):**

```bash
MQTT_PORT=443
MQTT_TRANSPORT=websockets
MQTT_WS_PATH=/mqtt
MQTT_TLS=true
MQTT_TOKEN_AUDIENCE=mqtt.example.com   # your public domain
```

#### Existing LetsMesh Observer Installs

If you already run [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) separately, configure **MQTT server #3** to point at your MeshCore Hub MQTT broker. Servers #1 and #2 are reserved for Let's Mesh US (`mqtt-us-v1.letsmesh.net`) and Let's Mesh EU (`mqtt-eu-v1.letsmesh.net`) respectively.

```bash
# In your packet-capture .env or docker-compose environment:
PACKETCAPTURE_MQTT3_ENABLED=true
PACKETCAPTURE_MQTT3_SERVER=your-meshcore-hub-host
PACKETCAPTURE_MQTT3_PORT=1883
PACKETCAPTURE_MQTT3_TRANSPORT=websockets
PACKETCAPTURE_MQTT3_USE_TLS=false
PACKETCAPTURE_MQTT3_USE_AUTH_TOKEN=true
PACKETCAPTURE_MQTT3_TOKEN_AUDIENCE=mqtt.localhost
```

#### Removed Services

The following Docker Compose services have been removed:

| Old Service               | Replacement                      |
| ------------------------- | -------------------------------- |
| `interface-receiver`      | `observer` (profile: `observer`) |
| `interface-sender`        | None (removed)                   |
| `interface-mock-receiver` | None (removed)                   |

The `observer` service uses the [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) image and is included in `docker-compose.yml` under the `observer` profile for an easy transition.

#### New Docker Compose File Structure

The Docker Compose configuration is now split into multiple files:

| File                         | Purpose                                                            |
| ---------------------------- | ------------------------------------------------------------------ |
| `docker-compose.yml`         | Base shared config (services, profiles, healthchecks, environment) |
| `docker-compose.dev.yml`     | Development overrides (port mappings for direct access)            |
| `docker-compose.prod.yml`    | Production overrides (external proxy network, no exposed ports)    |
| `docker-compose.traefik.yml` | Optional Traefik auto-discovery labels                             |

All `docker compose` commands now require explicit file selection:

```bash
# Development (exposes ports for local access)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile all up -d

# Production (connects to reverse proxy network)
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile all up -d

# Production with Traefik
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.traefik.yml --profile all up -d
```

Container and volume names are parameterized via `COMPOSE_PROJECT_NAME` in `.env`. This enables multiple instances (e.g., `hub-prod`, `hub-beta`) on the same Docker host.

#### Removed API Endpoints

The command dispatch API endpoints have been removed:

- `POST /api/v1/commands/send-message`
- `POST /api/v1/commands/send-channel-message`
- `POST /api/v1/commands/send-advertisement`

#### Native Python Decoder

The Node.js `meshcore-decoder` CLI tool has been replaced by the native Python `meshcoredecoder` library. This means:

- No Node.js runtime is needed in the Docker image
- The decoder is always enabled (no toggle)
- The `COLLECTOR_LETSMESH_DECODER_*` configuration variables have been removed
- `COLLECTOR_LETSMESH_DECODER_KEYS` has been renamed to `COLLECTOR_CHANNEL_KEYS`
- New `COLLECTOR_INCLUDE_TEST_CHANNEL` variable controls whether built-in test channel messages are collected (default: `false`)
