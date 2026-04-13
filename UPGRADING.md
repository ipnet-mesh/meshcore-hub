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

## Step 1: Backup the Database

**Do not skip this step.** The database migration renames columns and tables, and while it has been tested, you should always have a backup.

```bash
# Create a timestamped backup of the database volume
docker run --rm \
  -v meshcore_hub_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/meshcore-hub-db-$(date +%Y%m%d-%H%M%S).tar.gz -C / data

# Verify the backup was created
ls -lh meshcore-hub-db-*.tar.gz
```

To restore from backup if needed:

```bash
docker run --rm \
  -v meshcore_hub_data:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd / && tar xzf /backup/meshcore-hub-db-YYYYMMDD-HHMMSS.tar.gz"
```

## Step 2: Stop and Remove Containers

Stop all services and remove orphaned containers from the old configuration:

```bash
docker compose down --remove-orphans
```

> **Important:** Do NOT use `--volumes` / `-v`. That would delete your database. The `--remove-orphans` flag cleans up old services (like `interface-receiver`, `interface-sender`) that no longer exist in the new compose file.

## Step 3: Update Configuration Files

Download the latest configuration files:

```bash
# Download the new docker-compose.yml
wget -O docker-compose.yml https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/docker-compose.yml

# Download the new .env.example for reference
wget -O .env.example https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/.env.example
```

Then compare your existing `.env` against the new `.env.example` and update it (see Step 4).

## Step 4: Migrate Your `.env` File

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

## Step 5: Run Database Migration

The migration renames `receiver_node_id` → `observer_node_id` across all event tables and `event_receivers` → `event_observers`:

```bash
docker compose --profile core run --rm db-migrate
```

This runs automatically as part of the `core` profile, but can also be run standalone with the `migrate` profile:

```bash
docker compose --profile migrate run --rm db-migrate
```

## Step 6: Start Services

### With local MQTT broker (single-host deployment)

```bash
# Start everything including the MQTT broker
docker compose --profile mqtt --profile core up -d

# Or include packet capture on the same host
docker compose --profile mqtt --profile core --profile receiver up -d
```

### With external MQTT broker

```bash
# Start core services only (broker runs elsewhere)
docker compose --profile core up -d
```

### Verify

```bash
# Check all containers are running
docker compose ps

# Check collector connected to MQTT
docker compose logs collector | grep -i "connected to mqtt"

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
