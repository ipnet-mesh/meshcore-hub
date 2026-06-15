"""Tests for database engine configuration."""

from pathlib import Path

import pytest
from sqlalchemy import text

from meshcore_hub.common.database import (
    _resolve_pg_schema,
    _to_async_url,
    create_database_engine,
)


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


class TestAsyncUrlMapping:
    """Map sync URLs to their async-driver equivalents for the async engine."""

    @pytest.mark.parametrize(
        "sync_url,expected",
        [
            ("sqlite:///x.db", "sqlite+aiosqlite:///x.db"),
            ("sqlite+aiosqlite:///x.db", "sqlite+aiosqlite:///x.db"),
            ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
            ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
            # config assembles +psycopg2; the async engine must still use asyncpg
            ("postgresql+psycopg2://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
            ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ],
    )
    def test_to_async_url(self, sync_url: str, expected: str) -> None:
        assert _to_async_url(sync_url) == expected


class TestSchemaResolution:
    """search_path schema resolution (explicit arg vs DATABASE_SCHEMA env)."""

    def test_sqlite_never_has_schema(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_SCHEMA", "ignored")
        assert _resolve_pg_schema("sqlite:///x.db", None) is None
        assert _resolve_pg_schema("sqlite:///x.db", "explicit") is None

    def test_explicit_schema_wins(self) -> None:
        assert _resolve_pg_schema("postgresql://u@h/db", "prod") == "prod"

    def test_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_SCHEMA", "stg")
        assert _resolve_pg_schema("postgresql://u@h/db", None) == "stg"

    def test_none_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_SCHEMA", raising=False)
        assert _resolve_pg_schema("postgresql://u@h/db", None) is None
