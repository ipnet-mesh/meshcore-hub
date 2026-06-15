"""widen messages.signature to 32 chars

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-14 09:15:00.000000+00:00

The column was declared String(8) but actually stores 16-char hex signatures
(and can hold the up-to-32-char packet_hash fallback). SQLite never enforced the
length, so the undersized definition went unnoticed until a Postgres migration
rejected the data (varchar(8)). Widen it to String(32).

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column(
            "signature",
            existing_type=sa.String(length=8),
            type_=sa.String(length=32),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column(
            "signature",
            existing_type=sa.String(length=32),
            type_=sa.String(length=8),
            existing_nullable=True,
        )
