"""rename channel visibility public to community

Revision ID: 20260604_1200
Revises: 82dff87d6576
Create Date: 2026-06-04 12:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260604_1200"
down_revision: Union[str, None] = "82dff87d6576"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE channels SET visibility = 'community' WHERE visibility = 'public'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE channels SET visibility = 'public' WHERE visibility = 'community'"
    )
