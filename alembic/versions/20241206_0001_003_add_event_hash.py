"""Add event_hash column to event tables for deduplication

Revision ID: 003
Revises: 002
Create Date: 2024-12-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add event_hash column to messages table
    op.add_column(
        "messages",
        sa.Column("event_hash", sa.String(32), nullable=True),
    )
    op.create_index("ix_messages_event_hash", "messages", ["event_hash"])

    # Add event_hash column to advertisements table
    op.add_column(
        "advertisements",
        sa.Column("event_hash", sa.String(32), nullable=True),
    )
    op.create_index("ix_advertisements_event_hash", "advertisements", ["event_hash"])

    # Add event_hash column to trace_paths table
    op.add_column(
        "trace_paths",
        sa.Column("event_hash", sa.String(32), nullable=True),
    )
    op.create_index("ix_trace_paths_event_hash", "trace_paths", ["event_hash"])

    # Add event_hash column to telemetry table
    op.add_column(
        "telemetry",
        sa.Column("event_hash", sa.String(32), nullable=True),
    )
    op.create_index("ix_telemetry_event_hash", "telemetry", ["event_hash"])


def downgrade() -> None:
    # Remove event_hash from telemetry
    op.drop_index("ix_telemetry_event_hash", table_name="telemetry")
    op.drop_column("telemetry", "event_hash")

    # Remove event_hash from trace_paths
    op.drop_index("ix_trace_paths_event_hash", table_name="trace_paths")
    op.drop_column("trace_paths", "event_hash")

    # Remove event_hash from advertisements
    op.drop_index("ix_advertisements_event_hash", table_name="advertisements")
    op.drop_column("advertisements", "event_hash")

    # Remove event_hash from messages
    op.drop_index("ix_messages_event_hash", table_name="messages")
    op.drop_column("messages", "event_hash")
