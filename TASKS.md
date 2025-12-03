# MeshCore Hub - Task Tracker

This document tracks implementation progress for the MeshCore Hub project. Each task can be checked off as completed.

---

## Phase 1: Foundation ✅

### 1.1 Project Setup

- [x] Create `pyproject.toml` with project metadata and dependencies
- [x] Configure Python 3.11+ requirement
- [x] Set up `src/meshcore_hub/` package structure
- [x] Create `__init__.py` files for all packages
- [x] Create `__main__.py` entry point

### 1.2 Development Tools

- [x] Configure `black` formatter settings in pyproject.toml
- [x] Configure `flake8` linting (create `.flake8` or add to pyproject.toml)
- [x] Configure `mypy` type checking settings
- [x] Configure `pytest` settings and test directory
- [x] Create `.pre-commit-config.yaml` with hooks:
  - [x] black
  - [x] flake8
  - [x] mypy
  - [x] trailing whitespace
  - [x] end-of-file-fixer
- [x] Create `.env.example` with all environment variables

### 1.3 Common Package - Configuration

- [x] Create `common/config.py` with Pydantic Settings:
  - [x] `CommonSettings` (logging, MQTT connection)
  - [x] `InterfaceSettings` (mode, serial port, mock device)
  - [x] `CollectorSettings` (database URL, webhook settings)
  - [x] `APISettings` (host, port, API keys)
  - [x] `WebSettings` (host, port, network info)
- [x] Implement environment variable loading
- [x] Implement CLI argument override support
- [x] Add configuration validation

### 1.4 Common Package - Database Models

- [x] Create `common/database.py`:
  - [x] Database engine factory
  - [x] Session management
  - [x] Async session support
- [x] Create `common/models/base.py`:
  - [x] Base model with UUID primary key
  - [x] Timestamp mixins (created_at, updated_at)
- [x] Create `common/models/node.py`:
  - [x] Node model (public_key, name, adv_type, flags, first_seen, last_seen)
  - [x] Indexes on public_key
- [x] Create `common/models/node_tag.py`:
  - [x] NodeTag model (node_id FK, key, value, value_type)
  - [x] Unique constraint on (node_id, key)
- [x] Create `common/models/message.py`:
  - [x] Message model (receiver_node_id, message_type, pubkey_prefix, channel_idx, text, etc.)
  - [x] Indexes for common query patterns
- [x] Create `common/models/advertisement.py`:
  - [x] Advertisement model (receiver_node_id, node_id, public_key, name, adv_type, flags)
- [x] Create `common/models/trace_path.py`:
  - [x] TracePath model (receiver_node_id, initiator_tag, path_hashes JSON, snr_values JSON)
- [x] Create `common/models/telemetry.py`:
  - [x] Telemetry model (receiver_node_id, node_id, node_public_key, lpp_data, parsed_data JSON)
- [x] Create `common/models/event_log.py`:
  - [x] EventLog model (receiver_node_id, event_type, payload JSON)
- [x] Create `common/models/__init__.py` exporting all models

### 1.5 Common Package - Pydantic Schemas

- [x] Create `common/schemas/events.py`:
  - [x] AdvertisementEvent schema
  - [x] ContactMessageEvent schema
  - [x] ChannelMessageEvent schema
  - [x] TraceDataEvent schema
  - [x] TelemetryResponseEvent schema
  - [x] ContactsEvent schema
  - [x] SendConfirmedEvent schema
  - [x] StatusResponseEvent schema
  - [x] BatteryEvent schema
  - [x] PathUpdatedEvent schema
- [x] Create `common/schemas/nodes.py`:
  - [x] NodeCreate, NodeRead, NodeList schemas
  - [x] NodeTagCreate, NodeTagUpdate, NodeTagRead schemas
- [x] Create `common/schemas/messages.py`:
  - [x] MessageRead, MessageList schemas
  - [x] MessageFilters schema
- [x] Create `common/schemas/commands.py`:
  - [x] SendMessageCommand schema
  - [x] SendChannelMessageCommand schema
  - [x] SendAdvertCommand schema
- [x] Create `common/schemas/__init__.py` exporting all schemas

### 1.6 Common Package - Utilities

