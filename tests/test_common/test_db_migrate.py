"""Tests for the SQLite -> Postgres data migration helper.

The full round-trip is validated against a live Postgres; here we cover the
dialect-agnostic pieces (the Postgres-target guard, tz-aware column detection, and
the Core copy/stream/normalize logic exercised SQLite -> SQLite) so they run in CI.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select

from meshcore_hub.common import db_migrate
from meshcore_hub.common.db_migrate import (
    _copy_table,
    _is_superuser,
    _tz_aware_columns,
    migrate_sqlite_to_postgres,
)
from meshcore_hub.common.models import Base

# Import models so their tables register on Base.metadata.
import meshcore_hub.common.models.node  # noqa: F401
import meshcore_hub.common.models.raw_packet  # noqa: F401


def test_target_must_be_postgres() -> None:
    """The command refuses a non-Postgres target."""
    with pytest.raises(ValueError, match="PostgreSQL"):
        migrate_sqlite_to_postgres("sqlite:///a.db", "sqlite:///b.db")


def test_tz_aware_columns_detects_timestamptz() -> None:
    """Timezone-aware DateTime columns are identified for UTC normalization."""
    cols = _tz_aware_columns(Base.metadata.tables["raw_packets"])

    assert "received_at" in cols
    assert "created_at" in cols
    assert "packet_hash" not in cols  # not a datetime


def test_copy_table_roundtrips_rows_and_boolean() -> None:
    """_copy_table streams rows across engines, preserving the boolean value.

    (UTC normalization of naive datetimes is validated against Postgres, where
    timestamptz round-trips reliably; SQLite does not retain tzinfo.)
    """
    nodes = Base.metadata.tables["nodes"]
    src = create_engine("sqlite:///:memory:")
    dst = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(src)
    Base.metadata.create_all(dst)

    now = datetime(2026, 6, 13, 10, 0)
    with src.begin() as conn:
        conn.execute(
            nodes.insert(),
            [
                {
                    "id": f"n{i}",
                    "public_key": f"key{i}",
                    "is_observer": i == 0,
                    "first_seen": now,
                    "created_at": now,
                    "updated_at": now,
                }
                for i in range(3)
            ],
        )

    with dst.begin() as conn:
        copied = _copy_table(src, conn, nodes, batch_size=2)  # forces >1 batch

    assert copied == 3
    with dst.connect() as conn:
        assert conn.execute(select(func.count()).select_from(nodes)).scalar() == 3
        observers = conn.execute(
            select(func.count()).select_from(nodes).where(nodes.c.is_observer.is_(True))
        ).scalar()
    assert observers == 1  # boolean preserved across the copy

    src.dispose()
    dst.dispose()


def test_is_superuser_false_for_non_postgres() -> None:
    """session_replication_role is Postgres-only; SQLite is never a superuser target."""
    engine = create_engine("sqlite:///:memory:")
    try:
        assert _is_superuser(engine) is False
    finally:
        engine.dispose()


def _seed_nodes(engine, count: int) -> None:
    nodes = Base.metadata.tables["nodes"]
    now = datetime(2026, 6, 13, 10, 0)
    with engine.begin() as conn:
        conn.execute(
            nodes.insert(),
            [
                {
                    "id": f"n{i}",
                    "public_key": f"key{i}",
                    "is_observer": i == 0,
                    "first_seen": now,
                    "created_at": now,
                    "updated_at": now,
                }
                for i in range(count)
            ],
        )


@pytest.fixture
def _patch_engines(monkeypatch, tmp_path):
    """Route create_database_engine to SQLite files keyed by URL.

    Lets the Postgres-targeting migration flow run end-to-end SQLite -> SQLite in CI:
    a ``postgresql://`` target URL satisfies the guard while the real engine is a
    local SQLite file, so the schema/empty/truncate/copy logic is exercised without
    a live Postgres.
    """
    src_url = f"sqlite:///{tmp_path / 'src.db'}"
    target_url = "postgresql://fake/target"  # satisfies the Postgres guard
    src_engine = create_engine(src_url)
    tgt_engine = create_engine(f"sqlite:///{tmp_path / 'tgt.db'}")
    Base.metadata.create_all(src_engine)

    def fake_create_engine(url, echo=False, schema=None):
        if url == src_url:
            return src_engine
        if url == target_url:
            return tgt_engine
        raise AssertionError(f"unexpected url {url!r}")

    monkeypatch.setattr(db_migrate, "create_database_engine", fake_create_engine)
    return src_url, target_url, src_engine, tgt_engine


def _count_rows(engine) -> int:
    nodes = Base.metadata.tables["nodes"]
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(nodes)).scalar() or 0)


def test_migrate_dry_run_reports_counts_without_writing(_patch_engines) -> None:
    """Dry run reports source/target counts and leaves the target untouched."""
    src_url, target_url, src_engine, tgt_engine = _patch_engines
    Base.metadata.create_all(tgt_engine)
    _seed_nodes(src_engine, 3)

    result = migrate_sqlite_to_postgres(src_url, target_url, dry_run=True)

    assert result.dry_run is True
    nodes_result = next(t for t in result.tables if t.name == "nodes")
    assert nodes_result.source_rows == 3
    assert nodes_result.target_rows == 0
    assert _count_rows(tgt_engine) == 0  # nothing written


def test_migrate_copies_all_rows(_patch_engines) -> None:
    """A full run copies rows and reconciles source/target counts as OK."""
    src_url, target_url, src_engine, tgt_engine = _patch_engines
    Base.metadata.create_all(tgt_engine)
    _seed_nodes(src_engine, 5)

    result = migrate_sqlite_to_postgres(src_url, target_url, batch_size=2)

    assert result.ok is True
    assert _count_rows(tgt_engine) == 5
    nodes_result = next(t for t in result.tables if t.name == "nodes")
    assert nodes_result.source_rows == nodes_result.target_rows == 5


def test_migrate_refuses_non_empty_target(_patch_engines) -> None:
    """Without --truncate, a non-empty target is refused before any write."""
    src_url, target_url, src_engine, tgt_engine = _patch_engines
    Base.metadata.create_all(tgt_engine)
    _seed_nodes(src_engine, 2)
    _seed_nodes(tgt_engine, 1)

    with pytest.raises(RuntimeError, match="not empty"):
        migrate_sqlite_to_postgres(src_url, target_url)


def test_migrate_truncate_overwrites_target(_patch_engines) -> None:
    """--truncate clears existing target rows before loading from source."""
    src_url, target_url, src_engine, tgt_engine = _patch_engines
    Base.metadata.create_all(tgt_engine)
    _seed_nodes(src_engine, 2)
    _seed_nodes(tgt_engine, 4)

    result = migrate_sqlite_to_postgres(src_url, target_url, truncate=True)

    assert result.ok is True
    assert _count_rows(tgt_engine) == 2


def test_migrate_errors_when_target_schema_missing(_patch_engines) -> None:
    """A target without the schema (no create_all) fails with a clear message."""
    src_url, target_url, src_engine, tgt_engine = _patch_engines
    # Note: target schema intentionally not created.
    _seed_nodes(src_engine, 1)

    with pytest.raises(RuntimeError, match="Run 'meshcore-hub db upgrade'"):
        migrate_sqlite_to_postgres(src_url, target_url)
