"""Make event_hash columns unique for race condition prevention

Revision ID: 005
Revises: 004
Create Date: 2024-12-06

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing non-unique indexes and create unique constraints
    # Note: SQLite handles NULL values as unique (each NULL is distinct)

    # Messages: drop index, create unique constraint
    op.drop_index("ix_messages_event_hash", table_name="messages")
    op.create_unique_constraint("uq_messages_event_hash", "messages", ["event_hash"])

    # Advertisements: drop index, create unique constraint
    op.drop_index("ix_advertisements_event_hash", table_name="advertisements")
    op.create_unique_constraint(
        "uq_advertisements_event_hash", "advertisements", ["event_hash"]
    )

    # Trace paths: drop index, create unique constraint
    op.drop_index("ix_trace_paths_event_hash", table_name="trace_paths")
    op.create_unique_constraint(
        "uq_trace_paths_event_hash", "trace_paths", ["event_hash"]
    )

    # Telemetry: drop index, create unique constraint
    op.drop_index("ix_telemetry_event_hash", table_name="telemetry")
    op.create_unique_constraint("uq_telemetry_event_hash", "telemetry", ["event_hash"])


def downgrade() -> None:
    # Restore non-unique indexes

    # Telemetry
    op.drop_constraint("uq_telemetry_event_hash", "telemetry", type_="unique")
    op.create_index("ix_telemetry_event_hash", "telemetry", ["event_hash"])

    # Trace paths
    op.drop_constraint("uq_trace_paths_event_hash", "trace_paths", type_="unique")
    op.create_index("ix_trace_paths_event_hash", "trace_paths", ["event_hash"])

    # Advertisements
    op.drop_constraint("uq_advertisements_event_hash", "advertisements", type_="unique")
    op.create_index("ix_advertisements_event_hash", "advertisements", ["event_hash"])

    # Messages
    op.drop_constraint("uq_messages_event_hash", "messages", type_="unique")
    op.create_index("ix_messages_event_hash", "messages", ["event_hash"])