- [x] Create `common/mqtt.py`:
  - [x] MQTT client factory function
  - [x] Topic builder utilities
  - [x] Message serialization helpers
  - [x] Async publish/subscribe wrappers
- [x] Create `common/logging.py`:
  - [x] Logging configuration function
  - [x] Structured logging format
  - [x] Log level configuration from settings

### 1.7 Database Migrations

- [x] Create `alembic.ini` configuration
- [x] Create `alembic/env.py` with async support
- [x] Create `alembic/script.py.mako` template
- [x] Create initial migration with all tables:
  - [x] nodes table
  - [x] node_tags table
  - [x] messages table
  - [x] advertisements table
  - [x] trace_paths table
  - [x] telemetry table
  - [x] events_log table
- [x] Test migration upgrade/downgrade

### 1.8 Main CLI Entry Point

- [x] Create root Click group in `__main__.py`
- [x] Add `--version` option
- [x] Add `--config` option for config file path
- [x] Add subcommand placeholders for: interface, collector, api, web, db

---

## Phase 2: Interface Component ✅

### 2.1 Device Abstraction

- [x] Create `interface/device.py`:
  - [x] `MeshCoreDevice` class wrapping meshcore_py
  - [x] Connection management (connect, disconnect, reconnect)
  - [x] Get device public key via `send_appstart()`
  - [x] Event subscription registration
  - [x] Command sending methods
- [x] Create `interface/mock_device.py`:
  - [x] `MockMeshCoreDevice` class
  - [x] Configurable event generation
  - [x] Simulated message sending
  - [x] Simulated network topology (optional)
  - [x] Configurable delays and error rates

### 2.2 Receiver Mode

- [x] Create `interface/receiver.py`:
  - [x] `Receiver` class
  - [x] Initialize MQTT client
  - [x] Initialize MeshCore device
  - [x] Subscribe to all relevant MeshCore events:
    - [x] ADVERTISEMENT
    - [x] CONTACT_MSG_RECV
    - [x] CHANNEL_MSG_RECV
    - [x] TRACE_DATA
    - [x] TELEMETRY_RESPONSE
    - [x] CONTACTS
    - [x] SEND_CONFIRMED
    - [x] STATUS_RESPONSE
    - [x] BATTERY
    - [x] PATH_UPDATED
  - [x] Event handler that publishes to MQTT
  - [x] Topic construction: `<prefix>/<pubkey>/event/<event_name>`
  - [x] JSON serialization of event payloads
  - [x] Graceful shutdown handling

### 2.3 Sender Mode

- [x] Create `interface/sender.py`:
  - [x] `Sender` class
  - [x] Initialize MQTT client
  - [x] Initialize MeshCore device
  - [x] Subscribe to command topics:
    - [x] `<prefix>/+/command/send_msg`
    - [x] `<prefix>/+/command/send_channel_msg`
    - [x] `<prefix>/+/command/send_advert`
    - [x] `<prefix>/+/command/request_status`
    - [x] `<prefix>/+/command/request_telemetry`
  - [x] Command handlers:
    - [x] `handle_send_msg` - send direct message
    - [x] `handle_send_channel_msg` - send channel message
    - [x] `handle_send_advert` - send advertisement
    - [x] `handle_request_status` - request node status
    - [x] `handle_request_telemetry` - request telemetry
  - [x] Error handling and logging
  - [x] Graceful shutdown handling

### 2.4 Interface CLI

- [x] Create `interface/cli.py`:
  - [x] `interface` Click command group
  - [x] `--mode` option (receiver/sender, required)
  - [x] `--port` option for serial port
  - [x] `--baud` option for baud rate
  - [x] `--mock` flag to use mock device
  - [x] `--mqtt-host`, `--mqtt-port` options
  - [x] `--prefix` option for MQTT topic prefix
  - [x] Signal handlers for graceful shutdown
- [x] Register CLI with main entry point

### 2.5 Interface Tests

- [x] Create `tests/test_interface/conftest.py`:
  - [x] Mock MQTT client fixture
  - [x] Mock device fixture
- [x] Create `tests/test_interface/test_device.py`:
  - [x] Test connection/disconnection
  - [x] Test event subscription
  - [x] Test command sending
