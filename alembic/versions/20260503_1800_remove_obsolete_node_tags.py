"""remove obsolete role and member_id node tags

Revision ID: 20260503_1800
Revises: d7a9bbe85a9e
Create Date: 2026-05-03 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260503_1800"
down_revision: Union[str, None] = "d7a9bbe85a9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM node_tags WHERE key = 'role' AND value = 'infra'")
    op.execute("DELETE FROM node_tags WHERE key = 'member_id'")


def downgrade() -> None:
    pass
