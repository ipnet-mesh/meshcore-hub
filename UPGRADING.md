# Upgrading MeshCore Hub

This guide covers upgrading from a previous MeshCore Hub release to the current version. The latest release includes **breaking changes** to the MQTT broker, packet capture service, and data ingestion pipeline.

## Overview of Changes

| Area | Before | After |
|------|--------|-------|
| MQTT broker | Eclipse Mosquitto (TCP) | [meshcore-mqtt-broker](https://github.com/michaelhart/meshcore-mqtt-broker) (WebSocket, JWT auth) |
| Packet capture | Proprietary `interface-receiver` service | [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) (LetsMesh Observer model) |
| Auth model | MQTT username/password for publishing | JWT signed by device hardware public key |
| Collector MQTT | Anonymous subscriber | Subscriber account (admin-level) with credentials |
| Decoder | Node.js `meshcore-decoder` CLI subprocess | Native Python `meshcoredecoder` library |
| Python | 3.13 | 3.14 |
| DB columns | `receiver_node_id` | `observer_node_id` |
| DB table | `event_receivers` | `event_observers` |
| API commands | `/api/v1/commands/*` | Removed |
| Compose profiles | `receiver`, `sender`, `mock` | `receiver` (packet-capture) |
| Compose files | Single `docker-compose.yml` | Base + environment overrides (`.dev.yml`, `.prod.yml`) |
| Container names | `meshcore-*` | Parameterized via `COMPOSE_PROJECT_NAME` (default: `hub-dev-*`) |
| Volume names | `meshcore_*` | Parameterized via `COMPOSE_PROJECT_NAME` (default: `hub-dev_*`) |

## Step 1: Backup

**Do not skip this step.** Back up all data volumes before proceeding.

### Using Makefile

```bash
make backup
```

### Using shell commands

```bash
source .env 2>/dev/null || true
mkdir -p backup
for vol in ${COMPOSE_PROJECT_NAME:-hub-dev}_hub_data \
           ${COMPOSE_PROJECT_NAME:-hub-dev}_mqtt_broker_data \
           ${COMPOSE_PROJECT_NAME:-hub-dev}_prometheus_data \
           ${COMPOSE_PROJECT_NAME:-hub-dev}_alertmanager_data \
           ${COMPOSE_PROJECT_NAME:-hub-dev}_packetcapture_data; do
  docker run --rm -v $vol:/data -v $(pwd)/backup:/backup \
    alpine tar czf /backup/$vol-$(date +%Y%m%d-%H%M%S).tar.gz -C / data
done
```

To restore from backup if needed:

```bash
make restore FILE=backup/hub-dev_hub_data-YYYYMMDD-HHMMSS.tar.gz
```

## Step 2: Stop and Remove Containers

Stop all services and remove orphaned containers from the old configuration:

```bash
docker compose down --remove-orphans
```

> **Important:** Do NOT use `--volumes` / `-v`. That would delete your database. The `--remove-orphans` flag cleans up old services (like `interface-receiver`, `interface-sender`) that no longer exist in the new compose file.

## Step 3: Rename Docker Volumes

Container and volume names are now parameterized via `COMPOSE_PROJECT_NAME`. The default is `hub-dev`, so volumes are renamed from `meshcore_*` to `hub-dev_*`.

First, check which volumes you have:

```bash
docker volume ls | grep meshcore
```

### Volumes to migrate

These volumes always need migrating:

| Old Name | New Name |
|----------|----------|
| `meshcore_hub_data` | `hub-dev_hub_data` |
| `meshcore_prometheus_data` | `hub-dev_prometheus_data` |
| `meshcore_alertmanager_data` | `hub-dev_alertmanager_data` |
| `meshcore_packetcapture_data` | `hub-dev_packetcapture_data` |

For the MQTT broker, it depends on your current version:

| Your Current Broker | Volume to Migrate | Action |
|---------------------|-------------------|--------|
| `meshcore-mqtt-broker` | `meshcore_mqtt_broker_data` → `hub-dev_mqtt_broker_data` | Rename or copy below |
| Mosquitto (older) | `meshcore_mosquitto_data`, `meshcore_mosquitto_log` | **Remove** — no longer used. New volume created automatically on first run. |

### Option A: Rename (Docker Engine 23.0+)

> **Note:** `docker volume rename` is not available in all Docker builds (e.g., Docker Desktop). If the command is not found, use Option B instead.

```bash
docker volume rename meshcore_hub_data hub-dev_hub_data
docker volume rename meshcore_prometheus_data hub-dev_prometheus_data
docker volume rename meshcore_alertmanager_data hub-dev_alertmanager_data
docker volume rename meshcore_packetcapture_data hub-dev_packetcapture_data

# Only if you already have meshcore-mqtt-broker (skip if still on Mosquitto)
docker volume rename meshcore_mqtt_broker_data hub-dev_mqtt_broker_data
```

### Option B: Copy (all Docker versions)

If `docker volume rename` is not available in your Docker build:

```bash
# For each volume: create new, copy data, remove old
docker volume create hub-dev_hub_data
docker run --rm -v meshcore_hub_data:/from -v hub-dev_hub_data:/to alpine sh -c "cp -a /from/. /to/"

docker volume create hub-dev_prometheus_data
docker run --rm -v meshcore_prometheus_data:/from -v hub-dev_prometheus_data:/to alpine sh -c "cp -a /from/. /to/"

docker volume create hub-dev_alertmanager_data
docker run --rm -v meshcore_alertmanager_data:/from -v hub-dev_alertmanager_data:/to alpine sh -c "cp -a /from/. /to/"

docker volume create hub-dev_packetcapture_data
docker run --rm -v meshcore_packetcapture_data:/from -v hub-dev_packetcapture_data:/to alpine sh -c "cp -a /from/. /to/"

# Only if you already have meshcore-mqtt-broker (skip if still on Mosquitto)
docker volume create hub-dev_mqtt_broker_data
docker run --rm -v meshcore_mqtt_broker_data:/from -v hub-dev_mqtt_broker_data:/to alpine sh -c "cp -a /from/. /to/"

# Verify the new volumes have data, then remove old ones
docker volume rm meshcore_hub_data meshcore_prometheus_data meshcore_alertmanager_data meshcore_packetcapture_data

# Only if you already have meshcore-mqtt-broker
docker volume rm meshcore_mqtt_broker_data
```

### Clean up old Mosquitto volumes (if applicable)

If upgrading from the Mosquitto era, remove the unused volumes:

```bash
# Skip if these don't exist
docker volume rm meshcore_mosquitto_data meshcore_mosquitto_log
```

> **Note:** If any volumes show "in use", remove any stopped containers first: `docker rm -f <container_id>`.

> **Note:** If setting up a multi-instance deployment (e.g., `hub-prod`, `hub-beta`), use that project name instead of `hub-dev`.

> **Note:** After migrating volumes, you may see warnings like `volume "hub-dev_hub_data" already exists but was not created by Docker Compose. Use \`external: true\` to use an existing volume`. This is safe to ignore — it appears because the volumes were created manually during migration rather than by Docker Compose. Fresh deployments will not see this warning.

## Step 4: Update Configuration Files

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

## Step 5: Migrate Your `.env` File

### Variables to Remove

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

### Variables to Update

| Variable | Old Value | New Value | Notes |
|----------|-----------|-----------|-------|
| `MQTT_TRANSPORT` | `tcp` | `websockets` | Required by the new JWT-based broker |
| `MQTT_WS_PATH` | `/mqtt` | `/` | New broker accepts connections on `/` |

### Variables to Add

```bash
# Docker Compose project name (container and volume prefix)
COMPOSE_PROJECT_NAME=hub-dev

# MQTT subscriber authentication for the collector
# The collector connects as a subscriber to read all published topics
# including /internal. Set these to match your broker's SUBSCRIBER_1 config.
MQTT_USERNAME=subscriber

# Generate a secure password (do not use a simple password in production):
#   openssl rand -base64 32
MQTT_PASSWORD=<generate-a-secure-password>

# JWT audience claim for packet capture authentication tokens
# Must match AUTH_EXPECTED_AUDIENCE on the broker
MQTT_TOKEN_AUDIENCE=mqtt.localhost

# IATA airport code for your observer location (required for packet capture)
# Use the 3-letter code for the nearest airport.
# Look up your code: https://www.iata.org/en/publications/directories/code-search/
PACKETCAPTURE_IATA=LOC
```

All other `PACKETCAPTURE_*` variables have sensible defaults in `docker-compose.yml` and only need to be set in `.env` if you want to override them. See `.env.example` for the full list.

## Step 6: Run Database Migration

The migration renames `receiver_node_id` → `observer_node_id` across all event tables and `event_receivers` → `event_observers`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core run --rm db-migrate
```

This runs automatically as part of the `core` profile, but can also be run standalone with the `migrate` profile:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile migrate run --rm db-migrate
```

## Step 7: Start Services

### With local MQTT broker (single-host deployment)

```bash
# Start everything including the MQTT broker
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mqtt --profile core up -d

# Or include packet capture on the same host
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mqtt --profile core --profile receiver up -d
```

### With external MQTT broker

```bash
# Start core services only (broker runs elsewhere)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core up -d
```

### Verify

```bash
# Check all containers are running
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps

# Check collector connected to MQTT
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs collector | grep -i "connected to mqtt"

# Check the web dashboard
open http://localhost:8080
```

## Notes

### JWT-Based Packet Capture Authentication

The new packet capture service ([meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture)) uses the LetsMesh Observer model:

- **No custom MQTT credentials needed for publishing.** Authentication is handled via JWT tokens signed by the capture device's hardware public key. The MQTT broker validates the JWT and authorizes publishing automatically.
- The collector connects as a **subscriber** to read all published events, including `/internal` topics. Configure `MQTT_USERNAME` and `MQTT_PASSWORD` to match the broker's subscriber account.

### Production MQTT Configuration

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

### Existing LetsMesh Observer Installs

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

### Removed Services

The following Docker Compose services have been removed:

| Old Service | Replacement |
|-------------|-------------|
| `interface-receiver` | `packet-capture` (profile: `receiver`) |
| `interface-sender` | None (removed) |
| `interface-mock-receiver` | None (removed) |

The `packet-capture` service uses the [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) image and is included in `docker-compose.yml` under the `receiver` profile for an easy transition.

### New Docker Compose File Structure

The Docker Compose configuration is now split into multiple files:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base shared config (services, profiles, healthchecks, environment) |
| `docker-compose.dev.yml` | Development overrides (port mappings for direct access) |
| `docker-compose.prod.yml` | Production overrides (external proxy network, no exposed ports) |
| `docker-compose.traefik.yml` | Optional Traefik auto-discovery labels |

All `docker compose` commands now require explicit file selection:

```bash
# Development (exposes ports for local access)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production (connects to reverse proxy network)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Production with Traefik
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.traefik.yml up -d
```

Container and volume names are parameterized via `COMPOSE_PROJECT_NAME` in `.env`. This enables multiple instances (e.g., `hub-prod`, `hub-beta`) on the same Docker host.

### Removed API Endpoints

The command dispatch API endpoints have been removed:

- `POST /api/v1/commands/send-message`
- `POST /api/v1/commands/send-channel-message`
- `POST /api/v1/commands/send-advertisement`

### Native Python Decoder

The Node.js `meshcore-decoder` CLI tool has been replaced by the native Python `meshcoredecoder` library. This means:

- No Node.js runtime is needed in the Docker image
- The decoder is always enabled (no toggle)
- The `COLLECTOR_LETSMESH_DECODER_*` configuration variables have been removed
- `COLLECTOR_LETSMESH_DECODER_KEYS` is still supported for providing additional channel decryption keys
