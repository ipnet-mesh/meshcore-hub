"""Shared pytest fixtures for all tests."""

import os
import tempfile
from typing import Generator

import dotenv
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from meshcore_hub.common import config as config_module
from meshcore_hub.common.models import Base

# The CLI entrypoint (meshcore_hub.__main__) calls load_dotenv() at import time so
# deployments can drop a .env in place. Importing it during collection (e.g. from
# test_main.py) would otherwise leak a developer's repo-root .env straight into
# os.environ for the whole session — bypassing _ignore_dotenv, which only stops
# pydantic-settings from reading the file. conftest.py is imported before any test
# module is collected, so neutralising load_dotenv here binds first.
dotenv.load_dotenv = lambda *args, **kwargs: False


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


def _cli_envvars() -> set[str]:
    """Collect Click envvar names from CLI commands (best-effort).

    CLI options read env vars via ``envvar=`` independently of pydantic
    Settings, so ``_settings_classes`` alone misses them (e.g. ``API_WORKERS``).
    """
    import importlib

    import click

    envvars: set[str] = set()

    def _collect(cmd: click.BaseCommand) -> None:
        if isinstance(cmd, click.Group):
            for subcmd in cmd.commands.values():
                _collect(subcmd)
        if isinstance(cmd, click.Command):
            for param in cmd.params:
                if isinstance(param, click.Option) and param.envvar:
                    ev = param.envvar
                    if isinstance(ev, str):
                        envvars.add(ev)
                    else:
                        envvars.update(ev)

    for module_path in (
        "meshcore_hub.api.cli",
        "meshcore_hub.collector.cli",
        "meshcore_hub.web.cli",
    ):
        try:
            mod = importlib.import_module(module_path)
            for attr in vars(mod).values():
                if isinstance(attr, click.BaseCommand):
                    _collect(attr)
        except Exception:
            pass

    return envvars


@pytest.fixture(autouse=True)
def _ignore_dotenv(monkeypatch):
    """Stop pydantic-settings and Click from reading ``.env`` or leaked env vars.

    Three-pronged defence:

    1. Disable ``env_file`` on every settings subclass so pydantic-settings
       won't read the ``.env`` file itself.
    2. Delete any env vars matching a settings field name from ``os.environ``
       for the duration of the test.
    3. Delete any env vars matching a Click CLI ``envvar=`` name (e.g.
       ``API_WORKERS``) that aren't settings fields.

    This catches vars exported into the shell via direnv, Makefile, CI, etc.
    before pytest started. Tests must depend only on defaults and explicit
    env overrides (``monkeypatch.setenv``).
    """
    for cls in _settings_classes():
        cfg = dict(cls.model_config)
        cfg["env_file"] = None
        monkeypatch.setattr(cls, "model_config", cfg)

        for field_name in cls.model_fields:
            monkeypatch.delenv(field_name.upper(), raising=False)

    for ev in _cli_envvars():
        monkeypatch.delenv(ev, raising=False)


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


@pytest.fixture(scope="session")
def test_db_path():
    """Session-scoped temporary SQLite database file path.

    One file per pytest session; engines below build schema on it once.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture(scope="session")
def db_backend() -> str:
    """Active test database backend (``sqlite`` or ``postgres``).

    Controlled by ``TEST_DATABASE_BACKEND`` env var (default: ``sqlite``).
    When ``postgres``, ``TEST_POSTGRES_URL`` must also be set.
    """
    backend = os.environ.get("TEST_DATABASE_BACKEND", "sqlite").lower()
    if backend not in ("sqlite", "postgres"):
        raise ValueError(
            f"TEST_DATABASE_BACKEND must be 'sqlite' or 'postgres', got: {backend}"
        )
    return backend


@pytest.fixture(scope="session")
def db_url(db_backend: str, test_db_path: str, request) -> Generator[str, None, None]:
    """Database URL for the active backend.

    For Postgres, each pytest-xdist worker gets its own database (e.g.
    ``test_gw0``) to avoid truncation races between parallel workers. Shared by
    the API and collector suites so both exercise the same backend.
    """
    if db_backend == "postgres":
        env_url = os.environ.get("TEST_POSTGRES_URL")
        if not env_url:
            pytest.skip(
                "TEST_DATABASE_BACKEND=postgres but TEST_POSTGRES_URL is not set; "
                "e.g. TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost:55432/test"
            )
        assert env_url is not None

        worker_id = "master"
        if hasattr(request.config, "workerinput"):
            worker_id = request.config.workerinput["workerid"]

        base_url = make_url(env_url)
        worker_db = f"{base_url.database}_{worker_id}"
        worker_url = base_url.set(database=worker_db).render_as_string(
            hide_password=False
        )

        admin_url = base_url.set(database="postgres")
        admin_engine = create_engine(
            admin_url.render_as_string(hide_password=False),
            isolation_level="AUTOCOMMIT",
        )
        try:
            with admin_engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": worker_db},
                ).scalar()
                if not exists:
                    conn.execute(text(f'CREATE DATABASE "{worker_db}"'))
        finally:
            admin_engine.dispose()

        yield worker_url

        admin_engine = create_engine(
            admin_url.render_as_string(hide_password=False),
            isolation_level="AUTOCOMMIT",
        )
        try:
            with admin_engine.connect() as conn:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": worker_db},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{worker_db}"'))
        finally:
            admin_engine.dispose()
    else:
        yield f"sqlite:///{test_db_path}"
