"""add routes.max_path_length

Revision ID: d307ee761a34
Revises: 5e3b712ccf10
Create Date: 2026-07-20 12:00:00.000000+00:00

Adds a single nullable ``max_path_length`` column to ``routes``. The
new knob caps the total number of hops in a candidate packet's full
path; receptions whose path exceeds it are dropped from matching
consideration entirely (before the subsequence matcher runs), so
over-long paths never count toward ``packet_count_threshold``.  Complements
the existing ``max_hop_span`` (which only constrains the gap between
the first and last *matched* configured node).

``null`` (the default) means unlimited and preserves the previous
behaviour for every existing route, so this migration is additive and
backwards-compatible with no data backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d307ee761a34"
down_revision: Union[str, None] = "5e3b712ccf10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "routes",
        sa.Column("max_path_length", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("routes", "max_path_length")
