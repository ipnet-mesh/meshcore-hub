"""Fixtures for collector component tests.

All fixtures run against the shared per-xdist-worker Postgres schema from
``tests/conftest.py`` (``db_url`` / ``db_schema``). The synchronous
``db_manager`` / ``db_session`` fixtures and the async ``async_db_session``
fixture use the production ``DatabaseManager`` paths (including
``async_session()``) and truncate between tests to coexist with the API
suite's session-scoped engine.
"""

import pytest

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models.base import Base


def _truncate_all(engine) -> None:
    """Delete rows from every table in child-first order (FK-safe)."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_manager(db_url, db_schema):
    """Database manager bound to the worker schema (production engine path)."""
    manager = DatabaseManager(db_url, schema=db_schema)
    manager.create_tables()
    yield manager
    _truncate_all(manager.engine)
    manager.dispose()


@pytest.fixture
def db_session(db_manager):
    """Create a database session for testing."""
    session = db_manager.get_session()
    yield session
    session.close()


@pytest.fixture
async def async_db_session(db_url, db_schema):
    """Async session from the production ``DatabaseManager.async_session()``."""
    manager = DatabaseManager(db_url, schema=db_schema)
    manager.create_tables()
    async with manager.async_session() as session:
        yield session
    _truncate_all(manager.engine)
    await manager.adispose()
