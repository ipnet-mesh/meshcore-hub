"""Make event_hash columns unique for race condition prevention

Revision ID: 005
Revises: 004
Create Date: 2024-12-06

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def _has_unique_on_column(table_name: str, column_name: str) -> bool:
    """Check if a unique constraint or unique index exists on a column."""
    bind = op.get_bind()
    inspector = inspect(bind)
    # Check unique constraints
    uniques = inspector.get_unique_constraints(table_name)
    for uq in uniques:
        if column_name in uq.get("column_names", []):
            return True
    # Also check indexes (SQLite may create unique index instead of constraint)
    indexes = inspector.get_indexes(table_name)
    for idx in indexes:
        if idx.get("unique") and column_name in idx.get("column_names", []):
            return True
    return False


def upgrade() -> None:
    # Convert non-unique indexes to unique indexes for race condition prevention
    # Note: SQLite handles NULL values as unique (each NULL is distinct)
    # SQLite doesn't support ALTER TABLE ADD CONSTRAINT, so we use unique indexes

    # Messages
    if _index_exists("messages", "ix_messages_event_hash"):
        op.drop_index("ix_messages_event_hash", table_name="messages")
    if not _has_unique_on_column("messages", "event_hash"):
        op.create_index(
            "ix_messages_event_hash_unique",
            "messages",
            ["event_hash"],
            unique=True,
        )

    # Advertisements
    if _index_exists("advertisements", "ix_advertisements_event_hash"):
        op.drop_index("ix_advertisements_event_hash", table_name="advertisements")
    if not _has_unique_on_column("advertisements", "event_hash"):
        op.create_index(
            "ix_advertisements_event_hash_unique",
            "advertisements",
            ["event_hash"],
            unique=True,
        )

    # Trace paths
    if _index_exists("trace_paths", "ix_trace_paths_event_hash"):
        op.drop_index("ix_trace_paths_event_hash", table_name="trace_paths")
    if not _has_unique_on_column("trace_paths", "event_hash"):
        op.create_index(
            "ix_trace_paths_event_hash_unique",
            "trace_paths",
            ["event_hash"],
            unique=True,
        )

    # Telemetry
    if _index_exists("telemetry", "ix_telemetry_event_hash"):
        op.drop_index("ix_telemetry_event_hash", table_name="telemetry")
    if not _has_unique_on_column("telemetry", "event_hash"):
        op.create_index(
            "ix_telemetry_event_hash_unique",
            "telemetry",
            ["event_hash"],
            unique=True,
        )


def downgrade() -> None:
    # Restore non-unique indexes

    # Telemetry
    if _index_exists("telemetry", "ix_telemetry_event_hash_unique"):
        op.drop_index("ix_telemetry_event_hash_unique", table_name="telemetry")
    if not _index_exists("telemetry", "ix_telemetry_event_hash"):
        op.create_index("ix_telemetry_event_hash", "telemetry", ["event_hash"])

    # Trace paths
    if _index_exists("trace_paths", "ix_trace_paths_event_hash_unique"):
        op.drop_index("ix_trace_paths_event_hash_unique", table_name="trace_paths")
    if not _index_exists("trace_paths", "ix_trace_paths_event_hash"):
        op.create_index("ix_trace_paths_event_hash", "trace_paths", ["event_hash"])

    # Advertisements
    if _index_exists("advertisements", "ix_advertisements_event_hash_unique"):
        op.drop_index(
            "ix_advertisements_event_hash_unique", table_name="advertisements"
        )
    if not _index_exists("advertisements", "ix_advertisements_event_hash"):
        op.create_index(
            "ix_advertisements_event_hash", "advertisements", ["event_hash"]
        )

    # Messages
    if _index_exists("messages", "ix_messages_event_hash_unique"):
        op.drop_index("ix_messages_event_hash_unique", table_name="messages")
    if not _index_exists("messages", "ix_messages_event_hash"):
        op.create_index("ix_messages_event_hash", "messages", ["event_hash"])
