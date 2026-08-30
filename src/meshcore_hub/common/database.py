"""Database connection and session management."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from meshcore_hub.common.models.base import Base

logger = logging.getLogger(__name__)


def _resolve_pg_schema(schema: str | None) -> str | None:
    """Resolve the Postgres schema to scope a connection to (search_path).

    An explicit ``schema`` wins; otherwise it falls back to the
    ``DATABASE_SCHEMA`` env var. The CLI's ``load_dotenv()`` and Docker both
    populate that var, so runtime entrypoints don't need to thread the schema
    through every constructor.
    """
    return schema or os.environ.get("DATABASE_SCHEMA")


def _to_async_url(database_url: str) -> str:
    """Map a sync database URL to its asyncpg equivalent.

    The async engine always uses asyncpg, even when the sync URL names a sync
    driver (e.g. ``postgresql+psycopg2://``, which is what the config
    assembler produces) — otherwise async sessions would try to use the sync
    driver.
    """
    scheme = database_url.split("://", 1)[0]
    return database_url.replace(f"{scheme}://", "postgresql+asyncpg://", 1)


def create_database_engine(
    database_url: str,
    echo: bool = False,
    schema: str | None = None,
) -> Engine:
    """Create a SQLAlchemy database engine.

    Args:
        database_url: SQLAlchemy database URL
        echo: Enable SQL query logging
        schema: Postgres schema to scope connections to via search_path.
            Defaults to the DATABASE_SCHEMA env var when not given.

    Returns:
        SQLAlchemy Engine instance
    """
    connect_args: dict[str, Any] = {}

    # Scope connections to the configured schema via search_path and pin the
    # session timezone to UTC so func.date(<timestamptz>) truncates on the UTC
    # day boundary — the collector writes UTC, so day buckets must line up on
    # it. This keeps the models schema-agnostic (no hardcoded schema=) so the
    # same code serves single-instance Postgres and multiple schema-isolated
    # instances on one cluster.
    resolved_schema = _resolve_pg_schema(schema)
    options_parts: list[str] = []
    if resolved_schema:
        options_parts.append(f"-csearch_path={resolved_schema}")
    options_parts.append("-ctimezone=UTC")
    connect_args["options"] = " ".join(options_parts)

    # Size the pool above the default Starlette threadpool (~40 threads) so
    # concurrent request handlers don't block waiting for a connection.
    engine_kwargs: dict[str, Any] = {
        "pool_size": 20,
        "max_overflow": 30,
    }

    return create_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
        **engine_kwargs,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory for the given engine.

    Args:
        engine: SQLAlchemy Engine instance

    Returns:
        Session factory
    """
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def create_tables(engine: Engine) -> None:
    """Create all database tables.

    Args:
        engine: SQLAlchemy Engine instance
    """
    Base.metadata.create_all(bind=engine)


def drop_tables(engine: Engine) -> None:
    """Drop all database tables.

    Args:
        engine: SQLAlchemy Engine instance
    """
    Base.metadata.drop_all(bind=engine)


class DatabaseManager:
    """Database connection manager.

    Manages database engine and session creation for a component.
    The async engine is created lazily on first async session access
    to avoid leaking connections when only sync operations are needed.
    """

    def __init__(
        self, database_url: str, echo: bool = False, schema: str | None = None
    ):
        """Initialize the database manager.

        Args:
            database_url: SQLAlchemy database URL
            echo: Enable SQL query logging
            schema: Postgres schema to scope connections to (search_path). Defaults to
                the DATABASE_SCHEMA env var when not given.
        """
        self.database_url = database_url
        self._echo = echo
        self._schema = _resolve_pg_schema(schema)

        self.engine = create_database_engine(database_url, echo=echo, schema=schema)
        self.session_factory = create_session_factory(self.engine)

        # Lazy-initialized async engine (created on first async_session call)
        self._async_engine: AsyncEngine | None = None
        self._async_session_factory: Any = None

    def _ensure_async_engine(self) -> None:
        """Create the async engine and session factory on first use."""
        if self._async_engine is not None:
            return

        from sqlalchemy.ext.asyncio import async_sessionmaker

        async_url = _to_async_url(self.database_url)
        # asyncpg sets search_path and timezone via server_settings (not the
        # libpq -c options string the sync psycopg2 engine uses). self._schema
        # is already resolved (explicit arg or DATABASE_SCHEMA env). Timezone
        # is pinned to UTC so day boundaries line up with the collector's
        # UTC writes.
        server_settings: dict[str, str] = {"timezone": "UTC"}
        if self._schema:
            server_settings["search_path"] = self._schema
        async_connect_args: dict[str, Any] = {"server_settings": server_settings}

        # Mirror the sync engine's pool configuration (see
        # create_database_engine): without pool_pre_ping a Postgres restart
        # leaves stale asyncpg connections in the pool that error on next use.
        async_engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "pool_size": 20,
            "max_overflow": 30,
        }

        self._async_engine = create_async_engine(
            async_url,
            echo=self._echo,
            connect_args=async_connect_args,
            **async_engine_kwargs,
        )

        self._async_session_factory = async_sessionmaker(
            self._async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def create_tables(self) -> None:
        """Create all database tables."""
        create_tables(self.engine)

    def drop_tables(self) -> None:
        """Drop all database tables."""
        drop_tables(self.engine)

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            New Session instance
        """
        return self.session_factory()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations.

        Yields:
            Session instance

        Example:
            with db.session_scope() as session:
                session.add(node)
                session.commit()
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide an async session context manager.

        Yields:
            AsyncSession instance

        Example:
            async with db.async_session() as session:
                result = await session.execute(select(Node))
                await session.commit()
        """
        self._ensure_async_engine()
        assert self._async_session_factory is not None
        async with self._async_session_factory() as session:
            yield session

    def dispose(self) -> None:
        """Dispose of the database engines and connection pools.

        The async engine's pooled connections can only be closed from a
        running event loop. When this method is called outside any loop
        (e.g. a CLI that used ``async_session`` via ``asyncio.run``), the
        async engine is disposed on a temporary loop. Inside a running
        loop, use :meth:`adispose` instead — the async engine is then left
        for that call and a warning is logged.
        """
        if self._async_engine is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._async_engine.dispose())
                self._async_engine = None
                self._async_session_factory = None
            else:
                logger.warning(
                    "dispose() called inside a running event loop; async "
                    "engine not closed — use adispose()"
                )
        self.engine.dispose()

    async def adispose(self) -> None:
        """Dispose both engines from an async context (e.g. app lifespan)."""
        if self._async_engine is not None:
            await self._async_engine.dispose()
            self._async_engine = None
            self._async_session_factory = None
        self.engine.dispose()


# Global database manager instance (initialized at runtime)
_db_manager: DatabaseManager | None = None


def init_database(database_url: str, echo: bool = False) -> DatabaseManager:
    """Initialize the global database manager.

    Args:
        database_url: SQLAlchemy database URL
        echo: Enable SQL query logging

    Returns:
        DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url, echo=echo)
    return _db_manager


def get_database() -> DatabaseManager:
    """Get the global database manager.

    Returns:
        DatabaseManager instance

    Raises:
        RuntimeError: If database not initialized
    """
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_manager


def get_session() -> Session:
    """Get a database session from the global manager.

    Returns:
        Session instance
    """
    return get_database().get_session()
