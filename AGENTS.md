# AGENTS.md - AI Coding Assistant Guidelines

This document provides context and guidelines for AI coding assistants working on the MeshCore Hub project.

## Agent Rules

* You MUST use Python (version in `.python-version` file)
* You MUST activate a Python virtual environment in the `.venv` directory or create one if it does not exist:
  - `ls ./.venv` to check if it exists
  - `python -m venv .venv` to create it
* You MUST always activate the virtual environment before running any commands
  - `source .venv/bin/activate`
* You MUST install all project dependencies using `pip install -e ".[dev]"` command`
* You MUST install `pre-commit` for quality checks
* Before commiting:
  - Run **targeted tests** for the components you changed, not the full suite:
    - `pytest tests/test_web/` for web-only changes (templates, static JS, web routes)
    - `pytest tests/test_api/` for API changes
    - `pytest tests/test_collector/` for collector changes
    - `pytest tests/test_interface/` for interface/sender/receiver changes
    - `pytest tests/test_common/` for common models/schemas/config changes
    - Only run the full `pytest` if changes span multiple components
  - Run `pre-commit run --all-files` to perform all quality checks

## Project Overview

MeshCore Hub is a Python 3.13+ monorepo for managing and orchestrating MeshCore mesh networks. It consists of five main components:

- **meshcore_interface**: Serial/USB interface to MeshCore companion nodes, publishes/subscribes to MQTT
- **meshcore_collector**: Collects MeshCore events from MQTT and stores them in a database
- **meshcore_api**: REST API for querying data and sending commands via MQTT
- **meshcore_web**: Web dashboard for visualizing network status
- **meshcore_common**: Shared utilities, models, and configurations

## Key Documentation

- [PROMPT.md](PROMPT.md) - Original project specification and requirements
- [SCHEMAS.md](SCHEMAS.md) - MeshCore event JSON schemas and database mappings
- [PLAN.md](PLAN.md) - Implementation plan and architecture decisions
- [TASKS.md](TASKS.md) - Detailed task breakdown with checkboxes for progress tracking

## Technology Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.13+ |
| Package Management | pip with pyproject.toml |
| CLI Framework | Click |
| Configuration | Pydantic Settings |
| Database ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| REST API | FastAPI |
| MQTT Client | paho-mqtt |
| MeshCore Interface | meshcore |
| Templates | Jinja2 (server), lit-html (SPA) |
| Frontend | ES Modules SPA with client-side routing |
| CSS Framework | Tailwind CSS + DaisyUI |
| Testing | pytest, pytest-asyncio |
| Formatting | black |
| Linting | flake8 |
| Type Checking | mypy |

## Code Style Guidelines

### General

- Follow PEP 8 style guidelines
- Use `black` for code formatting (line length 88)
- Use type hints for all function signatures
- Write docstrings for public modules, classes, and functions
- Keep functions focused and under 50 lines where possible

### Imports

```python
# Standard library
import os
from datetime import datetime
from typing import Optional

# Third-party
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy import select

# Local
from meshcore_hub.common.config import Settings
from meshcore_hub.common.models import Node
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Modules | snake_case | `node_tags.py` |
| Classes | PascalCase | `NodeTagCreate` |
| Functions | snake_case | `get_node_by_key()` |
| Constants | UPPER_SNAKE_CASE | `DEFAULT_MQTT_PORT` |
| Variables | snake_case | `public_key` |
| Type Variables | PascalCase | `T`, `NodeT` |

### Pydantic Models

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class NodeRead(BaseModel):
    """Schema for reading node data from API."""

    id: str
    public_key: str = Field(..., min_length=64, max_length=64)
    name: Optional[str] = None
    adv_type: Optional[str] = None
    last_seen: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

### SQLAlchemy Models

```python
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

class Node(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "nodes"

    public_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adv_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    tags: Mapped[list["NodeTag"]] = relationship(back_populates="node", cascade="all, delete-orphan")


class Member(Base, UUIDMixin, TimestampMixin):
    """Network member model - stores info about network operators."""
    __tablename__ = "members"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    callsign: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    public_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
```

### FastAPI Routes

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from meshcore_hub.api.dependencies import get_db, require_read
from meshcore_hub.common.schemas import NodeRead, NodeList

router = APIRouter(prefix="/nodes", tags=["nodes"])

