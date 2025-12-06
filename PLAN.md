# MeshCore Hub - Implementation Plan

## Project Overview

MeshCore Hub is a Python 3.11+ monorepo for managing and orchestrating MeshCore mesh networks. It consists of five main components that work together to receive, store, query, and visualize mesh network data.

---

## Questions Requiring Clarification

Before implementation, the following questions need answers:

### Architecture & Design

1. **MQTT Broker Selection**: Should we include an embedded MQTT broker (like `hbmqtt`) or assume an external broker (Mosquitto) is always used? The spec mentions Docker but doesn't specify broker deployment.

2. **Database Deployment**: For production, should we support PostgreSQL/MySQL from the start, or focus on SQLite initially and add other backends later? This affects connection pooling and async driver choices.

3. **Web Dashboard Separation**: Should `meshcore_web` be a separate FastAPI app or integrated into `meshcore_api`? Running two FastAPI apps adds deployment complexity.

4. **Member Profiles JSON Location**: Where should the static JSON file for member profiles be stored? In the config directory, as a mounted volume, or embedded in the package?

### Interface Component

5. **Multiple Serial Devices**: Should a single Interface instance support multiple serial devices simultaneously, or should users run multiple instances (one per device)?

6. **Reconnection Strategy**: What should happen when the serial connection is lost? Automatic reconnect with backoff, or exit and let the container orchestrator restart?

7. **Mock Device Scope**: How comprehensive should the mock MeshCore device be? Should it simulate realistic timing, packet loss, and network topology?

### Collector Component

8. **Event Deduplication**: How should we handle duplicate events from multiple receiver nodes? By message signature/hash, or accept all duplicates?

9. **Data Retention Policy**: Should we implement automatic data pruning (e.g., delete messages older than X days)? This affects long-running deployments.

10. **Webhook Configuration**: The SCHEMAS.md mentions webhooks but PROMPT.md doesn't detail webhook management. Should webhooks be configured via API, config file, or environment variables?

### API Component

11. **API Key Management**: How should API keys be generated and managed? Static config, database-stored, or runtime generation? What about key rotation?

12. **Rate Limiting**: Should the API implement rate limiting? If so, what defaults?

13. **CORS Configuration**: Should CORS be configurable for web dashboard access from different domains?

### Web Dashboard

14. **Authentication**: Should the web dashboard have its own authentication, or rely on API bearer tokens? What about session management?

15. **Real-time Updates**: Should the dashboard support real-time updates (WebSocket/SSE), or polling-based refresh?

16. **Map Provider**: Which map provider for the Node Map view? OpenStreetMap/Leaflet (free) or allow configuration for commercial providers?

### Node Tags System

17. **Tag Value Types**: Should node tags support typed values (string, number, boolean, coordinates) or just strings? The spec mentions lat/lon for the map feature.

18. **Reserved Tag Names**: Should certain tag names be reserved for system use (e.g., `location`, `description`)?

### DevOps & Operations

19. **Health Checks**: What health check endpoints should each component expose for Docker/Kubernetes?

20. **Metrics/Observability**: Should we include Prometheus metrics endpoints or structured logging for observability?

21. **Log Level Configuration**: Per-component or global log level configuration?

---

## Proposed Architecture

```
                                    +------------------+
                                    |   MQTT Broker    |
                                    |   (Mosquitto)    |
                                    +--------+---------+
                                             |
              +------------------------------+------------------------------+
              |                              |                              |
              v                              v                              v
    +---------+---------+          +---------+---------+          +---------+---------+
    | meshcore_interface|          | meshcore_interface|          | meshcore_interface|
    |    (RECEIVER)     |          |    (RECEIVER)     |          |    (SENDER)       |
    +-------------------+          +-------------------+          +-------------------+
              |                              |                              ^
              |  Publishes events            |                              |
              v                              v                              |
    +----------------------------------------------------------+           |
    |                      MQTT Topics                          |           |
    |  <prefix>/<pubkey>/event/<event_name>                    |           |
    |  <prefix>/+/command/<command_name>  <--------------------+-----------+
    +----------------------------------------------------------+
                              |
                              v
                    +---------+---------+
                    | meshcore_collector|
                    |   (Subscriber)    |
                    +---------+---------+
                              |
                              v
                    +---------+---------+
                    |     Database      |
                    |  (SQLite/Postgres)|
                    +---------+---------+
                              ^
                              |
              +---------------+---------------+
              |                               |
    +---------+---------+           +---------+---------+
    |   meshcore_api    |           |   meshcore_web    |
    |    (REST API)     |           |   (Dashboard)     |
    +-------------------+           +-------------------+
```

