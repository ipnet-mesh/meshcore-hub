"""Database connection and session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from meshcore_hub.common.models.base import Base


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

    # SQLite-specific configuration
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    # Enable foreign keys for SQLite
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore
            cursor = dbapi_connection.cursor()
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
    """

    def __init__(self, database_url: str, echo: bool = False):
        """Initialize the database manager.

        Args:
            database_url: SQLAlchemy database URL
            echo: Enable SQL query logging
        """
        self.database_url = database_url
        self.engine = create_database_engine(database_url, echo=echo)
        self.session_factory = create_session_factory(self.engine)

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

    def dispose(self) -> None:
        """Dispose of the database engine and connection pool."""
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
        raise RuntimeError(
            "Database not initialized. Call init_database() first."
        )
    return _db_manager


def get_session() -> Session:
    """Get a database session from the global manager.

    Returns:
        Session instance
    """
    return get_database().get_session()
