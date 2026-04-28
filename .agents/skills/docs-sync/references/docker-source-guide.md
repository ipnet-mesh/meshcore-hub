# Docker Source Guide

How to extract Docker configuration from all Compose files and verify documentation accuracy.

## Compose Files

| File | Purpose | Scope |
|------|---------|-------|
| `docker-compose.yml` | Base shared config | All services, profiles, volumes |
| `docker-compose.dev.yml` | Development overrides | Port mappings, dev dependencies |
| `docker-compose.prod.yml` | Production overrides | External proxy network |
| `docker-compose.traefik.yml` | Traefik auto-discovery labels | HTTP routing, TLS |

**Out of scope:** `tests/e2e/docker-compose.test.yml` is a test fixture with hardcoded values. Do NOT audit it against documentation.

## Services

### Service Inventory

Extract from `docker-compose.yml`:

| Service | Image | Profiles | Command |
|---------|-------|----------|---------|
| `mqtt` | `ghcr.io/ipnet-mesh/meshcore-mqtt-broker:latest` | `all`, `mqtt` | (default) |
| `observer` | `ghcr.io/agessaman/meshcore-packet-capture:${PACKETCAPTURE_IMAGE_VERSION}` | `all`, `observer` | (default) |
| `collector` | `ghcr.io/ipnet-mesh/meshcore-hub:${IMAGE_VERSION}` | `all`, `core` | `["collector"]` |
| `api` | `ghcr.io/ipnet-mesh/meshcore-hub:${IMAGE_VERSION}` | `all`, `core` | `["api"]` |
| `web` | `ghcr.io/ipnet-mesh/meshcore-hub:${IMAGE_VERSION}` | `all`, `core` | `["web"]` |
| `migrate` | `ghcr.io/ipnet-mesh/meshcore-hub:${IMAGE_VERSION}` | `all`, `core`, `migrate` | `["db", "upgrade"]` |
| `seed` | `ghcr.io/ipnet-mesh/meshcore-hub:${IMAGE_VERSION}` | `seed` | `["collector", "seed"]` |

### Verification Checklist

For each service, verify documentation includes:
- [ ] Service name and purpose
- [ ] Correct compose profile membership
- [ ] Dependencies (`depends_on`)
- [ ] Volumes mounted
- [ ] Key environment variables

## Compose Profiles

Extract from `docker-compose.yml` `profiles:` keys:

| Profile | Services | Use Case |
|---------|----------|----------|
| `all` | mqtt, observer, collector, api, web, migrate | Everything on one host |
| `core` | collector, api, web, migrate | Central server (no local MQTT or observer) |
| `mqtt` | mqtt | Local MQTT broker only |
| `observer` | observer | Packet capture observer only |
| `migrate` | migrate | Database migration only |
| `seed` | seed | Seed data import only |

### Verification

- [ ] Profile table in README.md matches compose file
- [ ] Profile table in AGENTS.md matches compose file
- [ ] All profile names documented
- [ ] All services within each profile listed
- [ ] Use cases described accurately

## Volumes

### Named Volumes

| Volume | Services | Purpose |
|--------|----------|---------|
| `data` | collector, api, migrate, seed | SQLite database + runtime data |
| `mqtt_data` | mqtt | MQTT broker persistence |
| `observer_data` | observer | Packet capture data |

Volume names are prefixed: `${COMPOSE_PROJECT_NAME:-hub}_data`, `${COMPOSE_PROJECT_NAME:-hub}_mqtt_data`, etc.

### Bind Mounts

| Host Path | Container Path | Service | Mode |
|-----------|---------------|---------|------|
| `${SEED_HOME:-./seed}` | `/seed` | collector | rw |
| `${SEED_HOME:-./seed}` | `/seed` | seed | ro |
| `${CONTENT_HOME:-./content}` | `/content` | web | ro |

### Verification

- [ ] All named volumes documented in README.md
- [ ] Bind mount paths match `SEED_HOME` and `CONTENT_HOME` env var defaults
- [ ] Volume naming convention (COMPOSE_PROJECT_NAME prefix) documented

## Port Mappings

### Development (docker-compose.dev.yml)

| Service | Host Port | Container Port | Variable |
|---------|-----------|----------------|----------|
| mqtt | `${MQTT_PORT:-1883}` | `${MQTT_PORT:-1883}` | `MQTT_PORT` |
| api | `${API_PORT:-8000}` | `8000` | `API_PORT` |
| web | `${WEB_PORT:-8080}` | `8080` | `WEB_PORT` |

