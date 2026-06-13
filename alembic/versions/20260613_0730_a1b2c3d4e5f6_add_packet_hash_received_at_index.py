"""add packet_hash_received_at composite index

Revision ID: a1b2c3d4e5f6
Revises: e9f0c4079540
Create Date: 2026-06-13 07:30:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e9f0c4079540"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.create_index(
            "ix_raw_packets_packet_hash_received_at",
            ["packet_hash", "received_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.drop_index("ix_raw_packets_packet_hash_received_at")
