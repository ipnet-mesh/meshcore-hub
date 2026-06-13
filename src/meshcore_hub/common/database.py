"""Database connection and session management."""

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from meshcore_hub.common.models.base import Base


def _to_async_url(database_url: str) -> str:
    """Map a sync database URL to its async-driver equivalent.

    Leaves an already driver-qualified URL (``dialect+driver://``) untouched so an
    explicit driver choice is respected.
    """
    scheme = database_url.split("://", 1)[0]
    if "+" in scheme:
        return database_url
    if scheme == "sqlite":
        return database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if scheme in ("postgresql", "postgres"):
        return database_url.replace(f"{scheme}://", "postgresql+asyncpg://", 1)
    return database_url


def create_database_engine(
    database_url: str,
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy database engine.

    Args:
        database_url: SQLAlchemy database URL
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy Engine instance
    """
    connect_args = {}
    engine_kwargs: dict[str, Any] = {}

    # SQLite-specific configuration
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    # Size the pool above the default Starlette threadpool (~40 threads) so
    # concurrent request handlers don't block waiting for a connection. Applies
    # to file-based SQLite and networked backends (e.g. a future Postgres).
    # In-memory SQLite uses a non-overflow pool, so skip these args there.
    is_memory_sqlite = database_url in ("sqlite://", "sqlite:///:memory:")
    if not is_memory_sqlite:
        engine_kwargs["pool_size"] = 20
        engine_kwargs["max_overflow"] = 30

    engine = create_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
        **engine_kwargs,
    )

    # Apply SQLite pragmas on every new connection
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore
            cursor = dbapi_connection.cursor()
            # WAL lets readers run concurrently with a single writer (the
            # collector), and busy_timeout waits instead of immediately raising
            # "database is locked" under contention. synchronous=NORMAL is safe
            # under WAL and faster.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


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

    def __init__(self, database_url: str, echo: bool = False):
        """Initialize the database manager.

        Args:
            database_url: SQLAlchemy database URL
            echo: Enable SQL query logging
        """
        self.database_url = database_url
        self._echo = echo

        # Ensure parent directory exists for SQLite databases
        if database_url.startswith("sqlite:///"):
            from pathlib import Path

            # Extract path from sqlite:///path/to/db.sqlite
            db_path = Path(database_url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_database_engine(database_url, echo=echo)
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
        self._async_engine = create_async_engine(async_url, echo=self._echo)

        # Apply the same SQLite pragmas as the sync engine (see
        # create_database_engine) for the async engine's connections.
        if self.database_url.startswith("sqlite"):

            @event.listens_for(self._async_engine.sync_engine, "connect")
            def set_sqlite_pragma_async(
                dbapi_connection: object, connection_record: object
            ) -> None:
                cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

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
        """Dispose of the database engine and connection pool."""
        self.engine.dispose()
        if self._async_engine is not None:
            self._async_engine.sync_engine.dispose()


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
