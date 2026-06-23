"""add spam scoring columns to messages

Revision ID: 38abdf4651fc
Revises: d4e5f6a7b8c9
Create Date: 2026-06-22 22:43:00.000000+00:00

Adds the three nullable spam-scoring columns (path_prefix, sender_normalized,
spam_score) and their two composite ``(*, received_at)`` indexes used by the
windowed COUNT(*) scorer. Uses batch mode so it applies on SQLite (which lacks
full ALTER TABLE) as well as Postgres.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "38abdf4651fc"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("path_prefix", sa.String(length=48), nullable=True)
        )
        batch_op.add_column(
            sa.Column("sender_normalized", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(sa.Column("spam_score", sa.Float(), nullable=True))
        batch_op.create_index(
            "ix_messages_path_prefix_received_at",
            ["path_prefix", "received_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_messages_sender_normalized_received_at",
            ["sender_normalized", "received_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index("ix_messages_sender_normalized_received_at")
        batch_op.drop_index("ix_messages_path_prefix_received_at")
        batch_op.drop_column("spam_score")
        batch_op.drop_column("sender_normalized")
        batch_op.drop_column("path_prefix")
