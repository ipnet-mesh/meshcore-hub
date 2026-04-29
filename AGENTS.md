# AGENTS.md - AI Coding Assistant Guidelines

This document provides context and guidelines for AI coding assistants working on the MeshCore Hub project.

## Agent Rules

### Critical Rules (MUST follow)

* **Always use parenthesized exception tuples** — `except (ValueError, TypeError):` not `except ValueError, TypeError:`. The comma form is Python 2 syntax and will fail at import time in Python 3. This is the most common error that passes visual review but breaks the application.
* You MUST use Python (version in `.python-version` file)
* You MUST activate a Python virtual environment in the `.venv` directory or create one if it does not exist:
  - `ls ./.venv` to check if it exists
  - `python -m venv .venv` to create it
* You MUST always activate the virtual environment before running any commands
  - `source .venv/bin/activate`
* You MUST install all project dependencies using `pip install -e ".[dev]"` command`
* You MUST install `pre-commit` for quality checks
* **Never `git push` without explicit confirmation** — staging and committing after discrete changes is fine, but pushing to remote requires the user to explicitly request it
* You MUST keep project documentation in sync with behavior/config/schema changes made in code (at minimum update relevant sections in `README.md`, `SCHEMAS.md`, `docs/upgrading.md`, `docs/auth.md`, `docs/letsmesh.md` when applicable)
* Before commiting:
  - Run **targeted tests** for the components you changed, not the full suite:
    - `pytest tests/test_web/` for web-only changes (templates, static JS, web routes)
    - `pytest tests/test_api/` for API changes
    - `pytest tests/test_collector/` for collector changes
    - `pytest tests/test_common/` for common models/schemas/config changes
    - Only run the full `pytest` if changes span multiple components
  - Run `pre-commit run --all-files` to perform all quality checks

## Project Overview

MeshCore Hub is a Python 3.14+ monorepo for managing and orchestrating MeshCore mesh networks. Data ingestion is done via [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture), which captures MeshCore mesh traffic and publishes events to MQTT. MeshCore Hub then collects, stores, and presents this data. It consists of four main components:

- **meshcore_collector**: Collects MeshCore events from MQTT and stores them in a database
- **meshcore_api**: REST API for querying data
- **meshcore_web**: Web dashboard for visualizing network status
- **meshcore_common**: Shared utilities, models, and configurations

## Key Documentation

- [SCHEMAS.md](SCHEMAS.md) - MeshCore event JSON schemas and database mappings
- [docs/upgrading.md](docs/upgrading.md) - Upgrade guide for breaking changes
- [docs/auth.md](docs/auth.md) - OIDC authentication setup and configuration
- [docs/letsmesh.md](docs/letsmesh.md) - LetsMesh packet decoding details
- [docs/seeding.md](docs/seeding.md) - Seed data format and import guide
- [docs/i18n.md](docs/i18n.md) - Translation reference guide

## Technology Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.14+ |
| Package Management | pip with pyproject.toml |
| CLI Framework | Click |
| Configuration | Pydantic Settings |
| Database ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| REST API | FastAPI |
| MQTT Client | paho-mqtt |
| MQTT Broker | [meshcore-mqtt-broker](https://github.com/michaelhart/meshcore-mqtt-broker) (WebSocket + JWT auth) |
| Templates | Jinja2 (server), lit-html (SPA) |
| Frontend | ES Modules SPA with client-side routing |
| CSS Framework | Tailwind CSS v4 (CLI) + DaisyUI v5 |
| Frontend Build | Node.js 22 LTS (`npm run build`) |
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
│   │   ├── i18n.py           # Translation loading
│   │   ├── health.py         # Health check utilities
│   │   ├── hash_utils.py     # Hash utility functions
│   │   ├── models/           # SQLAlchemy models
│   │   │   ├── node.py       # Node model
│   │   │   ├── member.py     # Network member model
│   │   │   ├── user_profile.py     # User profile model (OIDC users)
│   │   │   ├── user_profile_node.py # User-node adoption join table
│   │   │   └── ...
│   │   └── schemas/          # Pydantic schemas
│   │       ├── members.py    # Member API schemas
│   │       ├── user_profiles.py  # User profile API schemas
│   │       └── ...
│   ├── collector/
│   │   ├── cli.py            # Collector CLI with seed commands
│   │   ├── subscriber.py     # MQTT subscriber
│   │   ├── cleanup.py        # Data retention/cleanup service
│   │   ├── letsmesh_decoder.py     # Native Python packet decoder
│   │   ├── letsmesh_normalizer.py  # LetsMesh upload topic normalizer
│   │   ├── tag_import.py     # Tag import from YAML
│   │   ├── member_import.py  # Member import from YAML
│   │   ├── handlers/         # Event handlers
│   │   └── webhook.py        # Webhook dispatcher
│   ├── api/
│   │   ├── cli.py
│   │   ├── app.py            # FastAPI app
│   │   ├── auth.py           # Authentication
│   │   ├── dependencies.py
│   │   ├── metrics.py        # Prometheus metrics endpoint
│   │   └── routes/           # API routes
│   │       ├── members.py    # Member CRUD endpoints
│   │   ├── user_profiles.py  # User profile endpoints (GET/PUT profile)
│   │   ├── adoptions.py      # Node adoption endpoints (POST adopt, DELETE release)
│   │   └── ...
│   └── web/
│       ├── cli.py
│       ├── app.py            # FastAPI app
│       ├── pages.py          # Custom markdown page loader
│       ├── middleware.py     # Cache-Control middleware
│       ├── templates/        # Jinja2 templates (spa.html shell)
│       └── static/
│           ├── css/
│           │   ├── app.css        # Custom styles
│           │   ├── input.css      # Tailwind v4 input (source)
│           │   └── tailwind.css   # Built Tailwind+DaisyUI CSS (generated)
│           ├── vendor/            # Vendored JS/CSS libraries (built by npm run build)
│           │   ├── lit-html/      # lit-html ES module
│           │   ├── leaflet/       # Leaflet map library
│           │   ├── chart.js/      # Chart.js library
│           │   └── qrcodejs/      # QR code library
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
│   ├── test_collector/
│   ├── test_api/
│   └── test_web/
├── alembic/
│   ├── env.py
│   └── versions/
├── etc/
│   ├── docker/                # Docker configuration examples
│   │   └── meshcore-mqtt-broker/
│   ├── prometheus/            # Prometheus configuration
│   │   ├── prometheus.yml    # Scrape and alerting config
│   │   └── alerts.yml        # Alert rules
│   ├── alertmanager/          # Alertmanager configuration
│   │   └── alertmanager.yml  # Routing and receiver config
│   └── systemd/               # Systemd service templates
│       ├── meshcore-hub-update@.service  # Auto-update service
│       └── meshcore-hub-update@.timer    # Auto-update timer
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
├── Dockerfile                # Docker build configuration (multi-stage: Node.js frontend + Python)
├── package.json              # Frontend build dependencies (Tailwind, DaisyUI, lit-html, etc.)
├── build.js                  # Frontend build script (Tailwind CLI + vendor copy)
├── docker-compose.yml        # Docker Compose base config
├── docker-compose.dev.yml    # Development overrides (port mappings)
├── docker-compose.prod.yml   # Production overrides (proxy network)
├── docker-compose.traefik.yml # Optional Traefik labels
├── docs/                    # Documentation
│   ├── images/              # Screenshots and images
│   ├── hosting/             # Reverse proxy hosting guides
│   ├── content.md           # Custom content setup guide
│   ├── i18n.md              # Translation reference guide
│   ├── letsmesh.md          # LetsMesh packet decoding details
│   ├── seeding.md           # Seed data format and import guide
│   ├── upgrading.md         # Upgrade guide for breaking changes
│   └── webhooks.md          # Webhook configuration reference
└── SCHEMAS.md
```