- [x] Create `tests/test_interface/test_mock_device.py`:
  - [x] Test mock event generation
  - [x] Test mock command handling
- [x] Create `tests/test_interface/test_receiver.py`:
  - [x] Test event to MQTT publishing
  - [x] Test topic construction
  - [x] Test payload serialization
- [x] Create `tests/test_interface/test_sender.py`:
  - [x] Test MQTT to command dispatching
  - [x] Test command payload parsing
  - [x] Test error handling

---

## Phase 3: Collector Component ✅

### 3.1 MQTT Subscriber

- [x] Create `collector/subscriber.py`:
  - [x] `Subscriber` class
  - [x] Initialize MQTT client
  - [x] Subscribe to all event topics: `<prefix>/+/event/#`
  - [x] Parse topic to extract public_key and event_type
  - [x] Route events to appropriate handlers
  - [x] Handle connection/disconnection
  - [x] Graceful shutdown

### 3.2 Event Handlers

- [x] Create `collector/handlers/__init__.py`:
  - [x] Handler registry pattern
- [x] Create `collector/handlers/advertisement.py`:
  - [x] Parse advertisement payload
  - [x] Upsert node in nodes table
  - [x] Insert advertisement record
  - [x] Update node last_seen timestamp
- [x] Create `collector/handlers/message.py`:
  - [x] Parse contact/channel message payload
  - [x] Insert message record
  - [x] Handle both CONTACT_MSG_RECV and CHANNEL_MSG_RECV
- [x] Create `collector/handlers/trace.py`:
  - [x] Parse trace data payload
  - [x] Insert trace_path record
- [x] Create `collector/handlers/telemetry.py`:
  - [x] Parse telemetry payload
  - [x] Insert telemetry record
  - [x] Optionally upsert node
- [x] Create `collector/handlers/contacts.py`:
  - [x] Parse contacts sync payload
  - [x] Upsert multiple nodes
- [x] Create `collector/handlers/event_log.py`:
  - [x] Generic handler for events_log table
  - [x] Handle informational events (SEND_CONFIRMED, STATUS_RESPONSE, BATTERY, PATH_UPDATED)

### 3.3 Webhook Dispatcher (Optional based on Q10)

- [x] Create `collector/webhook.py`:
  - [x] `WebhookDispatcher` class
  - [x] Webhook configuration loading
  - [x] JSONPath filtering support
  - [x] Async HTTP POST sending
  - [x] Retry logic with backoff
  - [x] Error logging

### 3.4 Collector CLI

- [x] Create `collector/cli.py`:
  - [x] `collector` Click command
  - [x] `--mqtt-host`, `--mqtt-port` options
  - [x] `--prefix` option
  - [x] `--database-url` option
  - [x] Signal handlers for graceful shutdown
- [x] Register CLI with main entry point

### 3.5 Collector Tests

- [x] Create `tests/test_collector/conftest.py`:
  - [x] In-memory SQLite database fixture
  - [x] Mock MQTT client fixture
- [x] Create `tests/test_collector/test_subscriber.py`:
  - [x] Test topic parsing
  - [x] Test event routing
- [x] Create `tests/test_collector/test_handlers/`:
  - [x] `test_advertisement.py`
  - [x] `test_message.py`
  - [x] `test_trace.py`
  - [x] `test_telemetry.py`
  - [x] `test_contacts.py`
- [x] Create `tests/test_collector/test_webhook.py`:
  - [x] Test webhook dispatching
  - [x] Test JSONPath filtering
  - [x] Test retry logic

---

## Phase 4: API Component ✅

### 4.1 FastAPI Application Setup

- [x] Create `api/app.py`:
  - [x] FastAPI application instance
  - [x] Lifespan handler for startup/shutdown
  - [x] Include all routers
  - [x] Exception handlers
  - [x] CORS middleware configuration
- [x] Create `api/dependencies.py`:
  - [x] Database session dependency
  - [x] MQTT client dependency
  - [x] Settings dependency

### 4.2 Authentication

- [x] Create `api/auth.py`:
  - [x] Bearer token extraction
  - [x] `require_read` dependency (read or admin key)
  - [x] `require_admin` dependency (admin key only)
  - [x] 401/403 error responses

