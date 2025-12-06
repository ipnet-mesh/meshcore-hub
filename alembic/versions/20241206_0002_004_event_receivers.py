"""Add event_receivers junction table for multi-receiver tracking

Revision ID: 004
Revises: 003
Create Date: 2024-12-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_receivers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("event_hash", sa.String(32), nullable=False),
        sa.Column(
            "receiver_node_id",
            sa.String(36),
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snr", sa.Float, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_hash", "receiver_node_id", name="uq_event_receivers_hash_node"
        ),
    )
    op.create_index(
        "ix_event_receivers_event_hash",
        "event_receivers",
        ["event_hash"],
    )
    op.create_index(
        "ix_event_receivers_receiver_node_id",
        "event_receivers",
        ["receiver_node_id"],
    )
    op.create_index(
        "ix_event_receivers_type_hash",
        "event_receivers",
        ["event_type", "event_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_receivers_type_hash", table_name="event_receivers")
    op.drop_index("ix_event_receivers_receiver_node_id", table_name="event_receivers")
    op.drop_index("ix_event_receivers_event_hash", table_name="event_receivers")
    op.drop_table("event_receivers")