---

## Package Structure

```
meshcore-hub/
├── pyproject.toml                 # Root project configuration
├── README.md
├── PROMPT.md
├── SCHEMAS.md
├── PLAN.md
├── .env.example                   # Example environment variables
├── .pre-commit-config.yaml        # Pre-commit hooks
├── alembic.ini                    # Alembic configuration
├── alembic/                       # Database migrations
│   ├── env.py
│   ├── versions/
│   └── script.py.mako
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── tests/
│   ├── conftest.py
│   ├── test_interface/
│   ├── test_collector/
│   ├── test_api/
│   ├── test_web/
│   └── test_common/
└── src/
    └── meshcore_hub/
        ├── __init__.py
        ├── __main__.py            # CLI entrypoint
        ├── common/
        │   ├── __init__.py
        │   ├── config.py          # Pydantic settings
        │   ├── models/            # SQLAlchemy models
        │   │   ├── __init__.py
        │   │   ├── base.py
        │   │   ├── node.py
        │   │   ├── message.py
        │   │   ├── advertisement.py
        │   │   ├── trace_path.py
        │   │   ├── telemetry.py
        │   │   ├── node_tag.py
        │   │   └── event_log.py
        │   ├── schemas/           # Pydantic schemas (API request/response)
        │   │   ├── __init__.py
        │   │   ├── events.py
        │   │   ├── nodes.py
        │   │   ├── messages.py
        │   │   └── commands.py
        │   ├── mqtt.py            # MQTT client utilities
        │   ├── database.py        # Database session management
        │   └── logging.py         # Logging configuration
        ├── interface/
        │   ├── __init__.py
        │   ├── cli.py             # Click CLI for interface
        │   ├── receiver.py        # RECEIVER mode implementation
        │   ├── sender.py          # SENDER mode implementation
        │   ├── device.py          # MeshCore device wrapper
        │   └── mock_device.py     # Mock device for testing
        ├── collector/
        │   ├── __init__.py
        │   ├── cli.py             # Click CLI for collector
        │   ├── subscriber.py      # MQTT subscriber
        │   ├── handlers/          # Event handlers
        │   │   ├── __init__.py
        │   │   ├── message.py
        │   │   ├── advertisement.py
        │   │   ├── trace.py
        │   │   ├── telemetry.py
        │   │   └── contacts.py
        │   └── webhook.py         # Webhook dispatcher
        ├── api/
        │   ├── __init__.py
        │   ├── cli.py             # Click CLI for API
        │   ├── app.py             # FastAPI application
        │   ├── dependencies.py    # FastAPI dependencies
        │   ├── auth.py            # Bearer token authentication
        │   ├── routes/
        │   │   ├── __init__.py
        │   │   ├── messages.py
        │   │   ├── nodes.py
        │   │   ├── advertisements.py
        │   │   ├── trace_paths.py
        │   │   ├── telemetry.py
        │   │   ├── node_tags.py
        │   │   ├── commands.py
        │   │   └── dashboard.py   # Simple HTML dashboard
        │   └── templates/
        │       └── dashboard.html
        └── web/
            ├── __init__.py
            ├── cli.py             # Click CLI for web dashboard
            ├── app.py             # FastAPI application
            ├── routes/
            │   ├── __init__.py
            │   ├── home.py
            │   ├── members.py
            │   ├── network.py
            │   ├── nodes.py
            │   ├── map.py
            │   └── messages.py
            ├── templates/
            │   ├── base.html
            │   ├── home.html
            │   ├── members.html
            │   ├── network.html
            │   ├── nodes.html
            │   ├── map.html
            │   └── messages.html
            └── static/
                ├── css/
                └── js/
```

---

## Database Schema

### Core Tables

