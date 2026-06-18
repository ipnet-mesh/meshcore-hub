# Configuration

This document is the **single source of truth** for MeshCore Hub environment variables. Copy `.env.example` to `.env` and override the values you need; `.env.example` stays the commented template and this document stays the canonical reference.

Variables are grouped by feature. Each section below links to the feature's dedicated document (where one exists) for setup, architecture, and operational details. The companion documents no longer duplicate these tables — they link back here.

> **Cross-references:** [deployment.md](deployment.md) (production setup, scaling, Redis operational notes) · [database.md](database.md) (backend setup, migration runbook) · [observer.md](observer.md) (packet-capture observer vars, which live there because they configure an external image) · [auth.md](auth.md) (OIDC architecture, IdP guides) · [webhooks.md](webhooks.md) (payload format, URL routing) · [letsmesh.md](letsmesh.md) (packet decoding) · [content.md](content.md) (custom pages, media, logos) · [i18n.md](i18n.md) (translations) · [seeding.md](seeding.md) (seed YAML) · [maintenance.md](maintenance.md) (backup/restore)

---

## Common

Process-wide and MQTT-broker settings used by every service. For multi-instance Docker deployments, see [deployment.md → Multi-Instance Deployments](deployment.md#multi-instance-deployments); for seed data, see [seeding.md](seeding.md).

| Variable | Default | Description |
| --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | `hub` | Docker Compose project name; prefixes container and volume names. Change per instance when running multiple deployments on the same host |
| `IMAGE_VERSION` | `latest` | Docker image tag to use (`latest`, `main`, `v1.0.0`, etc.) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `DATA_HOME` | `./data` | Base directory for runtime data (the SQLite file lives under `${DATA_HOME}/collector/meshcore.db`) |
| `SEED_HOME` | `./seed` | Directory containing seed data files |
| `TZ` | `UTC` | IANA timezone for displaying dates/times (e.g. `America/New_York`, `Europe/London`) |
| `MQTT_HOST` | `localhost` (`mqtt` in Docker) | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port (production behind reverse proxy: `443`) |
| `MQTT_USERNAME` | _(none)_ | MQTT username (subscriber account on the MeshCore broker) |
| `MQTT_PASSWORD` | _(none)_ | MQTT password (generate with `openssl rand -base64 32`) |
| `MQTT_PREFIX` | `meshcore` | Topic prefix for all MQTT messages (legacy alias: `MQTT_TOPIC_PREFIX`) |
| `MQTT_TLS` | `false` | Enable TLS/SSL for MQTT connection (set `true` for `wss://`) |
| `MQTT_TRANSPORT` | `websockets` | MQTT transport protocol (the MeshCore broker uses WebSockets exclusively) |
| `MQTT_WS_PATH` | `/` | MQTT WebSocket path (production: `/mqtt` if reverse proxy rewrites paths) |
| `MQTT_TOKEN_AUDIENCE` | `mqtt.localhost` | JWT audience claim for packet-capture authentication tokens; must match `AUTH_EXPECTED_AUDIENCE` on the broker |

> **Timezone note:** API timestamps that omit an explicit timezone suffix are treated as UTC before rendering in the configured `TZ`.

## Database

MeshCore Hub defaults to **SQLite** (zero-config, single host). Set `DATABASE_BACKEND=postgres` to switch to **PostgreSQL** for write scaling, multi-host deployments, and multiple instances sharing one cluster via schema-per-instance. Postgres is opt-in — leave the `DATABASE_*` variables unset to keep using SQLite. See [database.md](database.md) for the full backend reference: bundled container, production role/database provisioning, managed/external Postgres, schema-per-instance isolation, and the SQLite → PostgreSQL migration runbook.

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_BACKEND` | `sqlite` | `sqlite` or `postgres`. Explicit switch — Postgres is never selected implicitly |
| `DATABASE_HOST` | `postgres` | Postgres hostname (`postgres` = bundled container service name) |
| `DATABASE_PORT` | `5432` | Postgres port |
| `DATABASE_NAME` | `meshcorehub` | Database name |
| `DATABASE_SCHEMA` | `meshcorehub` | Schema (`search_path`). Set a distinct value per instance on a shared cluster |
| `DATABASE_USER` | `meshcorehub` | Role name |
| `DATABASE_PASSWORD` | _(none)_ | **Required** for Postgres. Generate one, e.g. `openssl rand -base64 32` |
| `DATABASE_URL` | _(none)_ | Advanced: full SQLAlchemy URL; overrides all of the above |

The bundled `postgres` container derives its `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from the same `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME` values — one source of truth.

## Caching

Optional Redis-backed caching for API responses. When disabled or unavailable, the API queries the database directly. Operational guidance — Docker `cache` profile, bare-metal Redis, and multi-instance key-prefix isolation — is in [deployment.md → Redis Caching](deployment.md#redis-caching).

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_ENABLED` | `false` | Enable Redis API response caching |
| `REDIS_HOST` | `localhost` (`redis` in Docker) | Redis server host |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_PASSWORD` | _(none)_ | Redis password (optional) |
| `REDIS_KEY_PREFIX` | `hub` | Cache key prefix for multi-instance isolation |
| `REDIS_CACHE_TTL` | `30` | Default cache TTL in seconds |
| `REDIS_CACHE_TTL_DASHBOARD` | `30` | Cache TTL for dashboard endpoints in seconds |

## Collector

The collector subscribes to MQTT events and persists them to the database. For packet decoding behaviour, channel-key handling, and LetsMesh normalisation, see [letsmesh.md](letsmesh.md).

| Variable | Default | Description |
| --- | --- | --- |
| `CHANNEL_REFRESH_INTERVAL_SECONDS` | `300` | Seconds between channel-key refresh from the database (minimum `10`) |

## Webhooks

The collector can forward events (advertisements, messages) to external HTTP endpoints via webhooks with configurable URLs, secrets, retries, and timeouts. For URL routing rules, secret handling, retry behaviour, and payload format, see [webhooks.md](webhooks.md).

| Variable | Default | Description |
| --- | --- | --- |
| `WEBHOOK_ADVERTISEMENT_URL` | _(none)_ | Webhook URL for advertisement events |
| `WEBHOOK_ADVERTISEMENT_SECRET` | _(none)_ | Secret sent as `X-Webhook-Secret` header |
| `WEBHOOK_MESSAGE_URL` | _(none)_ | Webhook URL for all message events |
| `WEBHOOK_MESSAGE_SECRET` | _(none)_ | Secret for message webhook |
| `WEBHOOK_CHANNEL_MESSAGE_URL` | _(none)_ | Override URL for channel messages only |
| `WEBHOOK_CHANNEL_MESSAGE_SECRET` | _(none)_ | Secret for channel message webhook |
| `WEBHOOK_DIRECT_MESSAGE_URL` | _(none)_ | Override URL for direct messages only |
| `WEBHOOK_DIRECT_MESSAGE_SECRET` | _(none)_ | Secret for direct message webhook |
| `WEBHOOK_TIMEOUT` | `10.0` | Request timeout in seconds |
| `WEBHOOK_MAX_RETRIES` | `3` | Max retry attempts on failure |
| `WEBHOOK_RETRY_BACKOFF` | `2.0` | Exponential backoff multiplier |

## Auth

The web dashboard supports OIDC/OAuth2 authentication. When enabled (`OIDC_ENABLED=true`), the admin interface requires users to authenticate with an identity provider and have the `admin` role assigned. See [auth.md](auth.md) for the architecture, login flow, role/endpoint mapping, local-development notes, and IdP-specific guides (LogTo, etc.).

| Variable | Default | Description |
| --- | --- | --- |
| `OIDC_ENABLED` | `false` | Enable OIDC authentication |
| `OIDC_CLIENT_ID` | _(none)_ | OAuth2 client ID from your IdP (required when enabled) |
| `OIDC_CLIENT_SECRET` | _(none)_ | OAuth2 client secret from your IdP (required when enabled) |
| `OIDC_DISCOVERY_URL` | _(none)_ | IdP base URL — `.well-known/openid-configuration` is appended automatically (required when enabled) |
| `OIDC_REDIRECT_URI` | _(auto-derived)_ | Override callback URL (auto-derived from request if not set) |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | _(auto-derived)_ | Post-logout redirect URI (falls back to `OIDC_REDIRECT_URI` base or request URL) |
| `OIDC_SCOPES` | `openid email profile` | OAuth scopes to request. The `openid` scope is required. Quotes are stripped automatically |
| `OIDC_ROLES_CLAIM` | `roles` | ID token claim name containing user roles |
| `OIDC_ROLE_ADMIN` | `admin` | IdP role name granting admin access |
| `OIDC_ROLE_OPERATOR` | `operator` | IdP role name for operator access (future use) |
| `OIDC_ROLE_MEMBER` | `member` | IdP role name for member access |
| `OIDC_ROLE_TEST` | `test` | IdP role name for test users (excluded from public member views and counts) |
| `OIDC_SESSION_SECRET` | _(none)_ | Secret for signing session cookies (generate with `openssl rand -hex 32`; required when enabled) |
| `OIDC_SESSION_MAX_AGE` | `86400` | Session cookie lifetime in seconds (default 24 hours) |
| `OIDC_COOKIE_SECURE` | `false` | Set `true` to require HTTPS for session cookies (enable in production) |

## Data Retention

The collector automatically cleans up old event data and inactive nodes. Retention cleanup runs on the collector's scheduled cycle regardless of whether capture is currently enabled.

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_RETENTION_ENABLED` | `true` | Enable automatic cleanup of old events |
| `DATA_RETENTION_DAYS` | `30` | Days to retain event data |
| `DATA_RETENTION_INTERVAL_HOURS` | `24` | Hours between cleanup runs (applies to both event data and node cleanup) |
| `NODE_CLEANUP_ENABLED` | `true` | Enable removal of inactive nodes (nodes with `last_seen=NULL` are never removed) |
| `NODE_CLEANUP_DAYS` | `30` | Remove nodes not seen for this many days |
| `RAW_PACKET_CAPTURE_ENABLED` | `false` | Capture raw packets into `raw_packets`. In Compose, derived from `FEATURE_PACKETS` — see [letsmesh.md → Raw Packet Capture](letsmesh.md#raw-packet-capture) |
| `RAW_PACKET_RETENTION_DAYS` | `7` | Days to retain raw packets (independent of `DATA_RETENTION_DAYS`) |

## API

REST API server. For multi-worker scaling guidance (`API_WORKERS`), see [deployment.md → Scaling the API](deployment.md#scaling-the-api).

| Variable | Default | Description |
| --- | --- | --- |
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |
| `API_WORKERS` | `1` | Number of worker processes (increase for multi-core concurrency) |
| `API_READ_KEY` | _(none)_ | Read-only API key (generate with `openssl rand -hex 32`) |
| `API_ADMIN_KEY` | _(none)_ | Admin API key |
| `METRICS_ENABLED` | `true` | Enable Prometheus metrics endpoint at `/metrics` |
| `METRICS_CACHE_TTL` | `60` | Seconds to cache metrics output (reduces database load) |
| `CORS_ORIGINS` | _(none)_ | Comma-separated list of allowed CORS origins (only needed when the web dashboard runs on a different origin) |

## Web Dashboard

Web server, dashboard presentation, network metadata, and custom content. For the custom content directory layout (pages, media, logos), see [content.md](content.md); for translations and `WEB_LOCALE` values, see [i18n.md](i18n.md).

| Variable | Default | Description |
| --- | --- | --- |
| `WEB_HOST` | `0.0.0.0` | Web server bind address |
| `WEB_PORT` | `8080` | Web server port |
| `API_BASE_URL` | `http://localhost:8000` | API endpoint URL |
| `API_KEY` | _(none)_ | API key for web dashboard queries (optional — set if `API_READ_KEY` is set on the API) |
| `WEB_THEME` | `dark` | Default theme (`dark` or `light`); users can override via the navbar toggle |
| `WEB_LOCALE` | `en` | Locale/language for the web dashboard (e.g. `en`, `nl`) |
| `WEB_DATETIME_LOCALE` | `en-US` | Locale used for date formatting (e.g. `en-US` for MM/DD/YYYY, `en-GB` for DD/MM/YYYY) |
| `WEB_AUTO_REFRESH_SECONDS` | `30` | Auto-refresh interval in seconds for list pages (`0` to disable) |
| `WEB_DEBUG` | `false` | Enable debug mode in the web dashboard (extra diagnostic info) |
| `NETWORK_DOMAIN` | _(none)_ | Network domain name (optional) |
| `NETWORK_NAME` | `MeshCore Network` | Display name for the network |
| `NETWORK_CITY` | _(none)_ | City where network is located |
| `NETWORK_COUNTRY` | _(none)_ | Country code (ISO 3166-1 alpha-2) |
| `NETWORK_RADIO_PROFILE` | `EU/UK Narrow` | Radio profile name |
| `NETWORK_RADIO_FREQUENCY` | `869.618` | Radio frequency in MHz (raw number, units applied on display) |
| `NETWORK_RADIO_BANDWIDTH` | `62.5` | Radio bandwidth in kHz (raw number, units applied on display) |
| `NETWORK_RADIO_SPREADING_FACTOR` | `8` | Radio spreading factor |
| `NETWORK_RADIO_CODING_RATE` | `8` | Radio coding rate |
| `NETWORK_RADIO_TX_POWER` | `22` | Radio TX power in dBm (raw number, units applied on display) |
| `NETWORK_WELCOME_TEXT` | _(none)_ | Custom welcome text for homepage |
| `NETWORK_CONTACT_EMAIL` | _(none)_ | Contact email address |
| `NETWORK_CONTACT_DISCORD` | _(none)_ | Discord server link |
| `NETWORK_CONTACT_GITHUB` | _(none)_ | GitHub repository URL |
| `NETWORK_CONTACT_YOUTUBE` | _(none)_ | YouTube channel URL |
| `NETWORK_ANNOUNCEMENT` | _(none)_ | Markdown announcement shown as a dismissable flash banner on every page |
| `SYSTEM_ANNOUNCEMENT` | _(none)_ | Markdown system notice shown as a non-dismissable banner above the network announcement |
| `SYSTEM_MAINTENANCE` | `false` | Maintenance mode: nav shows only Home, profile menu hidden, every page renders a maintenance notice, and no API calls are made |
| `CONTENT_HOME` | `./content` | Directory containing custom content (pages/, media/) |

## Feature Flags

Control which pages are visible in the web dashboard. Disabled features are fully hidden: removed from navigation, return 404 on their routes, and excluded from sitemap/robots.txt.

| Variable | Default | Description |
| --- | --- | --- |
| `FEATURE_DASHBOARD` | `true` | Enable the `/dashboard` page |
| `FEATURE_NODES` | `true` | Enable the `/nodes` pages (list, detail, short links) |
| `FEATURE_ADVERTISEMENTS` | `true` | Enable the `/advertisements` page |
| `FEATURE_MESSAGES` | `true` | Enable the `/messages` page |
| `FEATURE_MAP` | `true` | Enable the `/map` page and `/map/data` endpoint |
| `FEATURE_MEMBERS` | `true` | Enable the `/members` page |
| `FEATURE_PAGES` | `true` | Enable custom markdown pages |
| `FEATURE_CHANNELS` | `true` | Enable the `/channels` page |
| `FEATURE_RADIO_CONFIG` | `true` | Show radio config panel on home page |
| `FEATURE_PACKETS` | `true` | Enable the `/packets` raw-packet browser. In Compose this also drives `RAW_PACKET_CAPTURE_ENABLED` on the collector |

**Dependencies:** Dashboard auto-disables when all of Nodes/Advertisements/Messages are disabled. Map auto-disables when Nodes is disabled. Members auto-disables when OIDC is disabled (set via `OIDC_ENABLED`).

## Traefik

Optional. Only relevant when using `docker-compose.traefik.yml` for reverse-proxy auto-discovery. See [deployment.md → Reverse Proxy](deployment.md#reverse-proxy) and [Multi-Instance Deployments](deployment.md#multi-instance-deployments) for usage.

| Variable | Default | Description |
| --- | --- | --- |
| `TRAEFIK_DOMAIN` | _(none)_ | Domain routed by Traefik (e.g. `meshcore.example.com`) |
| `TRAEFIK_PRIORITY` | `10` | Router priority — higher wins on overlapping domains. Use higher values for more specific subdomains (staging `20`, MQTT broker `30`) |

## Prometheus & Alertmanager

Optional. External monitoring ports used by the `metrics` compose profile. The MeshCore Hub application itself does not consume these; they configure the bundled monitoring containers.

| Variable | Default | Description |
| --- | --- | --- |
| `PROMETHEUS_PORT` | `9090` | External Prometheus port (when using `--profile metrics`) |
| `ALERTMANAGER_PORT` | `9093` | External Alertmanager port (when using `--profile metrics`) |