@router.get("", response_model=NodeList)
async def list_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_read)],
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
) -> NodeList:
    """List all nodes with pagination."""
    # Implementation
    pass
```

### Click CLI Commands

```python
import click
from meshcore_hub.common.config import Settings

@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """MeshCore Hub CLI."""
    ctx.ensure_object(dict)

@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.pass_context
def api(ctx: click.Context, host: str, port: int) -> None:
    """Start the API server."""
    import uvicorn
    from meshcore_hub.api.app import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port)
```

### Async Patterns

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    await setup_database()
    await connect_mqtt()

    yield

    # Shutdown
    await disconnect_mqtt()
    await close_database()
```

### Error Handling

```python
from fastapi import HTTPException, status

# Use specific HTTP exceptions
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Node with public_key '{public_key}' not found"
)

# Log exceptions with context
import logging
logger = logging.getLogger(__name__)

try:
    result = await risky_operation()
except SomeException as e:
    logger.exception("Failed to perform operation: %s", e)
    raise
```

## Project Structure

```
meshcore-hub/
├── src/meshcore_hub/
│   ├── __init__.py
│   ├── __main__.py           # CLI entry point
│   ├── common/
│   │   ├── config.py         # Pydantic settings
│   │   ├── database.py       # DB session management
│   │   ├── mqtt.py           # MQTT utilities
│   │   ├── logging.py        # Logging config
│   │   ├── models/           # SQLAlchemy models
│   │   │   ├── node.py       # Node model
│   │   │   ├── member.py     # Network member model
│   │   │   └── ...
│   │   └── schemas/          # Pydantic schemas
│   │       ├── members.py    # Member API schemas
│   │       └── ...
│   ├── interface/
│   │   ├── cli.py
│   │   ├── device.py         # MeshCore device wrapper
│   │   ├── mock_device.py    # Mock for testing
│   │   ├── receiver.py       # RECEIVER mode
│   │   └── sender.py         # SENDER mode
│   ├── collector/
│   │   ├── cli.py            # Collector CLI with seed commands
│   │   ├── subscriber.py     # MQTT subscriber
│   │   ├── cleanup.py        # Data retention/cleanup service
│   │   ├── tag_import.py     # Tag import from YAML
│   │   ├── member_import.py  # Member import from YAML
│   │   ├── handlers/         # Event handlers
│   │   └── webhook.py        # Webhook dispatcher
│   ├── api/
│   │   ├── cli.py
│   │   ├── app.py            # FastAPI app
│   │   ├── auth.py           # Authentication
│   │   ├── dependencies.py
│   │   └── routes/           # API routes
│   │       ├── members.py    # Member CRUD endpoints
│   │       └── ...
│   └── web/
│       ├── cli.py
│       ├── app.py            # FastAPI app
│       ├── pages.py          # Custom markdown page loader
│       ├── templates/        # Jinja2 templates (spa.html shell)
│       └── static/
│           ├── css/app.css   # Custom styles
│           └── js/spa/       # SPA frontend (ES modules)
│               ├── app.js        # Entry point, route registration
│               ├── router.js     # Client-side History API router
│               ├── api.js        # API fetch helper
│               ├── components.js # Shared UI components (lit-html)
│               ├── icons.js      # SVG icon functions (lit-html)
│               └── pages/        # Page modules (lazy-loaded)
│                   ├── home.js, dashboard.js, nodes.js, ...
│                   └── admin/    # Admin page modules
├── tests/
│   ├── conftest.py
│   ├── test_common/
│   ├── test_interface/
│   ├── test_collector/
│   ├── test_api/
│   └── test_web/
├── alembic/
│   ├── env.py
│   └── versions/
├── etc/
│   └── mosquitto.conf        # MQTT broker configuration
├── example/
│   ├── seed/                 # Example seed data files
│   │   ├── node_tags.yaml    # Example node tags
│   │   └── members.yaml      # Example network members
│   └── content/              # Example custom content
│       ├── pages/            # Example custom pages
│       └── media/            # Example media files
├── seed/                     # Seed data directory (SEED_HOME)
│   ├── node_tags.yaml        # Node tags for import
│   └── members.yaml          # Network members for import
├── data/                     # Runtime data (gitignored, DATA_HOME default)
│   └── collector/            # Collector data
│       └── meshcore.db       # SQLite database
├── Dockerfile                # Docker build configuration
└── docker-compose.yml        # Docker Compose services
```

