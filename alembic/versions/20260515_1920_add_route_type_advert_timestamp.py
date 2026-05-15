"""add route_type and advert_timestamp to advertisements

Revision ID: 20260515_1920
Revises: 20260503_1800
Create Date: 2026-05-15 19:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_1920"
down_revision: Union[str, None] = "20260503_1800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "advertisements",
        sa.Column("route_type", sa.String(20), nullable=True),
    )
    op.add_column(
        "advertisements",
        sa.Column("advert_timestamp", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("advertisements", "advert_timestamp")
    op.drop_column("advertisements", "route_type")
