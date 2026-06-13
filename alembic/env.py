"""Alembic environment configuration."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from meshcore_hub.common.models import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get database URL from environment or config."""
    from pathlib import Path

    # First try explicit DATABASE_URL environment variable
    url = os.environ.get("DATABASE_URL")
    if url:
        # Ensure directory exists for sqlite URLs
        if url.startswith("sqlite:///"):
            db_path = Path(url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        return url
    # Try DATA_HOME environment variable
    data_home = os.environ.get("DATA_HOME")
    if data_home:
        db_path = Path(data_home) / "collector" / "meshcore.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"
    # Fall back to alembic.ini
    return config.get_main_option("sqlalchemy.url", "sqlite:///./meshcore.db")


def get_schema(url: str) -> str | None:
    """Postgres schema to migrate into, or None for SQLite.

    Each Hub instance keeps its tables and alembic_version in its own schema so
    multiple instances (prod, stg, ...) can share one Postgres database with
    independent migration state.
    """
    if url.startswith(("postgresql", "postgres")):
        return os.environ.get("DATABASE_SCHEMA", "meshcorehub")
    return None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    schema = get_schema(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Batch mode is a SQLite-only workaround for its limited ALTER TABLE;
        # Postgres performs ALTERs directly.
        render_as_batch=url.startswith("sqlite"),
        version_table_schema=schema,
        include_schemas=schema is not None,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    url = get_database_url()
    configuration["sqlalchemy.url"] = url
    schema = get_schema(url)

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Ensure the instance's schema exists and scope this connection to it so
        # tables (and alembic_version) are created there. No-op for SQLite.
        if schema is not None:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Batch mode is a SQLite-only workaround for its limited ALTER TABLE.
            render_as_batch=url.startswith("sqlite"),
            version_table_schema=schema,
            include_schemas=schema is not None,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