## MQTT Topic Structure

### Events (Published by Interface RECEIVER)
```
<prefix>/<public_key>/event/<event_name>
```

Examples:
- `meshcore/abc123.../event/advertisement`
- `meshcore/abc123.../event/contact_msg_recv`
- `meshcore/abc123.../event/channel_msg_recv`

### Commands (Subscribed by Interface SENDER)
```
<prefix>/+/command/<command_name>
```

Examples:
- `meshcore/+/command/send_msg`
- `meshcore/+/command/send_channel_msg`
- `meshcore/+/command/send_advert`

## Database Conventions

- Use UUIDs for primary keys (stored as VARCHAR(36))
- Use `public_key` (64-char hex) as the canonical node identifier
- All timestamps stored as UTC
- JSON columns for flexible data (path_hashes, parsed_data, etc.)
- Foreign keys reference nodes by UUID, not public_key

## Testing Guidelines

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_mqtt_client():
    client = AsyncMock()
    client.publish = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_receiver_publishes_event(mock_mqtt_client):
    """Test that receiver publishes events to correct MQTT topic."""
    # Arrange
    receiver = Receiver(mqtt_client=mock_mqtt_client, prefix="test")

    # Act
    await receiver.handle_advertisement(event_data)

    # Assert
    mock_mqtt_client.publish.assert_called_once()
    call_args = mock_mqtt_client.publish.call_args
    assert "test/" in call_args[0][0]
    assert "/event/advertisement" in call_args[0][0]