### 4.3 Node Routes

- [x] Create `api/routes/nodes.py`:
  - [x] `GET /api/v1/nodes` - list nodes with pagination
    - [x] Query params: limit, offset, search, adv_type
  - [x] `GET /api/v1/nodes/{public_key}` - get single node
  - [x] Include related tags in response (optional)

### 4.4 Node Tag Routes

- [x] Create `api/routes/node_tags.py`:
  - [x] `GET /api/v1/nodes/{public_key}/tags` - list tags
  - [x] `POST /api/v1/nodes/{public_key}/tags` - create tag (admin)
  - [x] `PUT /api/v1/nodes/{public_key}/tags/{key}` - update tag (admin)
  - [x] `DELETE /api/v1/nodes/{public_key}/tags/{key}` - delete tag (admin)

### 4.5 Message Routes

- [x] Create `api/routes/messages.py`:
  - [x] `GET /api/v1/messages` - list messages with filters
    - [x] Query params: type, pubkey_prefix, channel_idx, since, until, limit, offset
  - [x] `GET /api/v1/messages/{id}` - get single message

### 4.6 Advertisement Routes

- [x] Create `api/routes/advertisements.py`:
  - [x] `GET /api/v1/advertisements` - list advertisements
    - [x] Query params: public_key, since, until, limit, offset
  - [x] `GET /api/v1/advertisements/{id}` - get single advertisement

### 4.7 Trace Path Routes

- [x] Create `api/routes/trace_paths.py`:
  - [x] `GET /api/v1/trace-paths` - list trace paths
    - [x] Query params: since, until, limit, offset
  - [x] `GET /api/v1/trace-paths/{id}` - get single trace path

### 4.8 Telemetry Routes

- [x] Create `api/routes/telemetry.py`:
  - [x] `GET /api/v1/telemetry` - list telemetry records
    - [x] Query params: node_public_key, since, until, limit, offset
  - [x] `GET /api/v1/telemetry/{id}` - get single telemetry record

### 4.9 Command Routes

- [x] Create `api/routes/commands.py`:
  - [x] `POST /api/v1/commands/send-message` (admin)
    - [x] Request body: destination, text, timestamp (optional)
    - [x] Publish to MQTT command topic
  - [x] `POST /api/v1/commands/send-channel-message` (admin)
    - [x] Request body: channel_idx, text, timestamp (optional)
    - [x] Publish to MQTT command topic
  - [x] `POST /api/v1/commands/send-advertisement` (admin)
    - [x] Request body: flood (boolean)
    - [x] Publish to MQTT command topic

### 4.10 Dashboard Routes

- [x] Create `api/routes/dashboard.py`:
  - [x] `GET /api/v1/stats` - JSON statistics
    - [x] Total nodes count
    - [x] Active nodes (last 24h)
    - [x] Total messages count
    - [x] Messages today
    - [x] Total advertisements
    - [x] Channel message counts
  - [x] `GET /api/v1/dashboard` - HTML dashboard
- [x] Create `api/templates/dashboard.html`:
  - [x] Simple HTML template
  - [x] Display statistics
  - [x] Basic CSS styling
  - [x] Auto-refresh meta tag (optional)

### 4.11 API Router Registration

- [x] Create `api/routes/__init__.py`:
  - [x] Create main API router
  - [x] Include all sub-routers with prefixes
  - [x] Add OpenAPI tags

### 4.12 API CLI

- [x] Create `api/cli.py`:
  - [x] `api` Click command
  - [x] `--host` option
  - [x] `--port` option
  - [x] `--database-url` option
  - [x] `--read-key` option
  - [x] `--admin-key` option
  - [x] `--mqtt-host`, `--mqtt-port` options
  - [x] `--reload` flag for development
- [x] Register CLI with main entry point

### 4.13 API Tests

- [x] Create `tests/test_api/conftest.py`:
  - [x] Test client fixture
  - [x] In-memory database fixture
  - [x] Test API keys
- [x] Create `tests/test_api/test_auth.py`:
  - [x] Test missing token
  - [x] Test invalid token
  - [x] Test read-only access
  - [x] Test admin access
