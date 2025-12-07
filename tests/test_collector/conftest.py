"""Fixtures for collector component tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models.base import Base


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
async def async_db_session():
    """Create an async database session for testing.

    Uses a separate in-memory database with tables created inline.
    """
    # Create async engine with in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

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
