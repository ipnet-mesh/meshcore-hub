# MeshCore Hub

Python 3.11+ platform for managing and orchestrating MeshCore mesh networks.

## Overview

MeshCore Hub provides a complete solution for monitoring, collecting, and interacting with MeshCore mesh networks. It consists of multiple components that work together:

| Component | Description |
|-----------|-------------|
| **Interface** | Connects to MeshCore companion nodes via Serial/USB, bridges events to/from MQTT |
| **Collector** | Subscribes to MQTT events and persists them to a database |
| **API** | REST API for querying data and sending commands to the network |
| **Web Dashboard** | User-friendly web interface for visualizing network status |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    MeshCore     │     │    MeshCore     │     │    MeshCore     │
│    Device 1     │     │    Device 2     │     │    Device 3     │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │ Serial/USB            │ Serial/USB            │ Serial/USB
         │                       │                       │
┌────────▼────────┐     ┌────────▼────────┐     ┌────────▼────────┐
│   Interface     │     │   Interface     │     │   Interface     │
│   (RECEIVER)    │     │   (RECEIVER)    │     │   (SENDER)      │
└────────┬────────┘     └────────┬────────┘     └────────▲────────┘
         │                       │                       │
         │ Publish               │ Publish               │ Subscribe
         │                       │                       │
         └───────────┬───────────┴───────────────────────┘
                     │
              ┌──────▼──────┐
              │    MQTT     │
              │   Broker    │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │  Collector  │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │  Database   │
              └──────┬──────┘
                     │
         ┌───────────┴───────────┐
         │                       │
  ┌──────▼──────┐       ┌───────▼───────┐
  │     API     │◄──────│ Web Dashboard │
  └─────────────┘       └───────────────┘
```

## Features

- **Multi-node Support**: Connect multiple receiver nodes for better network coverage
- **Event Persistence**: Store messages, advertisements, telemetry, and trace data
- **REST API**: Query historical data with filtering and pagination
- **Command Dispatch**: Send messages and advertisements via the API
- **Node Tagging**: Add custom metadata to nodes for organization
- **Web Dashboard**: Visualize network status, node locations, and message history
- **Docker Ready**: Single image with all components, easy deployment

## Quick Start

### Using Docker Compose (Recommended)

Docker Compose supports **profiles** to selectively enable/disable components:

| Profile | Services |
|---------|----------|
| `mqtt` | Eclipse Mosquitto MQTT broker |
| `interface-receiver` | MeshCore device receiver (events to MQTT) |
| `interface-sender` | MeshCore device sender (MQTT to device) |
| `collector` | MQTT subscriber + database storage |
| `api` | REST API server |
| `web` | Web dashboard |
| `mock` | All services with mock device (for testing) |
| `all` | All production services |

```bash
# Clone the repository
git clone https://github.com/your-org/meshcore-hub.git
cd meshcore-hub/docker

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings (API keys, serial port, network info)

# Option 1: Start all services with mock device (for testing)
docker compose --profile mock up -d

# Option 2: Start specific services for production
docker compose --profile mqtt --profile collector --profile api --profile web up -d

# Option 3: Start all production services (requires real MeshCore device)
docker compose --profile all up -d

# View logs
docker compose logs -f

# Run database migrations
docker compose --profile migrate up

# Stop services
docker compose --profile mock down
```

#### Serial Device Access

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

### Manual Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install the package
pip install -e ".[dev]"

# Run database migrations
meshcore-hub db upgrade

# Start components (in separate terminals)
meshcore-hub interface --mode receiver --port /dev/ttyUSB0
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
| `MQTT_HOST` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_PREFIX` | `meshcore` | Topic prefix for all MQTT messages |

### Interface Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERFACE_MODE` | `RECEIVER` | Operating mode (RECEIVER or SENDER) |
| `SERIAL_PORT` | `/dev/ttyUSB0` | Serial port for MeshCore device |
| `SERIAL_BAUD` | `115200` | Serial baud rate |
| `MOCK_DEVICE` | `false` | Use mock device for testing |

### Collector Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./meshcore.db` | SQLAlchemy database URL |

#### Webhook Configuration

The collector can forward events to external HTTP endpoints:

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_ADVERTISEMENT_URL` | *(none)* | Webhook URL for advertisement events |
| `WEBHOOK_ADVERTISEMENT_SECRET` | *(none)* | Secret sent as `X-Webhook-Secret` header |
| `WEBHOOK_MESSAGE_URL` | *(none)* | Webhook URL for all message events |
| `WEBHOOK_MESSAGE_SECRET` | *(none)* | Secret for message webhook |
| `WEBHOOK_CHANNEL_MESSAGE_URL` | *(none)* | Override URL for channel messages only |
| `WEBHOOK_DIRECT_MESSAGE_URL` | *(none)* | Override URL for direct messages only |
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
| `NETWORK_NAME` | `MeshCore Network` | Display name for the network |
| `NETWORK_CITY` | *(none)* | City where network is located |
| `NETWORK_COUNTRY` | *(none)* | Country code (ISO 3166-1 alpha-2) |
| `NETWORK_LOCATION` | *(none)* | Center coordinates (lat,lon) |

## CLI Reference

```bash
# Show help
meshcore-hub --help

