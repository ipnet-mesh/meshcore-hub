"""Shared pytest fixtures for all tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meshcore_hub.common import config as config_module
from meshcore_hub.common.models import Base


def _settings_classes():
    """CommonSettings and every subclass (recursively)."""
    seen: set[type] = set()
    stack = [config_module.CommonSettings]
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
    return seen


@pytest.fixture(autouse=True)
def _ignore_dotenv(monkeypatch):
    """Stop pydantic-settings from reading the repo-root ``.env`` during tests.

    Settings classes set ``env_file=".env"`` so deployments can drop a file in
    place. Tests must depend only on defaults and explicit env overrides
    (``monkeypatch.setenv``), never on whatever a developer happens to have in
    their local ``.env`` — otherwise e.g. ``DATABASE_BACKEND=postgres`` there
    leaks into unrelated tests. Each settings subclass carries its own merged
    ``model_config`` dict, so patch every one.
    """
    for cls in _settings_classes():
        cfg = dict(cls.model_config)
        cfg["env_file"] = None
        monkeypatch.setattr(cls, "model_config", cfg)


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()