#### `nodes`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| public_key | VARCHAR(64) | Unique, indexed |
| name | VARCHAR(255) | Node display name |
| adv_type | VARCHAR(20) | chat, repeater, room, none |
| flags | INTEGER | Capability flags |
| first_seen | TIMESTAMP | First advertisement |
| last_seen | TIMESTAMP | Most recent activity |
| created_at | TIMESTAMP | Record creation |
| updated_at | TIMESTAMP | Record update |

#### `node_tags`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| node_id | UUID | FK to nodes |
| key | VARCHAR(100) | Tag name |
| value | TEXT | Tag value (JSON for typed values) |
| value_type | VARCHAR(20) | string, number, boolean, coordinate |
| created_at | TIMESTAMP | Record creation |
| updated_at | TIMESTAMP | Record update |

*Unique constraint on (node_id, key)*

#### `messages`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| receiver_node_id | UUID | FK to nodes (receiving interface) |
| message_type | VARCHAR(20) | contact, channel |
| pubkey_prefix | VARCHAR(12) | Sender prefix (contact msgs) |
| channel_idx | INTEGER | Channel index (channel msgs) |
| text | TEXT | Message content |
| path_len | INTEGER | Hop count |
| txt_type | INTEGER | Message type indicator |
| signature | VARCHAR(8) | Message signature |
| snr | FLOAT | Signal-to-noise ratio |
| sender_timestamp | TIMESTAMP | Sender's timestamp |
| received_at | TIMESTAMP | When received by interface |
| created_at | TIMESTAMP | Record creation |

#### `advertisements`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| receiver_node_id | UUID | FK to nodes (receiving interface) |
| node_id | UUID | FK to nodes (advertised node) |
| public_key | VARCHAR(64) | Advertised public key |
| name | VARCHAR(255) | Advertised name |
| adv_type | VARCHAR(20) | Node type |
| flags | INTEGER | Capability flags |
| received_at | TIMESTAMP | When received |
| created_at | TIMESTAMP | Record creation |

#### `trace_paths`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| receiver_node_id | UUID | FK to nodes |
| initiator_tag | BIGINT | Trace identifier |
| path_len | INTEGER | Path length |
| flags | INTEGER | Trace flags |
| auth | INTEGER | Auth data |
| path_hashes | JSON | Array of node hashes |
| snr_values | JSON | Array of SNR values |
| hop_count | INTEGER | Total hops |
| received_at | TIMESTAMP | When received |
| created_at | TIMESTAMP | Record creation |

#### `telemetry`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| receiver_node_id | UUID | FK to nodes |
| node_id | UUID | FK to nodes (reporting node) |
| node_public_key | VARCHAR(64) | Reporting node key |
| lpp_data | BYTEA | Raw LPP data |
| parsed_data | JSON | Decoded sensor readings |
| received_at | TIMESTAMP | When received |
| created_at | TIMESTAMP | Record creation |

#### `events_log`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| receiver_node_id | UUID | FK to nodes |
| event_type | VARCHAR(50) | Event type name |
| payload | JSON | Full event payload |
| received_at | TIMESTAMP | When received |
| created_at | TIMESTAMP | Record creation |

---

## MQTT Topic Structure

### Event Topics (Published by RECEIVER)
```
meshcore/<public_key>/event/advertisement
meshcore/<public_key>/event/contact_msg_recv
meshcore/<public_key>/event/channel_msg_recv
meshcore/<public_key>/event/trace_data
meshcore/<public_key>/event/telemetry_response
meshcore/<public_key>/event/contacts
meshcore/<public_key>/event/send_confirmed
meshcore/<public_key>/event/status_response
meshcore/<public_key>/event/battery
meshcore/<public_key>/event/path_updated
```

### Command Topics (Subscribed by SENDER)
```
meshcore/+/command/send_msg
meshcore/+/command/send_channel_msg
meshcore/+/command/send_advert
meshcore/+/command/request_status
meshcore/+/command/request_telemetry
```

### Command Payloads

#### send_msg
```json
{
  "destination": "public_key or pubkey_prefix",
  "text": "message content",
  "timestamp": 1732820498
}
```

