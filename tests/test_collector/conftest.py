"""Fixtures for collector component tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Base


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
