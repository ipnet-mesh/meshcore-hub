"""add reversible column to routes

Revision ID: a1b2c3d4e5f6
Revises: 8f2a3c4d5e6f
Create Date: 2026-07-13 01:00:00.000000+00:00

Adds a ``reversible`` boolean to the ``routes`` table (default true).
When true, the matching engine also checks the reverse-ordered path,
so A->B->C matches packets observed as C->B->A.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8f2a3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "routes",
        sa.Column(
            "reversible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("routes", "reversible")