```

### Integration Tests

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

@pytest.fixture
async def client(db_session):
    """Create test client with database session."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

## Common Tasks

### Adding a New API Endpoint

1. Create/update Pydantic schema in `common/schemas/`
2. Add route function in appropriate `api/routes/` module
3. Include router in `api/routes/__init__.py` if new module
4. Add tests in `tests/test_api/`
5. Update OpenAPI documentation if needed

### Adding a New Event Handler

1. Create handler in `collector/handlers/`
2. Register handler in `collector/handlers/__init__.py`
3. Add corresponding Pydantic schema if needed
4. Create/update database model if persisted
5. Add Alembic migration if schema changed
6. Add tests in `tests/test_collector/`

### Adding a New SPA Page

The web dashboard is a Single Page Application. Pages are ES modules loaded by the client-side router.

1. Create a page module in `web/static/js/spa/pages/` (e.g., `my-page.js`)
2. Export an `async function render(container, params, router)` that renders into `container` using `litRender(html\`...\`, container)`
3. Register the route in `web/static/js/spa/app.js` with `router.addRoute('/my-page', pageHandler(pages.myPage))`
4. Add the page title to `updatePageTitle()` in `app.js`
5. Add a nav link in `web/templates/spa.html` (both mobile and desktop menus)

**Key patterns:**
- Import `html`, `litRender`, `nothing` from `../components.js` (re-exports lit-html)
- Use `apiGet()` from `../api.js` for API calls
- For list pages with filters, use the `renderPage()` pattern: render the page header immediately, then re-render with the filter form + results after fetch (keeps the form out of the shell to avoid layout shift from data-dependent filter selects)
- Old page content stays visible until data is ready (navbar spinner indicates loading)
- Use `pageColors` from `components.js` for section-specific colors (reads CSS custom properties from `app.css`)
- Return a cleanup function if the page creates resources (e.g., Leaflet maps, Chart.js instances)

### Internationalization (i18n)

The web dashboard supports internationalization via JSON translation files. The default language is English.

**Translation files location:** `src/meshcore_hub/web/static/locales/`

**Key files:**
- `en.json` - English translations (reference implementation)
- `languages.md` - Comprehensive translation reference guide for translators

**Using translations in JavaScript:**

Import the `t()` function from `components.js`:

```javascript
import { t } from '../components.js';

// Simple translation
const label = t('common.save');  // "Save"

// Translation with variable interpolation
const title = t('common.add_entity', { entity: t('entities.node') });  // "Add Node"

// Composed patterns for consistency
const emptyMsg = t('common.no_entity_found', { entity: t('entities.nodes').toLowerCase() });  // "No nodes found"
```

**Translation architecture:**

1. **Entity-based composition:** Core entity names (`entities.*`) are referenced by composite patterns for consistency
2. **Reusable patterns:** Common UI patterns (`common.*`) use `{{variable}}` interpolation for dynamic content
3. **Separation of concerns:**
   - Keys without `_label` suffix = table headers (title case, no colon)
   - Keys with `_label` suffix = inline labels (sentence case, with colon)

**When adding/modifying translations:**

1. **Add new keys** to `en.json` following existing patterns:
   - Use composition when possible (reference `entities.*` in `common.*` patterns)
   - Group related keys by section (e.g., `admin_members.*`, `admin_node_tags.*`)
   - Use `{{variable}}` syntax for dynamic content

2. **Update `languages.md`** with:
   - Key name, English value, and usage context
   - Variable descriptions if using interpolation
   - Notes about HTML content or special formatting

3. **Add tests** in `tests/test_common/test_i18n.py`:
   - Test new interpolation patterns
   - Test required sections if adding new top-level sections
   - Test composed patterns with entity references

4. **Run i18n tests:**
   ```bash
   pytest tests/test_common/test_i18n.py -v
   ```

**Best practices:**

- **Avoid duplication:** Use `common.*` patterns instead of duplicating similar strings
- **Compose with entities:** Reference `entities.*` keys in patterns rather than hardcoding entity names
- **Preserve variables:** Keep `{{variable}}` placeholders unchanged when translating
- **Test composition:** Verify patterns work with all entity types (singular/plural, lowercase/uppercase)
- **Document context:** Always update `languages.md` so translators understand usage

**Example - adding a new entity and patterns:**

```javascript
// 1. Add entity to en.json
"entities": {
  "sensor": "Sensor"
}

// 2. Use with existing common patterns
t('common.add_entity', { entity: t('entities.sensor') })  // "Add Sensor"
t('common.no_entity_found', { entity: t('entities.sensors').toLowerCase() })  // "No sensors found"

// 3. Update languages.md with context
// 4. Add test to test_i18n.py
```

**Translation loading:**

The i18n system (`src/meshcore_hub/common/i18n.py`) loads translations on startup:
- Defaults to English (`en`)
- Falls back to English for missing keys
- Returns the key itself if translation not found

For full translation guidelines, see `src/meshcore_hub/web/static/locales/languages.md`.

### Adding a New Database Model

1. Create model in `common/models/`
2. Export in `common/models/__init__.py`
3. Create Alembic migration: `meshcore-hub db revision --autogenerate -m "description"`
4. Review and adjust migration file
5. Test migration: `meshcore-hub db upgrade`

### Running the Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run pre-commit hooks
pre-commit install
pre-commit run --all-files

# Run tests
pytest

# Run specific component
meshcore-hub api --reload
meshcore-hub collector
meshcore-hub interface receiver --mock
```

## Environment Variables

See [PLAN.md](PLAN.md#configuration-environment-variables) for complete list.

Key variables:
- `DATA_HOME` - Base directory for runtime data (default: `./data`)
- `SEED_HOME` - Directory containing seed data files (default: `./seed`)
- `CONTENT_HOME` - Directory containing custom content (pages, media) (default: `./content`)
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_PREFIX` - MQTT broker connection
- `MQTT_TLS` - Enable TLS/SSL for MQTT (default: `false`)
- `API_READ_KEY`, `API_ADMIN_KEY` - API authentication keys
- `WEB_ADMIN_ENABLED` - Enable admin interface at /a/ (default: `false`, requires auth proxy)
- `WEB_THEME` - Default theme for the web dashboard (default: `dark`, options: `dark`, `light`). Users can override via the theme toggle in the navbar, which persists their preference in browser localStorage.
- `TZ` - Timezone for web dashboard date/time display (default: `UTC`, e.g., `America/New_York`, `Europe/London`)
- `FEATURE_DASHBOARD`, `FEATURE_NODES`, `FEATURE_ADVERTISEMENTS`, `FEATURE_MESSAGES`, `FEATURE_MAP`, `FEATURE_MEMBERS`, `FEATURE_PAGES` - Feature flags to enable/disable specific web dashboard pages (default: all `true`). Dependencies: Dashboard auto-disables when all of Nodes/Advertisements/Messages are disabled. Map auto-disables when Nodes is disabled.
- `LOG_LEVEL` - Logging verbosity

The database defaults to `sqlite:///{DATA_HOME}/collector/meshcore.db` and does not typically need to be configured.

### Directory Structure

**Seed Data (`SEED_HOME`)** - Contains initial data files for database seeding:
```
${SEED_HOME}/
├── node_tags.yaml    # Node tags (keyed by public_key)
└── members.yaml      # Network members list
```

**Custom Content (`CONTENT_HOME`)** - Contains custom pages and media for the web dashboard:
```
${CONTENT_HOME}/
├── pages/            # Custom markdown pages
│   ├── about.md      # Example: About page (/pages/about)
│   ├── faq.md        # Example: FAQ page (/pages/faq)
│   └── getting-started.md # Example: Getting Started (/pages/getting-started)
└── media/            # Custom media files
    └── images/
        └── logo.svg  # Custom logo (replaces default favicon and navbar/home logo)
```

Pages use YAML frontmatter for metadata:
```markdown
---
title: About Us        # Browser tab title and nav link (not rendered on page)
slug: about            # URL path (default: filename without .md)
menu_order: 10         # Nav sort order (default: 100, lower = earlier)
---

# About Our Network

Markdown content here (include your own heading)...
```

**Runtime Data (`DATA_HOME`)** - Contains runtime data (gitignored):
```
${DATA_HOME}/
└── collector/
    └── meshcore.db   # SQLite database
```

Services automatically create their subdirectories if they don't exist.

### Seeding

The database can be seeded with node tags and network members from YAML files in `SEED_HOME`:
- `node_tags.yaml` - Node tag definitions (keyed by public_key)
- `members.yaml` - Network member definitions

**Important:** Seeding is NOT automatic and must be run explicitly. This prevents seed files from overwriting user changes made via the admin UI.

```bash
# Native CLI
meshcore-hub collector seed

# With Docker Compose
docker compose --profile seed up
```

**Note:** Once the admin UI is enabled (`WEB_ADMIN_ENABLED=true`), tags should be managed through the web interface rather than seed files.

### Webhook Configuration

The collector supports forwarding events to external HTTP endpoints:

| Variable | Description |
|----------|-------------|
| `WEBHOOK_ADVERTISEMENT_URL` | Webhook for node advertisement events |
| `WEBHOOK_ADVERTISEMENT_SECRET` | Secret sent as `X-Webhook-Secret` header |
| `WEBHOOK_MESSAGE_URL` | Webhook for all message events (channel + direct) |
| `WEBHOOK_MESSAGE_SECRET` | Secret for message webhook |
| `WEBHOOK_CHANNEL_MESSAGE_URL` | Override for channel messages only |
| `WEBHOOK_DIRECT_MESSAGE_URL` | Override for direct messages only |
| `WEBHOOK_TIMEOUT` | Request timeout (default: 10.0s) |
| `WEBHOOK_MAX_RETRIES` | Max retries on failure (default: 3) |
| `WEBHOOK_RETRY_BACKOFF` | Exponential backoff multiplier (default: 2.0) |

### Data Retention / Cleanup Configuration

The collector supports automatic cleanup of old event data and inactive nodes:

**Event Data Cleanup:**

| Variable | Description |
|----------|-------------|
| `DATA_RETENTION_ENABLED` | Enable automatic event data cleanup (default: true) |
| `DATA_RETENTION_DAYS` | Days to retain event data (default: 30) |
| `DATA_RETENTION_INTERVAL_HOURS` | Hours between cleanup runs (default: 24) |

When enabled, the collector automatically deletes event data older than the retention period:
- Advertisements
- Messages (channel and direct)
- Telemetry
- Trace paths
- Event logs

**Node Cleanup:**

| Variable | Description |
|----------|-------------|
| `NODE_CLEANUP_ENABLED` | Enable automatic cleanup of inactive nodes (default: true) |
| `NODE_CLEANUP_DAYS` | Remove nodes not seen for this many days (default: 7) |

When enabled, the collector automatically removes nodes where:
- `last_seen` is older than the configured number of days
- Nodes with `last_seen=NULL` (never seen on network) are **NOT** removed
- Nodes created via tag import that have never been seen on the mesh are preserved

**Note:** Both event data and node cleanup run on the same schedule (DATA_RETENTION_INTERVAL_HOURS).

**Contact Cleanup (Interface RECEIVER):**

The interface RECEIVER mode can automatically remove stale contacts from the MeshCore companion node's contact database. This prevents the companion node from resyncing old/dead contacts back to the collector, freeing up memory on the device (typically limited to ~100 contacts).

| Variable | Description |
|----------|-------------|
| `CONTACT_CLEANUP_ENABLED` | Enable automatic removal of stale contacts (default: true) |
| `CONTACT_CLEANUP_DAYS` | Remove contacts not advertised for this many days (default: 7) |

When enabled, during each contact sync the receiver checks each contact's `last_advert` timestamp:
- Contacts with `last_advert` older than `CONTACT_CLEANUP_DAYS` are removed from the device
- Stale contacts are not published to MQTT (preventing collector database pollution)
- Contacts without a `last_advert` timestamp are preserved (no removal without data)

This cleanup runs automatically whenever the receiver syncs contacts (on startup and after each advertisement event).

Manual cleanup can be triggered at any time with:
```bash
# Dry run to see what would be deleted
meshcore-hub collector cleanup --retention-days 30 --dry-run

# Live cleanup
meshcore-hub collector cleanup --retention-days 30
```

Webhook payload structure:
```json
{
  "event_type": "advertisement",
  "public_key": "abc123...",
  "payload": { ... }
}
```

## Troubleshooting

### Common Issues

1. **MQTT Connection Failed**: Check broker is running and `MQTT_HOST`/`MQTT_PORT` are correct
2. **Database Migration Errors**: Ensure `DATA_HOME` is writable, run `meshcore-hub db upgrade`
3. **Import Errors**: Ensure package is installed with `pip install -e .`
4. **Type Errors**: Run `pre-commit run --all-files` to check type annotations and other issues
5. **NixOS greenlet errors**: On NixOS, the pre-built greenlet wheel may fail with `libstdc++.so.6` errors. Rebuild from source:
   ```bash
   pip install --no-binary greenlet greenlet
   ```

### Debugging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Or via environment
export LOG_LEVEL=DEBUG
```

## MeshCore Library Integration

The interface component uses the `meshcore` Python library to communicate with MeshCore devices. Key patterns:

### Device Commands

Commands are accessed via `mc.commands.*` on the MeshCore instance:

```python
# Set device time
await mc.commands.set_time(unix_timestamp)

# Send advertisement
await mc.commands.send_advert(flood=False)

# Send messages
await mc.commands.send_msg(destination, text)
await mc.commands.send_chan_msg(channel_idx, text)

# Request data
await mc.commands.send_statusreq(target)
await mc.commands.send_telemetry_req(target)
```

### Event Subscription

Events are received via the subscription system. The `Event` object has:
- `event.type` - The event type enum
- `event.payload` - Full event data (dict with all fields like `text`, `pubkey_prefix`, etc.)
- `event.attributes` - Subset of fields for filtering

**Important**: Use `event.payload` (not `event.attributes`) to get full message data.

### Auto Message Fetching

The library requires explicit message fetching. Call `start_auto_message_fetching()` to:
1. Subscribe to `MESSAGES_WAITING` events
2. Automatically call `get_msg()` to fetch pending messages
3. Immediately fetch any queued messages on startup

```python
await mc.start_auto_message_fetching()
```

### Receiver Initialization

On startup, the receiver performs these initialization steps:
1. Set device clock to current Unix timestamp
2. Optionally set the device name (if `MESHCORE_DEVICE_NAME` is configured)
3. Send a flood advertisement (broadcasts device name to the mesh)
4. Start automatic message fetching
5. Sync the device's contact database

### Contact Sync Behavior

The receiver syncs the device's contact database in two scenarios:

1. **Startup**: Initial sync when receiver starts
2. **Advertisement Events**: Automatic sync triggered whenever an advertisement is received from the mesh

Since advertisements are typically received every ~20 minutes, contact sync happens automatically without manual intervention. Each contact from the device is published individually to MQTT:
- Topic: `{prefix}/{device_public_key}/event/contact`
- Payload: `{public_key, adv_name, type}`

This ensures the collector's database stays current with all nodes discovered on the mesh network.

## References

- [meshcore Documentation](https://github.com/fdlamotte/meshcore)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Click Documentation](https://click.palletsprojects.com/)