### Production (docker-compose.prod.yml)

No ports exposed. Services connect to external `proxy-net` Docker network.

### Traefik (docker-compose.traefik.yml)

Routing via labels. API handles `/api`, `/metrics`, `/health`. Web handles everything else.

### Verification

- [ ] Port mappings in README.md match `docker-compose.dev.yml`
- [ ] Production routing description matches `docker-compose.traefik.yml`
- [ ] Container ports match `Dockerfile` exposed ports (8000, 8080)

## Environment Variables in Docker

### Per-Service Env Var Extraction

For each service's `environment:` block, extract every variable. Classify each:

**Hardcoded (container-internal):** Set to a fixed value in compose file, not configurable via `.env`. These should NOT appear in `.env.example` but SHOULD be noted in README.md service descriptions.
- Example: `DATA_HOME=/data` (collector), `API_HOST=0.0.0.0` (api), `CONTENT_HOME=/content` (web)

**Variable substitution (user-configurable):** Use `${VAR:-default}` syntax. These MUST appear in `.env.example` with the same default.
- Example: `MQTT_HOST=${MQTT_HOST:-mqtt}`, `LOG_LEVEL=${LOG_LEVEL:-INFO}`

**Passthrough (no default):** Reference `${VAR}` without a default. These MUST appear in `.env.example` (typically commented out or with empty value).
- Example: `API_READ_KEY`, `API_ADMIN_KEY`, `WEBHOOK_ADVERTISEMENT_URL`

### Collector Service Env Vars

Complete list from `docker-compose.yml` collector `environment:` block:

| Variable | Default in Compose | Category |
|----------|--------------------|----------|
| `LOG_LEVEL` | `INFO` | Common |
| `MQTT_HOST` | `mqtt` | MQTT |
| `MQTT_PORT` | `1883` | MQTT |
| `MQTT_USERNAME` | (empty) | MQTT |
| `MQTT_PASSWORD` | (empty) | MQTT |
| `MQTT_PREFIX` | `meshcore` | MQTT |
| `MQTT_TLS` | `false` | MQTT |
| `MQTT_TRANSPORT` | `websockets` | MQTT |
| `MQTT_WS_PATH` | `/` | MQTT |
| `DATA_HOME` | `/data` (hardcoded) | Path |
| `SEED_HOME` | `/seed` (hardcoded) | Path |
| `COLLECTOR_CHANNEL_KEYS` | (empty) | Collector |
| `COLLECTOR_INCLUDE_TEST_CHANNEL` | `false` | Collector |
| `WEBHOOK_ADVERTISEMENT_URL` | (passthrough) | Webhook |
| `WEBHOOK_ADVERTISEMENT_SECRET` | (passthrough) | Webhook |
| `WEBHOOK_MESSAGE_URL` | (passthrough) | Webhook |
| `WEBHOOK_MESSAGE_SECRET` | (passthrough) | Webhook |
| `WEBHOOK_CHANNEL_MESSAGE_URL` | (passthrough) | Webhook |
| `WEBHOOK_CHANNEL_MESSAGE_SECRET` | (passthrough) | Webhook |
| `WEBHOOK_DIRECT_MESSAGE_URL` | (passthrough) | Webhook |
| `WEBHOOK_DIRECT_MESSAGE_SECRET` | (passthrough) | Webhook |
| `WEBHOOK_TIMEOUT` | `10.0` | Webhook |
| `WEBHOOK_MAX_RETRIES` | `3` | Webhook |
| `WEBHOOK_RETRY_BACKOFF` | `2.0` | Webhook |
| `DATA_RETENTION_ENABLED` | `true` | Retention |
| `DATA_RETENTION_DAYS` | `30` | Retention |
| `DATA_RETENTION_INTERVAL_HOURS` | `24` | Retention |
| `NODE_CLEANUP_ENABLED` | `true` | Node Cleanup |
| `NODE_CLEANUP_DAYS` | `7` | Node Cleanup |

### API Service Env Vars