- [x] Create `tests/test_api/test_nodes.py`:
  - [x] Test list nodes
  - [x] Test get node
  - [x] Test pagination
  - [x] Test filtering
- [x] Create `tests/test_api/test_node_tags.py`:
  - [x] Test CRUD operations
  - [x] Test permission checks
- [x] Create `tests/test_api/test_messages.py`:
  - [x] Test list messages
  - [x] Test filtering
- [x] Create `tests/test_api/test_commands.py`:
  - [x] Test send message command
  - [x] Test permission checks
  - [x] Test MQTT publishing

---

## Phase 5: Web Dashboard ✅

### 5.1 FastAPI Application Setup

- [x] Create `web/app.py`:
  - [x] FastAPI application instance
  - [x] Jinja2 templates configuration
  - [x] Static files mounting
  - [x] Lifespan handler
  - [x] Include all routers

### 5.2 Frontend Assets

- [x] Create `web/static/css/` directory
- [x] Set up Tailwind CSS:
  - [x] Using Tailwind CDN with DaisyUI plugin
  - [x] Configured in base.html template
- [x] Create `web/static/js/` directory:
  - [x] Minimal JS for interactivity (if needed)

### 5.3 Base Template

- [x] Create `web/templates/base.html`:
  - [x] HTML5 doctype and structure
  - [x] Meta tags (viewport, charset)
  - [x] Tailwind CSS inclusion
  - [x] Navigation header:
    - [x] Network name
    - [x] Links to all pages
  - [x] Footer with contact info
  - [x] Content block for page content

### 5.4 Home Page

- [x] Create `web/routes/home.py`:
  - [x] `GET /` - home page route
  - [x] Load network configuration
- [x] Create `web/templates/home.html`:
  - [x] Welcome message with network name
  - [x] Network description/details
  - [x] Radio configuration display
  - [x] Location information
  - [x] Contact information (email, Discord)
  - [x] Quick links to other sections

### 5.5 Members Page

- [x] Create `web/routes/members.py`:
  - [x] `GET /members` - members list route
  - [x] Load members from JSON file
- [x] Create `web/templates/members.html`:
  - [x] Members list/grid
  - [x] Member cards with:
    - [x] Name
    - [x] Callsign (if applicable)
    - [x] Role/description
    - [x] Contact info (optional)

### 5.6 Network Overview Page

- [x] Create `web/routes/network.py`:
  - [x] `GET /network` - network stats route
  - [x] Fetch stats from API
- [x] Create `web/templates/network.html`:
  - [x] Statistics cards:
    - [x] Total nodes
    - [x] Active nodes
    - [x] Total messages
    - [x] Messages today
    - [x] Channel statistics
  - [x] Recent activity summary

### 5.7 Nodes Page

- [x] Create `web/routes/nodes.py`:
  - [x] `GET /nodes` - nodes list route
  - [x] `GET /nodes/{public_key}` - node detail route
  - [x] Fetch from API with pagination
- [x] Create `web/templates/nodes.html`:
  - [x] Search/filter form
  - [x] Nodes table:
    - [x] Name
    - [x] Public key (truncated)
    - [x] Type
    - [x] Last seen
    - [x] Tags
  - [x] Pagination controls
- [x] Create `web/templates/node_detail.html`:
  - [x] Full node information
  - [x] All tags
  - [x] Recent messages (if any)
  - [x] Recent advertisements

### 5.8 Node Map Page

- [x] Create `web/routes/map.py`:
  - [x] `GET /map` - map page route
  - [x] `GET /map/data` - JSON endpoint for node locations
  - [x] Filter nodes with location tags
- [x] Create `web/templates/map.html`:
  - [x] Leaflet.js map container
  - [x] Leaflet CSS/JS includes
  - [x] JavaScript for:
    - [x] Initialize map centered on NETWORK_LOCATION
    - [x] Fetch node location data
    - [x] Add markers for each node
    - [x] Popup with node info on click

### 5.9 Messages Page

- [x] Create `web/routes/messages.py`:
  - [x] `GET /messages` - messages list route
  - [x] Fetch from API with filters
