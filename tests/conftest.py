"""Shared pytest fixtures for all tests."""

import os

import dotenv
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from meshcore_hub.common import config as config_module
from meshcore_hub.common.database import create_database_engine
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


def _truncate_all(engine) -> None:
    """Delete rows from every table in child-first order (FK-safe)."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


# Default points at the throwaway stack from `make test-db-up`. Override with
# TEST_POSTGRES_URL to use any other Postgres instance.
DEFAULT_TEST_POSTGRES_URL = (
    "postgresql+psycopg2://meshcorehub:meshcorehub-test"
    "@localhost:55432/meshcorehub_test"
)


@pytest.fixture(scope="session")
def db_url(worker_id: str) -> str:
    """PostgreSQL URL for this pytest session (Postgres is the only backend).

    Missing or unreachable database is a hard exit — Postgres is mandatory,
    not skippable — with an actionable message pointing at ``make test-db-up``.
    """
    url = os.environ.get("TEST_POSTGRES_URL") or DEFAULT_TEST_POSTGRES_URL
    probe = create_engine(url, poolclass=NullPool)
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.exit(
            f"PostgreSQL test database unreachable at {url!r}: {exc}\n"
            "Backend tests require PostgreSQL. Start the throwaway stack "
            "with: make test-db-up\n"
            "(or point TEST_POSTGRES_URL at your own instance)",
            returncode=4,
        )
    finally:
        probe.dispose()
    return url


@pytest.fixture(scope="session")
def db_schema(worker_id: str, db_url: str):
    """Per-xdist-worker schema isolating parallel test runs.

    ``hub_test_master`` / ``hub_test_gw0`` / ... The test role owns the
    database (no superuser or CREATEDB needed), so the schema is created with
    a plain connection — no admin connection to a maintenance database.
    Engines built through the production ``create_database_engine`` factory
    scope themselves to it via ``search_path``. Torn down with DROP SCHEMA
    CASCADE.
    """
    schema = f"hub_test_{worker_id}"
    admin = create_engine(db_url, poolclass=NullPool)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    yield schema
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def db_engine(db_url: str, db_schema: str):
    """Worker-schema Postgres engine built by the production factory.

    Tables are created idempotently; rows are truncated after each test so
    sibling tests start clean without paying schema-build costs.
    """
    engine = create_database_engine(db_url, schema=db_schema)
    Base.metadata.create_all(engine)
    yield engine
    _truncate_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()