| Variable | Default in Compose | Category |
|----------|--------------------|----------|
| `LOG_LEVEL` | `INFO` | Common |
| `MQTT_HOST` | `mqtt` | MQTT |
| `MQTT_PORT` | `1883` | MQTT |
| `MQTT_USERNAME` | (empty) | MQTT |
| `MQTT_PASSWORD` | (empty) | MQTT |
| `MQTT_PREFIX` | `meshcore` | MQTT |
| `MQTT_TLS` | `false` | MQTT |
| `MQTT_TRANSPORT` | `websockets` | MQTT |
| `MQTT_WS_PATH` | `/` | MQTT |
| `DATA_HOME` | `/data` (hardcoded) | Path |
| `API_HOST` | `0.0.0.0` (hardcoded) | API |
| `API_PORT` | `8000` (hardcoded) | API |
| `API_READ_KEY` | (passthrough) | Auth |
| `API_ADMIN_KEY` | (passthrough) | Auth |
| `METRICS_ENABLED` | `true` | Metrics |
| `METRICS_CACHE_TTL` | `60` | Metrics |

### Web Service Env Vars

| Variable | Default in Compose | Category |
|----------|--------------------|----------|
| `LOG_LEVEL` | `INFO` | Common |
| `API_BASE_URL` | `http://api:8000` (hardcoded) | API |
| `API_ADMIN_KEY` / `API_READ_KEY` | (cascading passthrough) | Auth |
| `WEB_HOST` | `0.0.0.0` (hardcoded) | Web |
| `WEB_PORT` | `8080` (hardcoded) | Web |
| `WEB_THEME` | `dark` | Theme |
| `WEB_LOCALE` | `en` | Locale |
| `WEB_DATETIME_LOCALE` | `en-US` | Locale |
| `OIDC_ENABLED` | `false` | Auth |
| `OIDC_CLIENT_ID` | (empty) | Auth |
| `OIDC_CLIENT_SECRET` | (empty) | Auth |
| `OIDC_DISCOVERY_URL` | (empty) | Auth |
| `OIDC_REDIRECT_URI` | (empty) | Auth |
| `OIDC_SCOPES` | `openid email profile` | Auth |
| `OIDC_ROLES_CLAIM` | `roles` | Auth |
| `OIDC_ADMIN_ROLE` | `admin` | Auth |
| `OIDC_MEMBER_ROLE` | `member` | Auth |
| `OIDC_SESSION_SECRET` | (empty) | Auth |
| `OIDC_SESSION_MAX_AGE` | `86400` | Auth |
| `OIDC_COOKIE_SECURE` | `false` | Auth |
| `NETWORK_NAME` | `MeshCore Network` | Network |
| `NETWORK_CITY` | (empty) | Network |
| `NETWORK_COUNTRY` | (empty) | Network |
| `NETWORK_RADIO_CONFIG` | (empty) | Network |
| `NETWORK_CONTACT_EMAIL` | (empty) | Network |
| `NETWORK_CONTACT_DISCORD` | (empty) | Network |
| `NETWORK_CONTACT_GITHUB` | (empty) | Network |
| `NETWORK_CONTACT_YOUTUBE` | (empty) | Network |
| `NETWORK_WELCOME_TEXT` | (empty) | Network |
| `CONTENT_HOME` | `/content` (hardcoded) | Path |
| `TZ` | `UTC` | Display |
| `COLLECTOR_CHANNEL_KEYS` | (empty) | Display |
| `COLLECTOR_INCLUDE_TEST_CHANNEL` | `false` | Display |
| `FEATURE_DASHBOARD` | `true` | Feature |
| `FEATURE_NODES` | `true` | Feature |
| `FEATURE_ADVERTISEMENTS` | `true` | Feature |
| `FEATURE_MESSAGES` | `true` | Feature |
| `FEATURE_MAP` | `true` | Feature |
| `FEATURE_MEMBERS` | `true` | Feature |
| `FEATURE_PAGES` | `true` | Feature |

### Observer (Packet Capture) Env Vars

These are ALL passthrough vars consumed by the external packet capture image. None are read by Hub Python code.

