"""Fixtures for collector component tests."""

import pytest

from meshcore_hub.common.database import DatabaseManager


@pytest.fixture
def db_manager():
    """Create an in-memory database manager for testing."""
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
async def async_db_session(db_manager):
    """Create an async database session for testing."""
    # Create tables in async engine
    async with db_manager.async_engine.begin() as conn:
        await conn.run_sync(db_manager.engine.pool.echo)
        # Tables already created by db_manager fixture with sync engine
        # Async engine shares same database file, so tables exist

    async with db_manager.async_session() as session:
        yield session