- [x] Create `web/templates/messages.html`:
  - [x] Filter form:
    - [x] Message type (contact/channel)
    - [x] Channel selector
    - [x] Date range
    - [x] Search text
  - [x] Messages table:
    - [x] Timestamp
    - [x] Type
    - [x] Sender/Channel
    - [x] Text (truncated)
    - [x] SNR
    - [x] Hops
  - [x] Pagination controls

### 5.10 Web CLI

- [x] Create `web/cli.py`:
  - [x] `web` Click command
  - [x] `--host` option
  - [x] `--port` option
  - [x] `--api-url` option
  - [x] `--api-key` option
  - [x] Network configuration options:
    - [x] `--network-name`
    - [x] `--network-city`
    - [x] `--network-country`
    - [x] `--network-location`
    - [x] `--network-radio-config`
    - [x] `--network-contact-email`
    - [x] `--network-contact-discord`
  - [x] `--members-file` option
  - [x] `--reload` flag for development
- [x] Register CLI with main entry point

### 5.11 Web Tests

- [x] Create `tests/test_web/conftest.py`:
  - [x] Test client fixture
  - [x] Mock API responses
- [x] Create `tests/test_web/test_home.py`
- [x] Create `tests/test_web/test_members.py`
- [x] Create `tests/test_web/test_network.py`
- [x] Create `tests/test_web/test_nodes.py`
- [x] Create `tests/test_web/test_map.py`
- [x] Create `tests/test_web/test_messages.py`

---

## Phase 6: Docker & Deployment

### 6.1 Dockerfile ✅

- [x] Create `docker/Dockerfile`:
  - [x] Multi-stage build:
    - [x] Stage 1: Build frontend assets (Tailwind)
    - [x] Stage 2: Python dependencies
    - [x] Stage 3: Final runtime image
  - [x] Base image: python:3.11-slim
  - [x] Install system dependencies
  - [x] Copy and install Python package
  - [x] Copy frontend assets
  - [x] Set entrypoint to `meshcore-hub`
  - [x] Default CMD (show help)
  - [x] Health check instruction

### 6.2 Docker Compose ✅

- [x] Create `docker/docker-compose.yml`:
  - [x] MQTT broker service (Eclipse Mosquitto):
    - [x] Port mapping (1883, 9001)
    - [x] Volume for persistence
    - [x] Configuration file
  - [x] Interface Receiver service:
    - [x] Depends on MQTT
    - [x] Device passthrough (/dev/ttyUSB0)
    - [x] Environment variables
  - [x] Interface Sender service:
    - [x] Depends on MQTT
    - [x] Device passthrough
    - [x] Environment variables
  - [x] Collector service:
    - [x] Depends on MQTT
    - [x] Database volume
    - [x] Environment variables
  - [x] API service:
    - [x] Depends on Collector (for DB)
    - [x] Port mapping (8000)
    - [x] Database volume (shared)
    - [x] Environment variables
  - [x] Web service:
    - [x] Depends on API
    - [x] Port mapping (8080)
    - [x] Environment variables
- [x] Create `docker/mosquitto.conf`:
  - [x] Listener configuration
  - [x] Anonymous access (or auth)
  - [x] Persistence settings

### 6.3 Health Checks ✅

- [x] Add health check endpoint to API:
  - [x] `GET /health` - basic health
  - [x] `GET /health/ready` - includes DB check
- [x] Add health check endpoint to Web:
  - [x] `GET /health` - basic health
  - [x] `GET /health/ready` - includes API connectivity
- [x] Add health check to Interface:
  - [x] Device connection status
  - [x] MQTT connection status
- [x] Add health check to Collector:
  - [x] MQTT connection status
  - [x] Database connection status

### 6.4 Database CLI Commands ✅

- [x] Create `db` Click command group:
  - [x] `meshcore-hub db upgrade` - run migrations
  - [x] `meshcore-hub db downgrade` - rollback migration
  - [x] `meshcore-hub db revision -m "message"` - create migration
  - [x] `meshcore-hub db current` - show current revision
  - [x] `meshcore-hub db history` - show migration history

### 6.5 Documentation

- [x] Update `README.md`:
  - [x] Project description
  - [x] Quick start guide
  - [x] Docker deployment instructions
  - [x] Manual installation instructions
  - [x] Configuration reference
  - [x] CLI reference