# Interface component
meshcore-hub interface --mode receiver --port /dev/ttyUSB0
meshcore-hub interface --mode sender --mock  # Use mock device

# Collector component
meshcore-hub collector --database-url sqlite:///./data.db

# Import node tags from JSON file
meshcore-hub collector import-tags /path/to/tags.json

# API component
meshcore-hub api --host 0.0.0.0 --port 8000

# Web dashboard
meshcore-hub web --port 8080 --network-name "My Network"

# Database management
meshcore-hub db upgrade      # Run migrations
meshcore-hub db downgrade    # Rollback one migration
meshcore-hub db current      # Show current revision
```

## Node Tags

Node tags allow you to attach custom metadata to nodes (e.g., location, role, owner). Tags are stored in the database and returned with node data via the API.

### Importing Tags from JSON

Tags can be bulk imported from a JSON file:

```bash
# Native CLI
meshcore-hub collector import-tags /path/to/tags.json

# With Docker Compose
docker compose --profile import-tags run --rm import-tags
```

### Tags JSON Format

```json
{
  "tags": [
    {
      "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "key": "location",
      "value": "San Francisco, CA",
      "value_type": "string"
    },
    {
      "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "key": "altitude",
      "value": "150",
      "value_type": "number"
    }
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `public_key` | Yes | 64-character hex public key of the node |
| `key` | Yes | Tag name (max 100 characters) |
| `value` | No | Tag value (stored as text) |
| `value_type` | No | Type hint: `string`, `number`, `boolean`, or `coordinate` (default: `string`) |

### Import Options

```bash
# Create nodes if they don't exist (default behavior)
meshcore-hub collector import-tags tags.json

# Skip tags for nodes that don't exist
meshcore-hub collector import-tags --no-create-nodes tags.json
```

### Data Directory Structure

For Docker deployments, organize your data files:

```
data/
├── collector/
│   └── tags.json      # Node tags for import
└── web/
    └── members.json   # Network members list
```

Example files are provided in `example/data/`.

### Managing Tags via API

Tags can also be managed via the REST API:

```bash
# List tags for a node
curl http://localhost:8000/api/v1/nodes/{public_key}/tags

# Create a tag (requires admin key)
curl -X POST \
  -H "Authorization: Bearer <API_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"key": "location", "value": "Building A"}' \
  http://localhost:8000/api/v1/nodes/{public_key}/tags

# Update a tag
curl -X PUT \
  -H "Authorization: Bearer <API_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"value": "Building B"}' \
  http://localhost:8000/api/v1/nodes/{public_key}/tags/location

# Delete a tag
curl -X DELETE \
  -H "Authorization: Bearer <API_ADMIN_KEY>" \
  http://localhost:8000/api/v1/nodes/{public_key}/tags/location
```

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
| GET | `/api/v1/nodes/{public_key}/tags` | Get node tags |
| POST | `/api/v1/nodes/{public_key}/tags` | Create node tag |
| GET | `/api/v1/messages` | List messages with filters |
| GET | `/api/v1/advertisements` | List advertisements |
| GET | `/api/v1/telemetry` | List telemetry data |
| GET | `/api/v1/trace-paths` | List trace paths |
| POST | `/api/v1/commands/send-message` | Send direct message |
| POST | `/api/v1/commands/send-channel-message` | Send channel message |
| GET | `/api/v1/stats` | Get network statistics |

## Development

### Setup

```bash
# Clone and setup
git clone https://github.com/your-org/meshcore-hub.git
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
# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/
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
├── tests/                  # Test suite
├── alembic/                # Database migrations
├── etc/                    # Configuration files (mosquitto.conf)
├── example/                # Example files for testing
│   └── data/               # Example data files (members.json)
├── data/                   # Runtime data (gitignored)
├── Dockerfile              # Docker build configuration
├── docker-compose.yml      # Docker Compose services (gitignored)
├── docker-compose.yml.example  # Docker Compose template
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
4. Run tests and linting (`pytest && black . && flake8`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

See [LICENSE](LICENSE) for details.

## Acknowledgments

- [MeshCore](https://meshcore.dev/) - The mesh networking protocol
- [meshcore](https://github.com/fdlamotte/meshcore) - Python library for MeshCore devices
