"""add is_observer flag to nodes

Revision ID: 20260610_1200
Revises: 20260604_1200
Create Date: 2026-06-10 12:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260610_1200"
down_revision: Union[str, None] = "20260604_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Backfill the flag from every event source, matching the union the API used to
# evaluate at query time. Portable across SQLite and PostgreSQL.
_BACKFILL_SQL = """
UPDATE nodes SET is_observer = true WHERE id IN (
    SELECT observer_node_id FROM advertisements WHERE observer_node_id IS NOT NULL
    UNION SELECT observer_node_id FROM messages WHERE observer_node_id IS NOT NULL
    UNION SELECT observer_node_id FROM telemetry WHERE observer_node_id IS NOT NULL
    UNION SELECT observer_node_id FROM trace_paths WHERE observer_node_id IS NOT NULL
    UNION SELECT observer_node_id FROM event_observers
)
"""


def upgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_observer",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.create_index("ix_nodes_is_observer", ["is_observer"])

    op.execute(_BACKFILL_SQL)


def downgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.drop_index("ix_nodes_is_observer")
        batch_op.drop_column("is_observer")
