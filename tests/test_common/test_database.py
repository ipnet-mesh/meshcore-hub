"""Tests for database engine configuration."""

from pathlib import Path

from sqlalchemy import text

from meshcore_hub.common.database import create_database_engine


class TestSqlitePragmas:
    """Verify concurrency-related SQLite pragmas are applied on connect."""

    def test_wal_and_busy_timeout_enabled(self, tmp_path: Path) -> None:
        """File-based SQLite engines should run in WAL mode with a busy timeout."""
        db_path = tmp_path / "pragma.db"
        engine = create_database_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
                busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
                foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()

            assert str(journal_mode).lower() == "wal"
            assert busy_timeout is not None and int(busy_timeout) >= 5000
            assert foreign_keys is not None and int(foreign_keys) == 1
        finally:
            engine.dispose()

    def test_in_memory_engine_builds(self) -> None:
        """In-memory SQLite must still build (no overflow-pool kwargs)."""
        engine = create_database_engine("sqlite:///:memory:")
        try:
            with engine.connect() as conn:
                assert conn.execute(text("SELECT 1")).scalar() == 1
        finally:
            engine.dispose()
