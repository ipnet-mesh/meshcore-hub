"""add routes.created_by

Revision ID: da69304d8106
Revises: d307ee761a34
Create Date: 2026-07-24 10:00:00.000000+00:00

Adds a nullable ``created_by`` column to ``routes``, storing the OIDC
subject identifier (``user_id``) of the operator or admin who created
the route.  This enables ownership-based write permissions: operators
can only modify routes they created, while admins can modify any route
and take ownership on edit.

Existing routes get ``NULL`` (admin-only modification), preserving
backwards compatibility with no data backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "da69304d8106"
down_revision: Union[str, None] = "d307ee761a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("routes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("routes", schema=None) as batch_op:
        batch_op.drop_column("created_by")
