# MeshCore Hub

[![CI](https://github.com/ipnet-mesh/meshcore-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/ipnet-mesh/meshcore-hub/actions/workflows/ci.yml)
[![Docker](https://github.com/ipnet-mesh/meshcore-hub/actions/workflows/docker.yml/badge.svg)](https://github.com/ipnet-mesh/meshcore-hub/actions/workflows/docker.yml)
[![BuyMeACoffee](https://raw.githubusercontent.com/pachadotdev/buymeacoffee-badges/main/bmc-donate-yellow.svg)](https://www.buymeacoffee.com/jinglemansweep)

Python 3.14+ platform for managing and orchestrating MeshCore mesh networks.

![MeshCore Hub Web Dashboard](docs/images/web.png)

> [!IMPORTANT]
> **Help Translate MeshCore Hub** 🌍
>
> We need volunteers to translate the web dashboard! Currently only English is available. Check out the [Translation Guide](src/meshcore_hub/web/static/locales/languages.md) to contribute a language pack. Partial translations welcome!

## Overview

MeshCore Hub provides a complete solution for monitoring, collecting, and interacting with MeshCore mesh networks. It consists of multiple components that work together:

| Component | Description |
|-----------|-------------|
| **Interface** | Connects to MeshCore companion nodes via Serial/USB, bridges events to/from MQTT |
| **Collector** | Subscribes to MQTT events and persists them to a database |
| **API** | REST API for querying data and sending commands to the network |
| **Web Dashboard** | Single Page Application (SPA) for visualizing network status |

## Architecture

```mermaid
flowchart LR
    subgraph Devices["MeshCore Devices"]
        D1["Device 1"]
        D2["Device 2"]
        D3["Device 3"]
    end

    subgraph Interfaces["Interface Layer"]
        I1["RECEIVER"]
        I2["RECEIVER"]
        I3["SENDER"]
    end

    D1 -->|Serial| I1
    D2 -->|Serial| I2
    D3 -->|Serial| I3

    I1 -->|Publish| MQTT
    I2 -->|Publish| MQTT
    MQTT -->|Subscribe| I3

    MQTT["MQTT Broker"]

    subgraph Backend["Backend Services"]
        Collector --> Database --> API
    end

    MQTT --> Collector
    API --> Web["Web Dashboard"]

    style Devices fill:none,stroke:#0288d1,stroke-width:2px
    style Interfaces fill:none,stroke:#f57c00,stroke-width:2px
    style Backend fill:none,stroke:#388e3c,stroke-width:2px
    style MQTT fill:none,stroke:#7b1fa2,stroke-width:3px
    style Collector fill:none,stroke:#388e3c,stroke-width:2px
    style Database fill:none,stroke:#c2185b,stroke-width:2px
    style API fill:none,stroke:#1976d2,stroke-width:2px
    style Web fill:none,stroke:#ffa000,stroke-width:2px
```

## Features

- **Multi-node Support**: Connect multiple receiver nodes for better network coverage
- **Event Persistence**: Store messages, advertisements, telemetry, and trace data
- **REST API**: Query historical data with filtering and pagination
- **Command Dispatch**: Send messages and advertisements via the API
- **Node Tagging**: Add custom metadata to nodes for organization
- **Web Dashboard**: Visualize network status, node locations, and message history
- **Internationalization**: Full i18n support with composable translation patterns
- **Docker Ready**: Single image with all components, easy deployment

## Getting Started

### Simple Self-Hosted Setup

The quickest way to get started is running the entire stack on a single machine with a connected MeshCore device.

**Prerequisites:**
1. Flash the [USB Companion firmware](https://meshcore.dev/) onto a compatible device (e.g., Heltec V3, T-Beam)
2. Connect the device via USB to a machine that supports Docker or Python

**Steps:**
```bash
# Create a directory, download the Docker Compose file and
# example environment configuration file

mkdir meshcore-hub
cd meshcore-hub
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/refs/heads/main/docker-compose.yml
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/refs/heads/main/.env.example

# Copy and configure environment
cp .env.example .env
# Edit .env: set SERIAL_PORT to your device (e.g., /dev/ttyUSB0 or /dev/ttyACM0)

# Start the entire stack with local MQTT broker
docker compose --profile mqtt --profile core --profile receiver up -d

# View the web dashboard
open http://localhost:8080
```

This starts all services: MQTT broker, collector, API, web dashboard, and the interface receiver that bridges your MeshCore device to the system.

### Distributed Community Setup

For larger deployments, you can separate receiver nodes from the central infrastructure. This allows multiple community members to contribute receiver coverage while hosting the backend centrally.

```mermaid
flowchart TB
    subgraph Community["Community Members"]
        R1["Raspberry Pi + MeshCore"]
        R2["Raspberry Pi + MeshCore"]
        R3["Any Linux + MeshCore"]
    end

    subgraph Server["Community VPS / Server"]
        MQTT["MQTT Broker"]
        Collector
        API
        Web["Web Dashboard (public)"]

        MQTT --> Collector --> API
        API <--- Web
    end

    R1 -->|MQTT port 1883| MQTT
    R2 -->|MQTT port 1883| MQTT
    R3 -->|MQTT port 1883| MQTT

    style Community fill:none,stroke:#0288d1,stroke-width:2px
    style Server fill:none,stroke:#388e3c,stroke-width:2px
    style MQTT fill:none,stroke:#7b1fa2,stroke-width:3px
    style Collector fill:none,stroke:#388e3c,stroke-width:2px
    style API fill:none,stroke:#1976d2,stroke-width:2px
    style Web fill:none,stroke:#ffa000,stroke-width:2px
```

**On each receiver node (Raspberry Pi, etc.):**
```bash
# Only run the receiver component
# Configure .env with MQTT_HOST pointing to your central server
MQTT_HOST=your-community-server.com
SERIAL_PORT=/dev/ttyUSB0

docker compose --profile receiver up -d
```

**On the central server (VPS/cloud):**
```bash
# Run the core infrastructure with local MQTT broker
docker compose --profile mqtt --profile core up -d

# Or connect to an existing MQTT broker (set MQTT_HOST in .env)
docker compose --profile core up -d
```

This architecture allows:
- Multiple receivers for better RF coverage across a geographic area
- Centralized data storage and web interface
- Community members to contribute coverage with minimal setup
- The central server to be hosted anywhere with internet access

## Deployment

### Docker Compose Profiles

Docker Compose uses **profiles** to select which services to run:

| Profile | Services | Use Case |
|---------|----------|----------|
| `core` | db-migrate, collector, api, web | Central server infrastructure |
| `receiver` | interface-receiver | Receiver node (events to MQTT) |
| `sender` | interface-sender | Sender node (MQTT to device) |
| `mqtt` | mosquitto broker | Local MQTT broker (optional) |
| `mock` | interface-mock-receiver | Testing without hardware |
| `migrate` | db-migrate | One-time database migration |
| `seed` | seed | One-time seed data import |

**Note:** Most deployments connect to an external MQTT broker. Add `--profile mqtt` only if you need a local broker.

```bash
# Create database schema
docker compose --profile migrate run --rm db-migrate

# Seed the database
docker compose --profile seed run --rm seed

# Start core services with local MQTT broker
docker compose --profile mqtt --profile core up -d

# Or connect to external MQTT (configure MQTT_HOST in .env)
docker compose --profile core up -d

# Start just the receiver (connects to MQTT_HOST from .env)
docker compose --profile receiver up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Serial Device Access

For production with real MeshCore devices, ensure the serial port is accessible:

```bash
# Check device path
ls -la /dev/ttyUSB*

# Add user to dialout group (Linux)
sudo usermod -aG dialout $USER

# Configure in .env
SERIAL_PORT=/dev/ttyUSB0
SERIAL_PORT_SENDER=/dev/ttyUSB1  # If using separate sender device
```

**Tip:** If USB devices reconnect as different numeric IDs (e.g., `/dev/ttyUSB0` becomes `/dev/ttyUSB1`), use the stable `/dev/serial/by-id/` path instead:

```bash
# List available devices by ID
ls -la /dev/serial/by-id/

# Example output:
# usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_abc123-if00-port0 -> ../../ttyUSB0

# Configure using the stable ID
SERIAL_PORT=/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_abc123-if00-port0
```

### Manual Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e ".[dev]"

# Run database migrations
meshcore-hub db upgrade

# Start components (in separate terminals)
meshcore-hub interface receiver --port /dev/ttyUSB0
meshcore-hub collector
meshcore-hub api
meshcore-hub web
```

## Configuration

All components are configured via environment variables. Create a `.env` file or export variables:

### Common Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DATA_HOME` | `./data` | Base directory for runtime data |
| `SEED_HOME` | `./seed` | Directory containing seed data files |
| `MQTT_HOST` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | *(none)* | MQTT username (optional) |
| `MQTT_PASSWORD` | *(none)* | MQTT password (optional) |
| `MQTT_PREFIX` | `meshcore` | Topic prefix for all MQTT messages |
| `MQTT_TLS` | `false` | Enable TLS/SSL for MQTT connection |

### Interface Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SERIAL_PORT` | `/dev/ttyUSB0` | Serial port for MeshCore device |
| `SERIAL_BAUD` | `115200` | Serial baud rate |
| `MESHCORE_DEVICE_NAME` | *(none)* | Device/node name set on startup (broadcast in advertisements) |
| `NODE_ADDRESS` | *(none)* | Override for device public key (64-char hex string) |
| `NODE_ADDRESS_SENDER` | *(none)* | Override for sender device public key |
| `CONTACT_CLEANUP_ENABLED` | `true` | Enable automatic removal of stale contacts from companion node |
| `CONTACT_CLEANUP_DAYS` | `7` | Remove contacts not advertised for this many days |

### Webhooks

The collector can forward certain events to external HTTP endpoints:

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_ADVERTISEMENT_URL` | *(none)* | Webhook URL for advertisement events |
| `WEBHOOK_ADVERTISEMENT_SECRET` | *(none)* | Secret sent as `X-Webhook-Secret` header |
| `WEBHOOK_MESSAGE_URL` | *(none)* | Webhook URL for all message events |
| `WEBHOOK_MESSAGE_SECRET` | *(none)* | Secret for message webhook |
| `WEBHOOK_CHANNEL_MESSAGE_URL` | *(none)* | Override URL for channel messages only |
| `WEBHOOK_CHANNEL_MESSAGE_SECRET` | *(none)* | Secret for channel message webhook |
| `WEBHOOK_DIRECT_MESSAGE_URL` | *(none)* | Override URL for direct messages only |
| `WEBHOOK_DIRECT_MESSAGE_SECRET` | *(none)* | Secret for direct message webhook |
| `WEBHOOK_TIMEOUT` | `10.0` | Request timeout in seconds |
| `WEBHOOK_MAX_RETRIES` | `3` | Max retry attempts on failure |
| `WEBHOOK_RETRY_BACKOFF` | `2.0` | Exponential backoff multiplier |

Webhook payload format:
```json
{
  "event_type": "advertisement",
  "public_key": "abc123...",
  "payload": { ... event data ... }
}
```

### Data Retention

The collector automatically cleans up old event data and inactive nodes:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_RETENTION_ENABLED` | `true` | Enable automatic cleanup of old events |
| `DATA_RETENTION_DAYS` | `30` | Days to retain event data |
| `DATA_RETENTION_INTERVAL_HOURS` | `24` | Hours between cleanup runs |
| `NODE_CLEANUP_ENABLED` | `true` | Enable removal of inactive nodes |
| `NODE_CLEANUP_DAYS` | `7` | Remove nodes not seen for this many days |

### API Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |
| `API_READ_KEY` | *(none)* | Read-only API key |
| `API_ADMIN_KEY` | *(none)* | Admin API key (required for commands) |

### Web Dashboard Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_HOST` | `0.0.0.0` | Web server bind address |
| `WEB_PORT` | `8080` | Web server port |
| `API_BASE_URL` | `http://localhost:8000` | API endpoint URL |
| `API_KEY` | *(none)* | API key for web dashboard queries (optional) |
| `WEB_THEME` | `dark` | Default theme (`dark` or `light`). Users can override via theme toggle in navbar. |
| `WEB_LOCALE` | `en` | Locale/language for the web dashboard (e.g., `en`, `es`, `fr`) |
| `WEB_ADMIN_ENABLED` | `false` | Enable admin interface at /a/ (requires auth proxy) |
| `TZ` | `UTC` | Timezone for displaying dates/times (e.g., `America/New_York`, `Europe/London`) |
| `NETWORK_DOMAIN` | *(none)* | Network domain name (optional) |
| `NETWORK_NAME` | `MeshCore Network` | Display name for the network |
| `NETWORK_CITY` | *(none)* | City where network is located |
| `NETWORK_COUNTRY` | *(none)* | Country code (ISO 3166-1 alpha-2) |
| `NETWORK_RADIO_CONFIG` | *(none)* | Radio config (comma-delimited: profile,freq,bw,sf,cr,power) |
| `NETWORK_WELCOME_TEXT` | *(none)* | Custom welcome text for homepage |
| `NETWORK_CONTACT_EMAIL` | *(none)* | Contact email address |
| `NETWORK_CONTACT_DISCORD` | *(none)* | Discord server link |
| `NETWORK_CONTACT_GITHUB` | *(none)* | GitHub repository URL |
| `NETWORK_CONTACT_YOUTUBE` | *(none)* | YouTube channel URL |
| `CONTENT_HOME` | `./content` | Directory containing custom content (pages/, media/) |

#### Feature Flags

Control which pages are visible in the web dashboard. Disabled features are fully hidden: removed from navigation, return 404 on their routes, and excluded from sitemap/robots.txt.

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_DASHBOARD` | `true` | Enable the `/dashboard` page |
| `FEATURE_NODES` | `true` | Enable the `/nodes` pages (list, detail, short links) |
| `FEATURE_ADVERTISEMENTS` | `true` | Enable the `/advertisements` page |
| `FEATURE_MESSAGES` | `true` | Enable the `/messages` page |
| `FEATURE_MAP` | `true` | Enable the `/map` page and `/map/data` endpoint |
| `FEATURE_MEMBERS` | `true` | Enable the `/members` page |
| `FEATURE_PAGES` | `true` | Enable custom markdown pages |

**Dependencies:** Dashboard auto-disables when all of Nodes/Advertisements/Messages are disabled. Map auto-disables when Nodes is disabled.

### Custom Content

The web dashboard supports custom content including markdown pages and media files. Content is organized in subdirectories:

```
content/
├── pages/     # Custom markdown pages
│   └── about.md
└── media/     # Custom media files
    └── images/
        └── logo.svg   # Custom logo (replaces favicon and navbar/home logo)
```

**Setup:**
```bash
# Create content directory structure
mkdir -p content/pages content/media

# Create a custom page
cat > content/pages/about.md << 'EOF'
---
title: About Us
slug: about
menu_order: 10
---

# About Our Network

Welcome to our MeshCore mesh network!

## Getting Started

1. Get a compatible LoRa device
2. Flash MeshCore firmware
3. Configure your radio settings
EOF
```

**Frontmatter fields:**
| Field | Default | Description |
|-------|---------|-------------|
| `title` | Filename titlecased | Browser tab title and navigation link text (not rendered on page) |
| `slug` | Filename without `.md` | URL path (e.g., `about` → `/pages/about`) |
| `menu_order` | `100` | Sort order in navigation (lower = earlier) |

The markdown content is rendered as-is, so include your own `# Heading` if desired.

Pages automatically appear in the navigation menu and sitemap. With Docker, mount the content directory:

```yaml
# docker-compose.yml (already configured)
volumes:
  - ${CONTENT_HOME:-./content}:/content:ro
environment:
  - CONTENT_HOME=/content
```

## Seed Data

The database can be seeded with node tags and network members from YAML files in the `SEED_HOME` directory (default: `./seed`).

#### Running the Seed Process

Seeding is a separate process and must be run explicitly:

```bash
docker compose --profile seed up
```

This imports data from the following files (if they exist):
- `{SEED_HOME}/node_tags.yaml` - Node tag definitions
- `{SEED_HOME}/members.yaml` - Network member definitions

#### Directory Structure

```
seed/                          # SEED_HOME (seed data files)
├── node_tags.yaml            # Node tags for import
└── members.yaml              # Network members for import

data/                          # DATA_HOME (runtime data)
└── collector/
    └── meshcore.db           # SQLite database
```

Example seed files are provided in `example/seed/`.

### Node Tags

Node tags allow you to attach custom metadata to nodes (e.g., location, role, owner). Tags are stored in the database and returned with node data via the API.

#### Node Tags YAML Format

Tags are keyed by public key in YAML format:

```yaml
# Each key is a 64-character hex public key
0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:
  friendly_name: Gateway Node
  role: gateway
  lat: 37.7749
  lon: -122.4194
  is_online: true

fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210:
  friendly_name: Oakland Repeater
  altitude: 150
```

Tag values can be:
- **YAML primitives** (auto-detected type): strings, numbers, booleans
- **Explicit type** (when you need to force a specific type):
  ```yaml
  altitude:
    value: "150"
    type: number
  ```

Supported types: `string`, `number`, `boolean`

### Network Members

Network members represent the people operating nodes in your network. Members can optionally be linked to nodes via their public key.

#### Members YAML Format

```yaml
- member_id: walshie86
  name: Walshie
  callsign: Walshie86
  role: member
  description: IPNet Member
- member_id: craig
  name: Craig
  callsign: M7XCN
  role: member
  description: IPNet Member
```

| Field | Required | Description |
|-------|----------|-------------|
| `member_id` | Yes | Unique identifier for the member |
| `name` | Yes | Member's display name |
| `callsign` | No | Amateur radio callsign |
| `role` | No | Member's role in the network |
| `description` | No | Additional description |
| `contact` | No | Contact information |
| `public_key` | No | Associated node public key (64-char hex) |

## API Documentation

When running, the API provides interactive documentation at:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

Health check endpoints are also available:

- **Health**: http://localhost:8000/health
- **Ready**: http://localhost:8000/health/ready (includes database check)

### Authentication

The API supports optional bearer token authentication:

```bash
# Read-only access
curl -H "Authorization: Bearer <API_READ_KEY>" http://localhost:8000/api/v1/nodes

# Admin access (required for commands)
curl -X POST \
  -H "Authorization: Bearer <API_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"destination": "abc123...", "text": "Hello!"}' \
  http://localhost:8000/api/v1/commands/send-message
```

### Example Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/nodes` | List all known nodes |
| GET | `/api/v1/nodes/{public_key}` | Get node details |
| GET | `/api/v1/nodes/prefix/{prefix}` | Get node by public key prefix |
| GET | `/api/v1/nodes/{public_key}/tags` | Get node tags |
| POST | `/api/v1/nodes/{public_key}/tags` | Create node tag |
| GET | `/api/v1/messages` | List messages with filters |
| GET | `/api/v1/advertisements` | List advertisements |
| GET | `/api/v1/telemetry` | List telemetry data |
| GET | `/api/v1/trace-paths` | List trace paths |
| GET | `/api/v1/members` | List network members |
| POST | `/api/v1/commands/send-message` | Send direct message |
| POST | `/api/v1/commands/send-channel-message` | Send channel message |
| POST | `/api/v1/commands/send-advertisement` | Send advertisement |
| GET | `/api/v1/dashboard/stats` | Get network statistics |
| GET | `/api/v1/dashboard/activity` | Get daily advertisement activity |
| GET | `/api/v1/dashboard/message-activity` | Get daily message activity |
| GET | `/api/v1/dashboard/node-count` | Get cumulative node count history |

## Development

### Setup

```bash
# Clone and setup
git clone https://github.com/ipnet-mesh/meshcore-hub.git
cd meshcore-hub
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=meshcore_hub --cov-report=html

# Run specific test file
pytest tests/test_api/test_nodes.py

# Run tests matching pattern
pytest -k "test_list"
```

### Code Quality

```bash
# Run all code quality checks (formatting, linting, type checking)
pre-commit run --all-files
```

### Creating Database Migrations

```bash
# Auto-generate migration from model changes
meshcore-hub db revision --autogenerate -m "Add new field to nodes"

# Create empty migration
meshcore-hub db revision -m "Custom migration"

# Apply migrations
meshcore-hub db upgrade
```

## Project Structure

```
meshcore-hub/
├── src/meshcore_hub/       # Main package
│   ├── common/             # Shared code (models, schemas, config)
│   ├── interface/          # MeshCore device interface
│   ├── collector/          # MQTT event collector
│   ├── api/                # REST API
│   └── web/                # Web dashboard
│       ├── templates/      # Jinja2 templates (SPA shell)
│       └── static/
│           ├── js/spa/     # SPA frontend (ES modules, lit-html)
│           └── locales/    # Translation files (en.json, languages.md)
├── tests/                  # Test suite
├── alembic/                # Database migrations
├── etc/                    # Configuration files (mosquitto.conf)
├── example/                # Example files for reference
│   ├── seed/               # Example seed data files
│   │   ├── node_tags.yaml  # Example node tags
│   │   └── members.yaml    # Example network members
│   └── content/            # Example custom content
│       ├── pages/          # Example custom pages
│       │   └── join.md     # Example join page
│       └── media/          # Example media files
│           └── images/     # Custom images
├── seed/                   # Seed data directory (SEED_HOME, copy from example/seed/)
├── content/                # Custom content directory (CONTENT_HOME, optional)
│   ├── pages/              # Custom markdown pages
│   └── media/              # Custom media files
│       └── images/         # Custom images (logo.svg replaces default logo)
├── data/                   # Runtime data directory (DATA_HOME, created at runtime)
├── Dockerfile              # Docker build configuration
├── docker-compose.yml      # Docker Compose services
├── PROMPT.md               # Project specification
├── SCHEMAS.md              # Event schema documentation
├── PLAN.md                 # Implementation plan
├── TASKS.md                # Task tracker
└── AGENTS.md               # AI assistant guidelines
```

## Documentation

- [PROMPT.md](PROMPT.md) - Original project specification
- [SCHEMAS.md](SCHEMAS.md) - MeshCore event schemas
- [PLAN.md](PLAN.md) - Architecture and implementation plan
- [TASKS.md](TASKS.md) - Development task tracker
- [AGENTS.md](AGENTS.md) - Guidelines for AI coding assistants

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and quality checks (`pytest && pre-commit run --all-files`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later). See [LICENSE](LICENSE) for details.

## Acknowledgments

- [MeshCore](https://meshcore.dev/) - The mesh networking protocol
- [meshcore](https://github.com/fdlamotte/meshcore) - Python library for MeshCore devices
