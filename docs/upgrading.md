# Upgrading MeshCore Hub

This guide covers upgrading from a previous MeshCore Hub release to the current version. Check the relevant version section below before upgrading.

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
| `FEATURE_PACKETS`            | `false`                | Show the Packets page and nav entry. Off by default.                                          |
| `RAW_PACKET_CAPTURE_ENABLED` | `false`                | Collector-side capture of raw packets. In Compose this is **derived from `FEATURE_PACKETS`**. |
| `RAW_PACKET_RETENTION_DAYS`  | = `DATA_RETENTION_DAYS` | Days to retain raw packets, independent of the global retention window.                       |

**Capture ↔ page split:** capture runs in the collector while the page is served by the web app — two separate processes with separate settings. Docker Compose links them: setting `FEATURE_PACKETS=true` enables **both** capture (`RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS}` on the collector) and the page. Advanced operators running the processes directly can set the two flags independently.

**No backfill:** only packets captured *after* enabling appear — historical traffic is not reconstructed.

**Storage:** `raw_packets` grows fastest of all tables (one row per packet per observer). On busy meshes or constrained storage, lower `RAW_PACKET_RETENTION_DAYS`. Retention cleanup runs regardless of whether capture is currently enabled, so turning capture off lets existing rows drain. Restricted-channel packets are stored in full but returned **metadata-only (redacted)** to roles that cannot see the channel.

**Caching:** `/packets` responses are cached in Redis (when enabled) using a **role-aware** cache key and honour the existing `REDIS_CACHE_TTL`, so redacted responses are never served across roles.

The `advertisements` and `messages` tables gain a nullable `packet_hash` column (added by the same `db upgrade`) so each event can link to its captured raw packets. When `FEATURE_PACKETS` is on, the Adverts and Messages list pages show a packet icon linking to the raw packets for that transmission. Only events ingested while capture was enabled carry the hash (no backfill), so the link is hidden for older rows.

**No action required** to keep current behaviour — the feature is off by default.

### Finer-Grained Packet Classification

Packets the collector previously could not categorise were all emitted as a single `letsmesh_packet` event. They are now classified by their MeshCore payload type — `req`, `response`, `ack`, `encrypted_direct`, `encrypted_channel`, `grp_data`, `anon_req`, `multipart`, `control`, `raw_custom`, plus `advert`/`path`/`trace` for malformed variants. `letsmesh_packet` remains only as a safety net for packets whose payload type can't be resolved.

**Action only if you consume `event_type`:** any external webhook filter, saved query, or dashboard keyed on `letsmesh_packet` should be updated to the specific type(s) it cares about. No database migration or config change is involved.

## v0.12.0

### Multi-Worker API (`API_WORKERS`)

The API can now run multiple worker processes in a single container for multi-core concurrency, controlled by a new `API_WORKERS` environment variable (default `1`, unchanged behaviour). Each worker is an independent process sharing one listening socket.

**New environment variable:**

| Variable      | Default | Description                                                         |
| ------------- | ------- | ------------------------------------------------------------------- |
| `API_WORKERS` | `1`     | Number of API worker processes (increase for multi-core concurrency) |

**No action required to upgrade** — the default of `1` preserves the previous single-process behaviour. To use it, set `API_WORKERS` in your `.env` and recreate the `api` service.

**Important:** with more than one worker, configuration must come from **environment variables** — CLI flags passed to `meshcore-hub api` are not propagated to forked worker processes. Docker Compose deployments already configure everything via env, so they are unaffected. Enabling Redis (`REDIS_ENABLED=true`) is recommended so all workers share one response cache.

While on SQLite, all workers share the same database file on the same host (WAL mode allows concurrent reads alongside the collector's single writer). Writes do not scale and this does not extend across multiple hosts; switch `DATABASE_URL` to PostgreSQL to scale beyond a single host. See [Scaling the API](../README.md#scaling-the-api) for details.

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
