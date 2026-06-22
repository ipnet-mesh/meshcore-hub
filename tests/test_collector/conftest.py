"""Fixtures for collector component tests.

The ``db_backend`` / ``db_url`` switch lives in the shared ``tests/conftest.py``.
The synchronous ``db_manager`` / ``db_session`` fixtures honour it so the spam
scorer, the re-scoring sweep, and the message handler are exercised on both
SQLite (default) and Postgres (``TEST_DATABASE_BACKEND=postgres``). On Postgres
they share the per-xdist-worker database with the API suite, so tables are
created idempotently and *truncated* (never dropped) at teardown to coexist with
the API's session-scoped engine.
"""

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models.base import Base


def _truncate_all(engine) -> None:
    """Delete rows from every table in child-first order (FK-safe)."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_manager(db_backend, db_url):
    """Create a database manager for testing, honouring the active backend.

    Default (SQLite) uses an isolated in-memory database per test, exactly as
    before. Postgres reuses the shared worker database with idempotent schema +
    truncate-on-teardown.
    """
    if db_backend == "postgres":
        manager = DatabaseManager(db_url)
        manager.create_tables()
        yield manager
        _truncate_all(manager.engine)
        manager.dispose()
    else:
        manager = DatabaseManager("sqlite:///:memory:")
        manager.create_tables()
        yield manager
        manager.dispose()


@pytest.fixture
def db_session(db_manager):
    """Create a database session for testing."""
    session = db_manager.get_session()
    yield session
    session.close()


@pytest.fixture
async def async_db_session():
    """Create an async database session for testing.

    Uses a separate in-memory database with tables created inline.
    """
    # Create async engine with in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma_async(
        dbapi_connection: object, connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Provide session
    async with async_session_maker() as session:
        yield session

    # Cleanup
    await engine.dispose()