Grouped by function:
- **Connection:** `SERIAL_PORT`, `PACKETCAPTURE_TIMEOUT`, `PACKETCAPTURE_MAX_CONNECTION_RETRIES`, `PACKETCAPTURE_CONNECTION_RETRY_DELAY`, `PACKETCAPTURE_HEALTH_CHECK_INTERVAL`
- **Identity:** `PACKETCAPTURE_IATA`, `PACKETCAPTURE_ORIGIN`
- **Behavior:** `PACKETCAPTURE_ADVERT_INTERVAL_HOURS`, `PACKETCAPTURE_RF_DATA_TIMEOUT`
- **MQTT Broker 1 (Let's Mesh US):** `PACKETCAPTURE_MQTT1_ENABLED`, `PACKETCAPTURE_MQTT1_SERVER`, `PACKETCAPTURE_MQTT1_PORT`, `PACKETCAPTURE_MQTT1_USE_TLS`, `PACKETCAPTURE_MQTT1_USE_AUTH_TOKEN`, `PACKETCAPTURE_MQTT1_TOKEN_AUDIENCE`, `PACKETCAPTURE_MQTT1_KEEPALIVE`
- **MQTT Broker 2 (Let's Mesh EU):** `PACKETCAPTURE_MQTT2_ENABLED`, `PACKETCAPTURE_MQTT2_SERVER`, `PACKETCAPTURE_MQTT2_PORT`, `PACKETCAPTURE_MQTT2_USE_TLS`, `PACKETCAPTURE_MQTT2_USE_AUTH_TOKEN`, `PACKETCAPTURE_MQTT2_TOKEN_AUDIENCE`, `PACKETCAPTURE_MQTT2_KEEPALIVE`
- **MQTT Broker 3 (Local):** `PACKETCAPTURE_MQTT3_ENABLED`, `PACKETCAPTURE_MQTT3_KEEPALIVE`
- **MQTT Reconnection:** `PACKETCAPTURE_MAX_MQTT_RETRIES`, `PACKETCAPTURE_MQTT_RETRY_DELAY`, `PACKETCAPTURE_EXIT_ON_RECONNECT_FAIL`

Note: Broker 3 is wired to hub's MQTT vars: `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TLS`, `MQTT_TOKEN_AUDIENCE`.

## Infrastructure-Only Variables

These appear in `.env.example` and compose files but are NOT consumed by any Python code:

| Variable | Consumer | Default |
|----------|----------|---------|
| `COMPOSE_PROJECT_NAME` | Docker Compose | `hub` |
| `IMAGE_VERSION` | Docker Compose | `latest` |
| `PACKETCAPTURE_IMAGE_VERSION` | Docker Compose | `latest` |
| `TRAEFIK_DOMAIN` | Traefik labels | (required when using traefik compose) |
| `SERIAL_PORT` | Observer container + device mapping | `/dev/ttyUSB0` |
| `MQTT_TOKEN_AUDIENCE` | MQTT broker container | `mqtt.localhost` |
| `PROMETHEUS_PORT` | Docker port mapping | `9090` |
| `ALERTMANAGER_PORT` | Docker port mapping | `9093` |

These MUST be in `.env.example` and README.md but NOT in AGENTS.md "Environment Variables" section (since AGENTS.md documents Hub-consumed vars).

## Dockerfile Verification

The `Dockerfile` sets ENV defaults that should match compose file defaults:

| Dockerfile ENV | Value | Must Match |
|----------------|-------|------------|
| `LOG_LEVEL` | `INFO` | Compose `LOG_LEVEL` default |
| `MQTT_HOST` | `mqtt` | Compose `MQTT_HOST` default |
| `MQTT_PORT` | `1883` | Compose `MQTT_PORT` default |
| `MQTT_PREFIX` | `meshcore` | Compose `MQTT_PREFIX` default |
| `DATA_HOME` | `/data` | Compose hardcoded `DATA_HOME` |
| `API_HOST` | `0.0.0.0` | Compose hardcoded `API_HOST` |
| `API_PORT` | `8000` | Compose hardcoded `API_PORT` |
| `WEB_HOST` | `0.0.0.0` | Compose hardcoded `WEB_HOST` |
| `WEB_PORT` | `8080` | Compose hardcoded `WEB_PORT` |
| `API_BASE_URL` | `http://api:8000` | Compose hardcoded `API_BASE_URL` |

## Inline Comment Verification

For `docker-compose.yml` and `.env.example`, verify every `# comment` accurately describes the value it annotates. Check:

1. **Default values in comments** match actual `${VAR:-default}` values
2. **Descriptions** accurately describe what the variable does
3. **Section headers** correctly group related variables
4. **References** to other files or sections are still valid (e.g., "see README.md" references)
5. **Examples** use current, valid values (not outdated formats)
