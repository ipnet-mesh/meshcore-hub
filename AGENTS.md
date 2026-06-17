# AGENTS.md - AI Coding Assistant Guidelines

## Critical Rules (MUST follow)

- **Always use parenthesized exception tuples** — `except (ValueError, TypeError):` not `except ValueError, TypeError:`. The comma form is Python 2 syntax and fails at import time in Python 3. The most common error that passes visual review but breaks the app.
- **To run tests and get results, use:**
  ```bash
  pytest --no-cov 2>&1 | grep -iE "passed|failed" | tail -3
  ```
  `--no-cov` skips coverage for speed; the pipe surfaces only the pass/fail summary.
- Use Python (version in `.python-version`); activate a venv in `.venv` before running pytest, pre-commit, or alembic locally.
- **All other operations run inside the compose stack** — never invoke `meshcore-hub` or `npm` directly on the host; build/run/exec via `docker compose` (see Development).
- **Never `git push` without explicit confirmation** — staging and committing discrete changes is fine.
- Before committing: run targeted `pytest --no-cov tests/test_<component>/` then `pre-commit run --all-files`.

## Setup

```bash
ls ./.venv || python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

This venv is only for local testing, linting, and migration authoring. Frontend assets and runtime deps build into the Docker image — there is no local `npm` step.

## Development

```bash
# Build / start / stop the stack (core = collector + api + web + migrate)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core up -d
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core down

# Run a command inside a running service
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core exec <service> <command>

# Shorthands (Makefile, mqtt+core profiles): make build | make up | make down | make logs
```

## Tests & Quality

Coverage is **opt-in**; add `--cov=meshcore_hub` (or `make test-cov`) when you want it. The dev loop defaults to no coverage and parallel across CPU cores.

```bash
# Canonical: run tests in parallel, no coverage, surface the pass/fail summary
pytest -nauto --no-cov 2>&1 | grep -iE "passed|failed" | tail -3

# Makefile shorthands
make test        # pytest -nauto --no-cov (parallel dev loop)
make test-cov    # full run with coverage report
make test-unit   # parallel, fast unit suites only (skips e2e)

# Targeted by component (run only what you changed)
pytest --no-cov tests/test_web/        # templates, static JS, web routes
pytest --no-cov tests/test_api/        # API changes
pytest --no-cov tests/test_collector/  # collector changes
pytest --no-cov tests/test_common/     # common models/schemas/config

# Full suite only if changes span multiple components
pytest --no-cov

# Quality checks
pre-commit run --all-files
```

## Database & Ops

The default backend is **SQLite** (zero-config, file at `${DATA_HOME}/collector/meshcore.db`). **PostgreSQL** is also supported via `DATABASE_BACKEND=postgres` — see `docs/database.md` for the full backend reference, production provisioning, and schema-per-instance setup. Migrations are backend-agnostic; the commands below work for both.

```bash
# --- LOCAL (venv): sync the volume DB to ./meshcore.db, then author a migration
# Volume name is ${COMPOSE_PROJECT_NAME:-hub}_data (default: hub_data)
# (SQLite only — for Postgres, point the migration env at the cluster directly)
docker run -it --rm -v hub_data:/data -v "$PWD":/pwd ubuntu cp /data/collector/meshcore.db /pwd/meshcore.db
meshcore-hub db revision --autogenerate -m "description"

# --- CONTAINER: apply migrations (the DB lives in the data volume)
# Migrations auto-apply on `up` via the migrate service. Manual one-off:
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core run --rm migrate db upgrade

# --- CONTAINER: seed node tags from SEED_HOME (NOT automatic)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile seed run --rm seed

# --- CONTAINER: data retention / node cleanup (exec into the running collector)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core exec collector meshcore-hub collector cleanup --retention-days 30 --dry-run
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core exec collector meshcore-hub collector cleanup --retention-days 30
```

## Conventions

```python
# Imports: stdlib, third-party, local
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy import select

from meshcore_hub.common.config import Settings
from meshcore_hub.common.models import Node
```

```python
# Pydantic model
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

```python
# SQLAlchemy model
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

    tags: Mapped[list["NodeTag"]] = relationship(back_populates="node", cascade="all, delete-orphan")


class UserProfile(Base, UUIDMixin, TimestampMixin):
    """UserProfile model for authenticated OIDC users."""
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    callsign: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    roles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

```python
# FastAPI route
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
    pass
```

```python
# Click CLI command
import click

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

```python
# Async lifespan
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    await setup_database()
    await connect_mqtt()

    yield

    await disconnect_mqtt()
    await close_database()
```

```python
# Error handling
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)

raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Node with public_key '{public_key}' not found"
)

try:
    result = await risky_operation()
except SomeException as e:
    logger.exception("Failed to perform operation: %s", e)
    raise
```

## Test patterns

```python
# Unit test
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

```python
# Integration test
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

## Where to find the rest

- `README.md` — project overview, deployment, MQTT topics, node tags, data retention, troubleshooting
- `SCHEMAS.md` — API/data schemas
- `.env.example` — all environment variables with defaults and comments
- `docs/auth.md` — OIDC authentication and roles
- `docs/content.md` — custom content (`CONTENT_HOME`)
- `docs/i18n.md` — translation reference
- `docs/letsmesh.md` — packet decoding and MQTT feed details
- `docs/seeding.md` — seed data
- `docs/upgrading.md` — upgrade notes
- `docs/webhooks.md` — webhook configuration and payloads