#### send_channel_msg
```json
{
  "channel_idx": 4,
  "text": "message content",
  "timestamp": 1732820498
}
```

#### send_advert
```json
{
  "flood": true
}
```

---

## API Endpoints

### Authentication
- Bearer token in `Authorization` header
- Two token levels: `read` (query only) and `admin` (query + commands)

### Nodes
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/nodes | read | List all nodes with pagination/filtering |
| GET | /api/v1/nodes/{public_key} | read | Get single node details |

### Node Tags
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/nodes/{public_key}/tags | read | List node's tags |
| POST | /api/v1/nodes/{public_key}/tags | admin | Create tag |
| PUT | /api/v1/nodes/{public_key}/tags/{key} | admin | Update tag |
| DELETE | /api/v1/nodes/{public_key}/tags/{key} | admin | Delete tag |

### Messages
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/messages | read | List messages with filters |
| GET | /api/v1/messages/{id} | read | Get single message |

**Query Parameters:**
- `type`: contact, channel
- `pubkey_prefix`: Filter by sender
- `channel_idx`: Filter by channel
- `since`: Start timestamp
- `until`: End timestamp
- `limit`, `offset`: Pagination

### Advertisements
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/advertisements | read | List advertisements |
| GET | /api/v1/advertisements/{id} | read | Get single advertisement |

### Trace Paths
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/trace-paths | read | List trace paths |
| GET | /api/v1/trace-paths/{id} | read | Get single trace path |

### Telemetry
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/telemetry | read | List telemetry data |
| GET | /api/v1/telemetry/{id} | read | Get single telemetry record |

### Commands
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /api/v1/commands/send-message | admin | Send direct message |
| POST | /api/v1/commands/send-channel-message | admin | Send channel message |
| POST | /api/v1/commands/send-advertisement | admin | Send advertisement |

### Dashboard
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/v1/dashboard | read | HTML dashboard page |
| GET | /api/v1/stats | read | JSON statistics |

---

## Configuration (Environment Variables)

### Common
| Variable | Default | Description |
|----------|---------|-------------|
| DATA_HOME | ./data | Base directory for service data |
| LOG_LEVEL | INFO | Logging level |
| MQTT_HOST | localhost | MQTT broker host |
| MQTT_PORT | 1883 | MQTT broker port |
| MQTT_USERNAME | | MQTT username (optional) |
| MQTT_PASSWORD | | MQTT password (optional) |
| MQTT_PREFIX | meshcore | Topic prefix |

### Data Directory Structure
The `DATA_HOME` environment variable controls where all service data is stored:
```
${DATA_HOME}/
├── collector/
│   ├── meshcore.db    # SQLite database
│   └── tags.json      # Node tags for import
└── web/
    └── members.json   # Network members list
```

### Interface
| Variable | Default | Description |
|----------|---------|-------------|
| INTERFACE_MODE | RECEIVER | RECEIVER or SENDER |
| SERIAL_PORT | /dev/ttyUSB0 | Serial port path |
| SERIAL_BAUD | 115200 | Baud rate |
| MESHCORE_DEVICE_NAME | *(none)* | Device/node name set on startup |
| MOCK_DEVICE | false | Use mock device |

### Collector
| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | sqlite:///{DATA_HOME}/collector/meshcore.db | SQLAlchemy URL |
| TAGS_FILE | {DATA_HOME}/collector/tags.json | Path to tags JSON file |

### API
| Variable | Default | Description |
|----------|---------|-------------|
| API_HOST | 0.0.0.0 | API bind host |
| API_PORT | 8000 | API bind port |
| API_READ_KEY | | Read-only API key |
| API_ADMIN_KEY | | Admin API key |
| DATABASE_URL | sqlite:///{DATA_HOME}/collector/meshcore.db | SQLAlchemy URL |

