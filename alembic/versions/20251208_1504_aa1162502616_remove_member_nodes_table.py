"""Remove member_nodes table

Revision ID: aa1162502616
Revises: 03b9b2451bd9
Create Date: 2025-12-08 15:04:37.260923+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "aa1162502616"
down_revision: Union[str, None] = "03b9b2451bd9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the member_nodes table
    # Nodes are now associated with members via a 'member_id' tag on the node
    op.drop_table("member_nodes")


def downgrade() -> None:
    # Recreate the member_nodes table if needed for rollback
    op.create_table(
        "member_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("public_key", sa.String(length=64), nullable=False),
        sa.Column("node_role", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_member_nodes_member_id_members"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_nodes")),
    )
    op.create_index(
        op.f("ix_member_nodes_member_id"), "member_nodes", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_member_nodes_public_key"), "member_nodes", ["public_key"], unique=False
    )
    op.create_index(
        "ix_member_nodes_member_public_key",
        "member_nodes",
        ["member_id", "public_key"],
        unique=False,
    )
