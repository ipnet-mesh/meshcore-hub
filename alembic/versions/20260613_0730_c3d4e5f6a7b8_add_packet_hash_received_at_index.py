"""add packet_hash_received_at composite index

Revision ID: c3d4e5f6a7b8
Revises: e8eb47c49062
Create Date: 2026-06-13 07:30:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "e8eb47c49062"
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