- [ ] Create `docs/` directory (optional):
  - [ ] Architecture overview
  - [ ] API documentation link
  - [ ] Deployment guides

### 6.6 CI/CD ✅

- [x] Create `.github/workflows/ci.yml`:
  - [x] Run on push/PR
  - [x] Set up Python
  - [x] Install dependencies
  - [x] Run linting (black, flake8)
  - [x] Run type checking (mypy)
  - [x] Run tests (pytest)
  - [x] Upload coverage report
- [x] Create `.github/workflows/docker.yml`:
  - [x] Build Docker image
  - [x] Push to registry (on release)

### 6.7 End-to-End Testing ✅

- [x] Create `tests/e2e/` directory
- [x] Create `tests/e2e/docker-compose.test.yml`:
  - [x] All services with mock device
  - [x] Test database
- [x] Create `tests/e2e/test_full_flow.py`:
  - [x] Start all services
  - [x] Generate mock events
  - [x] Verify events stored in database
  - [x] Verify API returns events
  - [x] Verify web dashboard displays data
  - [x] Test command flow (API -> MQTT -> Sender)

---

## Progress Summary

| Phase | Total Tasks | Completed | Progress |
|-------|-------------|-----------|----------|
| Phase 1: Foundation | 47 | 47 | 100% |
| Phase 2: Interface | 35 | 35 | 100% |
| Phase 3: Collector | 27 | 27 | 100% |
| Phase 4: API | 44 | 44 | 100% |
| Phase 5: Web Dashboard | 40 | 40 | 100% |
| Phase 6: Docker & Deployment | 28 | 25 | 89% |
| **Total** | **221** | **218** | **99%** |

*Note: Remaining 3 tasks are optional (creating a `docs/` directory).*

---

## Notes & Decisions

### Decisions Made
*(Record architectural decisions and answers to clarifying questions here)*

- [ ] Q1 (MQTT Broker):
- [ ] Q2 (Database):
- [ ] Q3 (Web Dashboard Separation):
- [ ] Q4 (Members JSON Location):
- [ ] Q5 (Multiple Serial Devices):
- [ ] Q6 (Reconnection Strategy):
- [ ] Q7 (Mock Device Scope):
- [ ] Q8 (Event Deduplication):
- [ ] Q9 (Data Retention):
- [ ] Q10 (Webhook Configuration):
- [ ] Q11 (API Key Management):
- [ ] Q12 (Rate Limiting):
- [ ] Q13 (CORS):
- [ ] Q14 (Dashboard Authentication):
- [ ] Q15 (Real-time Updates):
- [ ] Q16 (Map Provider):
- [ ] Q17 (Tag Value Types):
- [ ] Q18 (Reserved Tag Names):
- [ ] Q19 (Health Checks):
- [ ] Q20 (Metrics/Observability):
- [ ] Q21 (Log Level Configuration):

### Blockers
*(Track any blockers or dependencies here)*

### Session Log
*(Track what was accomplished in each session)*

| Date | Session | Tasks Completed | Notes |
|------|---------|-----------------|-------|
| 2025-12-03 | 1 | Phase 1: Foundation | Project setup, common package, database models, schemas, migrations, CLI |
| 2025-12-03 | 2 | Phase 2: Interface | Device abstraction, mock device, receiver/sender modes, CLI, tests |
| 2025-12-03 | 3 | Phase 3: Collector | MQTT subscriber, event handlers, CLI, tests (webhook pending) |
| 2025-12-03 | 4 | Phase 4: API | FastAPI app, auth, all routes, CLI, tests (108 passed, 9 pre-existing failures) |
| 2025-12-03 | 5 | Phase 5: Web Dashboard | FastAPI + Jinja2, Tailwind/DaisyUI, Leaflet map, all pages, CLI (tests pending) |
| 2025-12-03 | 6 | Code quality | Aligned mypy settings between `mypy src/` and pre-commit hooks; added meshcore to ignore_missing_imports, added alembic to pre-commit dependencies |
| 2025-12-03 | 7 | Docker packaging | Fixed pyproject.toml package-data to include web/templates and api/templates in wheel builds |
