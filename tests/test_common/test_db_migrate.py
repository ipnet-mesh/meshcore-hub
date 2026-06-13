"""Tests for the SQLite -> Postgres data migration helper.

The full round-trip is validated against a live Postgres; here we cover the
dialect-agnostic pieces (the Postgres-target guard, tz-aware column detection, and
the Core copy/stream/normalize logic exercised SQLite -> SQLite) so they run in CI.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select

from meshcore_hub.common.db_migrate import (
    _copy_table,
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