### Web Dashboard
| Variable | Default | Description |
|----------|---------|-------------|
| WEB_HOST | 0.0.0.0 | Web bind host |
| WEB_PORT | 8080 | Web bind port |
| API_BASE_URL | http://localhost:8000 | API endpoint |
| API_KEY | | API key for queries |
| NETWORK_DOMAIN | | Network domain |
| NETWORK_NAME | MeshCore Network | Network name |
| NETWORK_CITY | | City location |
| NETWORK_COUNTRY | | Country code |
| NETWORK_LOCATION | | Lat,Lon |
| NETWORK_RADIO_CONFIG | | Radio config details |
| NETWORK_CONTACT_EMAIL | | Contact email |
| NETWORK_CONTACT_DISCORD | | Discord link |
| MEMBERS_FILE | {DATA_HOME}/web/members.json | Path to members JSON |

---

## Implementation Phases

### Phase 1: Foundation
1. Set up project structure with pyproject.toml
2. Configure development tools (black, flake8, mypy, pytest)
3. Set up pre-commit hooks
4. Implement `meshcore_common`:
   - Pydantic settings/config
   - SQLAlchemy models
   - Database connection management
   - MQTT client utilities
   - Logging configuration
5. Set up Alembic for migrations
6. Create initial migration

### Phase 2: Interface Component
1. Implement MeshCore device wrapper
2. Implement RECEIVER mode:
   - Event subscription
   - MQTT publishing
3. Implement SENDER mode:
   - MQTT subscription
   - Command dispatching
4. Implement mock device for testing
5. Create Click CLI
6. Write unit tests

### Phase 3: Collector Component
1. Implement MQTT subscriber
2. Implement event handlers for each event type
3. Implement database persistence
4. Create Click CLI
5. Write unit tests

### Phase 4: API Component
1. Set up FastAPI application
2. Implement authentication middleware
3. Implement all REST endpoints
4. Implement MQTT command publishing
5. Implement simple HTML dashboard
6. Add OpenAPI documentation
7. Create Click CLI
8. Write unit and integration tests

### Phase 5: Web Dashboard
1. Set up FastAPI with Jinja2 templates
2. Configure Tailwind CSS / DaisyUI
3. Implement all dashboard views
4. Add map functionality (Leaflet.js)
5. Create Click CLI
6. Write tests

### Phase 6: Docker & Deployment
1. Create multi-stage Dockerfile
2. Create docker-compose.yml with all services
3. Add health check endpoints
4. Document deployment procedures
5. End-to-end testing

---

## Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "click>=8.1.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.12.0",
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
    "paho-mqtt>=2.0.0",
    "meshcore-py>=0.1.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",
    "httpx>=0.25.0",
    "aiosqlite>=0.19.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "black>=23.0.0",
    "flake8>=6.1.0",
    "mypy>=1.5.0",
    "pre-commit>=3.4.0",
]
postgres = [
    "asyncpg>=0.28.0",
    "psycopg2-binary>=2.9.0",
]
```

---

## CLI Interface

```bash
# Main entrypoint
meshcore-hub <component> [options]

# Interface component
meshcore-hub interface --mode receiver --port /dev/ttyUSB0
meshcore-hub interface --mode sender --mock

# Collector component
meshcore-hub collector

# API component
meshcore-hub api --host 0.0.0.0 --port 8000

# Web dashboard
meshcore-hub web --host 0.0.0.0 --port 8080

# Database migrations
meshcore-hub db upgrade
meshcore-hub db downgrade
meshcore-hub db revision --message "description"
```

---

## Testing Strategy

### Unit Tests
- Test each module in isolation
- Mock external dependencies (MQTT, database, serial)
- Target 80%+ code coverage

### Integration Tests
- Test component interactions
- Use SQLite in-memory database
- Use mock MQTT broker

### End-to-End Tests
- Full system tests with Docker Compose
- Test complete event flow from mock device to API query

---

## Security Considerations

1. **API Authentication**: Bearer tokens with two permission levels
2. **Input Validation**: Pydantic validation on all inputs
3. **SQL Injection**: SQLAlchemy ORM prevents SQL injection
4. **MQTT Security**: Support for username/password authentication
5. **Secret Management**: Environment variables for secrets, never in code
6. **Rate Limiting**: Consider implementing for production deployments

---

## Future Enhancements (Out of Scope)

- WebSocket/SSE for real-time updates
- User management and role-based access
- Multi-tenant support
- Prometheus metrics
- Alerting system
- Mobile-responsive dashboard optimization
- Message encryption/decryption display
- Network topology visualization
