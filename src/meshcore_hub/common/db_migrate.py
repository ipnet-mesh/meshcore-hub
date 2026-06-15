"""Copy all data from a source (SQLite) database into a target (Postgres) database.

This powers ``meshcore-hub db migrate-to-postgres``. It operates at the SQLAlchemy
Core level, iterating ``Base.metadata.sorted_tables`` and copying each table through
the ORM's typed columns. The round-trip ``SQLite value -> Python object -> Postgres
value`` is what makes the conversion correct (e.g. integer ``0/1`` -> ``bool``, JSON
``TEXT`` -> ``dict``, datetime string -> ``timestamptz``) without any per-model code.

The schema must already exist in the target (created by ``db upgrade``); this module
only moves data and never mutates the source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Engine

from meshcore_hub.common.database import create_database_engine
from meshcore_hub.common.models.base import Base

logger = logging.getLogger(__name__)


@dataclass
class TableResult:
    """Per-table outcome of a migration run."""

    name: str
    source_rows: int
    target_rows: int

    @property
    def ok(self) -> bool:
        return self.source_rows == self.target_rows


@dataclass
class MigrationResult:
    """Aggregate outcome of a migration run."""

    tables: list[TableResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.tables)


def _tz_aware_columns(table: sa.Table) -> list[str]:
    """Names of timezone-aware DateTime columns on a table.

    SQLite does not persist tzinfo, so these values read back naive and must be
    stamped UTC before insert into Postgres ``timestamptz`` (the app always writes
    UTC via utc_now()).
    """
    return [
        col.name
        for col in table.columns
        if isinstance(col.type, sa.DateTime)
        and bool(getattr(col.type, "timezone", False))
    ]


def _count(engine: Engine, table: sa.Table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar() or 0)


def _is_superuser(engine: Engine) -> bool:
    """Whether the target role can SET session_replication_role (superuser-only)."""
    if engine.dialect.name != "postgresql":
        return False
    try:
        with engine.connect() as conn:
            value = conn.execute(
                text("SELECT current_setting('is_superuser')")
            ).scalar()
        return str(value).lower() == "on"
    except Exception:  # pragma: no cover - defensive
        return False


def _copy_table(
    source_engine: Engine,
    tgt_conn: sa.engine.Connection,
    table: sa.Table,
    batch_size: int,
) -> int:
    """Stream rows from source and bulk-insert into the target connection."""
    tz_cols = _tz_aware_columns(table)
    copied = 0
    with source_engine.connect().execution_options(stream_results=True) as src:
        result = src.execute(select(table))
        for partition in result.partitions(batch_size):
            rows = []
            for row in partition:
                data = dict(row._mapping)
                for col in tz_cols:
                    value = data.get(col)
                    if value is not None and value.tzinfo is None:
                        data[col] = value.replace(tzinfo=timezone.utc)
                rows.append(data)
            if rows:
                tgt_conn.execute(insert(table), rows)
                copied += len(rows)
    return copied


def migrate_sqlite_to_postgres(
    source_url: str,
    target_url: str,
    *,
    target_schema: Optional[str] = None,
    batch_size: int = 2000,
    truncate: bool = False,
    dry_run: bool = False,
    disable_replication_role: bool = False,
) -> MigrationResult:
    """Copy every table from ``source_url`` into ``target_url``.

    Args:
        source_url: SQLAlchemy URL of the source (SQLite) database.
        target_url: SQLAlchemy URL of the target (Postgres) database.
        target_schema: Postgres schema to load into (search_path). Defaults to the
            DATABASE_SCHEMA env var via the engine.
        batch_size: Rows per insert batch.
        truncate: Delete existing rows from target tables before loading.
        dry_run: Report source/target counts without writing.
        disable_replication_role: Skip the session_replication_role trick even if the
            target role is a superuser (e.g. to mirror managed-Postgres behaviour).

    Returns:
        MigrationResult with per-table source/target row counts.
    """
    if not target_url.startswith(("postgresql", "postgres")):
        raise ValueError("Target must be a PostgreSQL database URL")

    source_engine = create_database_engine(source_url)
    target_engine = create_database_engine(target_url, schema=target_schema)
    tables = list(Base.metadata.sorted_tables)  # parent-first; excludes alembic_version

    try:
        # Pre-flight: schema present + (unless truncating) target empty.
        for table in tables:
            try:
                existing = _count(target_engine, table)
            except Exception as exc:  # table missing -> schema not initialised
                raise RuntimeError(
                    f"Target table {table.name!r} not found. Run 'meshcore-hub db "
                    f"upgrade' against the target first."
                ) from exc
            if existing and not (truncate or dry_run):
                raise RuntimeError(
                    f"Target table {table.name!r} is not empty ({existing} rows). "
                    f"Refusing to load; pass --truncate to overwrite."
                )

        if dry_run:
            result = MigrationResult(dry_run=True)
            for table in tables:
                result.tables.append(
                    TableResult(
                        table.name,
                        _count(source_engine, table),
                        _count(target_engine, table),
                    )
                )
            return result

        use_replica = (
            target_engine.dialect.name == "postgresql"
            and not disable_replication_role
            and _is_superuser(target_engine)
        )
        if not use_replica:
            logger.info(
                "Not disabling FK triggers (session_replication_role); relying on "
                "parent-first table order."
            )

        # Single transaction: all-or-nothing. A failure leaves the target empty.
        with target_engine.begin() as tgt:
            if use_replica:
                tgt.execute(text("SET session_replication_role = replica"))
            if truncate:
                for table in reversed(tables):  # children first
                    tgt.execute(table.delete())
            for table in tables:
                copied = _copy_table(source_engine, tgt, table, batch_size)
                logger.info("Copied %s rows into %s", copied, table.name)
            if use_replica:
                tgt.execute(text("SET session_replication_role = DEFAULT"))

        # Reconcile.
        result = MigrationResult()
        for table in tables:
            result.tables.append(
                TableResult(
                    table.name,
                    _count(source_engine, table),
                    _count(target_engine, table),
                )
            )
        return result
    finally:
        source_engine.dispose()
        target_engine.dispose()
