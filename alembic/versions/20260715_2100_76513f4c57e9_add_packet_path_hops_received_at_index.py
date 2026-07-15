"""add standalone received_at index to packet_path_hops

Revision ID: 76513f4c57e9
Revises: c0d1e2f3a4b5
Create Date: 2026-07-15 21:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "76513f4c57e9"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_packet_path_hops_received_at",
        "packet_path_hops",
        ["received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_packet_path_hops_received_at",
        table_name="packet_path_hops",
    )
