"""Tests for database engine configuration."""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from meshcore_hub.common.database import (
    DatabaseManager,
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


class TestPostgresSessionTimezone:
    """Verify Postgres connections are pinned to UTC at the engine level.

    func.date(<timestamptz>) truncates on the session timezone's day boundary.
    The collector writes UTC, so the session must be UTC for day buckets to
    match SQLite's UTC-text truncation.
    """

    def test_sync_engine_sets_timezone_utc_without_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Postgres engine without a schema still pins timezone=UTC."""
        monkeypatch.delenv("DATABASE_SCHEMA", raising=False)
        with patch("meshcore_hub.common.database.create_engine") as mock_create:
            create_database_engine("postgresql://u:p@h/db")
        _, kwargs = mock_create.call_args
        assert kwargs["connect_args"]["options"] == "-ctimezone=UTC"

    def test_sync_engine_timezone_utc_with_schema(self) -> None:
        """Postgres engine with a schema sets both search_path and timezone."""
        with patch("meshcore_hub.common.database.create_engine") as mock_create:
            create_database_engine("postgresql://u:p@h/db", schema="meshcorehub")
        _, kwargs = mock_create.call_args
        options = kwargs["connect_args"]["options"]
        assert "-csearch_path=meshcorehub" in options
        assert "-ctimezone=UTC" in options

    def test_sqlite_engine_has_no_timezone_options(self, tmp_path: Path) -> None:
        """SQLite engines must not set timezone options."""
        engine = create_database_engine(f"sqlite:///{tmp_path / 'x.db'}")
        try:
            assert "options" not in engine.url.query
        finally:
            engine.dispose()

    def test_async_engine_sets_server_settings_timezone_utc(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """asyncpg engine gets server_settings with timezone=UTC."""
        monkeypatch.delenv("DATABASE_SCHEMA", raising=False)
        manager = DatabaseManager.__new__(DatabaseManager)
        manager.database_url = "postgresql://u:p@h/db"
        manager._echo = False
        manager._schema = None
        manager._async_engine = None
        manager._async_session_factory = None

        with patch("meshcore_hub.common.database.create_async_engine") as mock_async:
            manager._ensure_async_engine()
        _, kwargs = mock_async.call_args
        assert kwargs["connect_args"]["server_settings"] == {"timezone": "UTC"}

    def test_async_engine_sets_server_settings_with_schema(self) -> None:
        """asyncpg engine with schema gets both search_path and timezone."""
        manager = DatabaseManager.__new__(DatabaseManager)
        manager.database_url = "postgresql://u:p@h/db"
        manager._echo = False
        manager._schema = "meshcorehub"
        manager._async_engine = None
        manager._async_session_factory = None

        with patch("meshcore_hub.common.database.create_async_engine") as mock_async:
            manager._ensure_async_engine()
        _, kwargs = mock_async.call_args
        server_settings = kwargs["connect_args"]["server_settings"]
        assert server_settings["timezone"] == "UTC"
        assert server_settings["search_path"] == "meshcorehub"