## MQTT Topic Structure

The MQTT broker ([meshcore-mqtt-broker](https://github.com/michaelhart/meshcore-mqtt-broker)) uses WebSocket transport with MeshCore public key authentication for publishers and subscriber accounts for consumers.

### Upload Topics (published by packet capture)
```
<prefix>/<IATA>/<public_key>/<feed_type>
```

Examples:
- `meshcore/STN/abc123.../packets`
- `meshcore/STN/abc123.../status`
- `meshcore/STN/abc123.../internal`

The `<IATA>` segment is a 3-letter airport code (e.g., `STN`, `SEA`) or `test`, validated by the MQTT broker. The hub ignores this segment during parsing.

### Subscriber Subscriptions
The collector subscribes to:
- `{prefix}/+/+/packets`
- `{prefix}/+/+/status`
- `{prefix}/+/+/internal`

## Database Conventions

- Use UUIDs for primary keys (stored as VARCHAR(36))
- Use `public_key` (64-char hex) as the canonical node identifier
- All timestamps stored as UTC
- JSON columns for flexible data (path_hashes, parsed_data, etc.)
- Foreign keys reference nodes by UUID, not public_key

## Standard Node Tags

Node tags are flexible key-value pairs that allow custom metadata to be attached to nodes. While tags are completely optional and freeform, the following standard tag keys are recommended for consistent use across the web dashboard:

| Tag Key | Description | Usage |
|---------|-------------|-------|
| `name` | Node display name | Used as the primary display name throughout the UI (overrides the advertised name) |
| `description` | Short description | Displayed as supplementary text under the node name |
| `member_id` | Member identifier reference | Links the node to a network member (matches `member_id` in Members table) |
| `lat` | GPS latitude override | Overrides node-reported latitude for map display |
| `lon` | GPS longitude override | Overrides node-reported longitude for map display |
| `elevation` | GPS elevation override | Overrides node-reported elevation |
| `role` | Node role/purpose | Used for website presentation and filtering (e.g., "gateway", "repeater", "sensor") |

**Important Notes:**
- All tags are optional - nodes can function without any tags
- Tag keys are case-sensitive
- The `member_id` tag should reference a valid `member_id` from the Members table

## Testing Guidelines

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_collector_handles_advertisement():
    """Test that collector handler processes advertisement events."""
    handler = AdvertisementHandler(db_session=AsyncMock())

    await handler.handle(event_data)

    handler.db_session.add.assert_called_once()
    node = handler.db_session.add.call_args[0][0]
    assert node.public_key == event_data["public_key"]
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
- [docs/i18n.md](docs/i18n.md) - Comprehensive translation reference guide for translators

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

2. **Update `docs/i18n.md`** with:
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
- **Document context:** Always update `docs/i18n.md` so translators understand usage

**Example - adding a new entity and patterns:**

```javascript
// 1. Add entity to en.json
"entities": {
  "sensor": "Sensor"
}

// 2. Use with existing common patterns
t('common.add_entity', { entity: t('entities.sensor') })  // "Add Sensor"
t('common.no_entity_found', { entity: t('entities.sensors').toLowerCase() })  // "No sensors found"

// 3. Update docs/i18n.md with context
// 4. Add test to test_i18n.py
```

**Translation loading:**

The i18n system (`src/meshcore_hub/common/i18n.py`) loads translations on startup:
- Defaults to English (`en`)
- Falls back to English for missing keys
- Returns the key itself if translation not found

For full translation guidelines, see [docs/i18n.md](docs/i18n.md).

### Adding a New Database Model

1. Create model in `common/models/`
2. Export in `common/models/__init__.py`
3. Create Alembic migration: `meshcore-hub db revision --autogenerate -m "description"`
4. Review and adjust migration file
5. Test migration: `meshcore-hub db upgrade`

### Running the Development Environment

```bash
# Build frontend assets (requires Node.js 22+ LTS)
npm install
npm run build

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
```

## Environment Variables

Key variables:
- `DATA_HOME` - Base directory for runtime data (default: `./data`)
- `SEED_HOME` - Directory containing seed data files (default: `./seed`)
- `CONTENT_HOME` - Directory containing custom content (pages, media) (default: `./content`)
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_PREFIX` - MQTT broker connection
- `MQTT_USERNAME`, `MQTT_PASSWORD` - MQTT subscriber authentication credentials
- `MQTT_TRANSPORT` - MQTT transport protocol (default: `websockets`)
- `MQTT_WS_PATH` - WebSocket path (default: `/`)
- `MQTT_TLS` - Enable TLS/SSL for MQTT (default: `false`, set `true` for `wss://`)
- `COLLECTOR_CHANNEL_KEYS` - Additional decoder channel keys for decrypting GroupText packets
- `COLLECTOR_INCLUDE_TEST_CHANNEL` - Include built-in 'test' channel messages (default: `false`)
- `API_READ_KEY`, `API_ADMIN_KEY` - API authentication keys
- `OIDC_ENABLED` - Enable OIDC authentication (default: `false`)
- `OIDC_CLIENT_ID` - OIDC client ID (required if OIDC_ENABLED=true)
- `OIDC_CLIENT_SECRET` - OIDC client secret (required if OIDC_ENABLED=true)
- `OIDC_DISCOVERY_URL` - OIDC discovery URL (required if OIDC_ENABLED=true)
- `OIDC_REDIRECT_URI` - Explicit callback URL (overrides auto-derivation)
- `OIDC_POST_LOGOUT_REDIRECT_URI` - Post-logout redirect URI (must match IdP sign-out URIs, falls back to `OIDC_REDIRECT_URI` base)
- `OIDC_SCOPES` - OAuth scopes (default: `openid email profile`). The `openid` scope is required for ID tokens and userinfo. Quotes are stripped automatically. When using LogTo as the OIDC provider, include `roles` in `OIDC_SCOPES` (e.g., `"openid email profile roles"`) to enable role-based admin access.
- `OIDC_ROLES_CLAIM` - ID token claim for roles (default: `roles`)
- `OIDC_ROLE_ADMIN` - IdP role name for admin access (default: `admin`)
- `OIDC_ROLE_OPERATOR` - IdP role name for operator access (default: `operator`)
- `OIDC_ROLE_MEMBER` - IdP role name for member access (default: `member`)
- `OIDC_SESSION_SECRET` - Secret for signing session cookies (required if OIDC_ENABLED=true)
- `OIDC_SESSION_MAX_AGE` - Session lifetime in seconds (default: `86400`)
- `OIDC_COOKIE_SECURE` - HTTPS-only cookies (default: `false`)
- `WEB_THEME` - Default theme for the web dashboard (default: `dark`, options: `dark`, `light`). Users can override via the theme toggle in the navbar, which persists their preference in browser localStorage.
- `WEB_AUTO_REFRESH_SECONDS` - Auto-refresh interval in seconds for list pages (default: `30`, `0` to disable)
- `WEB_DEBUG` - Enable debug mode in the web dashboard (default: `false`)
- `TZ` - Timezone for web dashboard date/time display (default: `UTC`, e.g., `America/New_York`, `Europe/London`)
- `FEATURE_DASHBOARD`, `FEATURE_NODES`, `FEATURE_ADVERTISEMENTS`, `FEATURE_MESSAGES`, `FEATURE_MAP`, `FEATURE_MEMBERS`, `FEATURE_PAGES` - Feature flags to enable/disable specific web dashboard pages (default: all `true`). Dependencies: Dashboard auto-disables when all of Nodes/Advertisements/Messages are disabled. Map auto-disables when Nodes is disabled.
- `NETWORK_DOMAIN` - Network domain name (default: none)
- `NETWORK_NAME` - Network display name (default: `MeshCore Network`)
- `METRICS_ENABLED` - Enable Prometheus metrics endpoint at /metrics (default: `true`)
- `METRICS_CACHE_TTL` - Seconds to cache metrics output (default: `60`)
- `LOG_LEVEL` - Logging verbosity

Infrastructure passthrough variables (consumed by Docker Compose or MQTT broker, not Hub Python):
- `COMPOSE_PROJECT_NAME` - Docker Compose project prefix for containers and volumes (default: `hub`)
- `MQTT_TOKEN_AUDIENCE` - JWT audience claim for packet capture auth tokens (default: `mqtt.localhost`)

The database defaults to `sqlite:///{DATA_HOME}/collector/meshcore.db` and does not typically need to be configured.

### Directory Structure

**Seed Data (`SEED_HOME`)** - Contains initial data files for database seeding:
```
${SEED_HOME}/
├── node_tags.yaml    # Node tags (keyed by public_key)
└── members.yaml      # Network members list
```

**Custom Content (`CONTENT_HOME`)** - Custom pages and media for the web dashboard. See [docs/content.md](docs/content.md) for directory structure, frontmatter fields, and setup guide.

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
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile seed up
```

**Note:** When OIDC is enabled (`OIDC_ENABLED=true`), the admin UI requires authenticated sessions with the `admin` role. Tags should be managed through the web interface by authenticated admin users.

### Webhook Configuration

The collector supports forwarding events to external HTTP endpoints with configurable URLs, secrets, retries, and timeouts. See [docs/webhooks.md](docs/webhooks.md) for the full configuration reference, URL routing logic, and payload format.

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
| `NODE_CLEANUP_DAYS` | Remove nodes not seen for this many days (default: 30) |

When enabled, the collector automatically removes nodes where:
- `last_seen` is older than the configured number of days
- Nodes with `last_seen=NULL` (never seen on network) are **NOT** removed
- Nodes created via tag import that have never been seen on the mesh are preserved

**Note:** Both event data and node cleanup run on the same schedule (DATA_RETENTION_INTERVAL_HOURS).

Manual cleanup can be triggered at any time with:
```bash
# Dry run to see what would be deleted
meshcore-hub collector cleanup --retention-days 30 --dry-run

# Live cleanup
meshcore-hub collector cleanup --retention-days 30
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

## References

- [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Click Documentation](https://click.palletsprojects.com/)
