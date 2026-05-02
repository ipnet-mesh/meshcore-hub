"""add roles to user_profiles, drop members

Revision ID: a7eaa878e58b
Revises: 72b6578ee3bf
Create Date: 2026-04-30 09:24:58.073046+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7eaa878e58b"
down_revision: Union[str, None] = "72b6578ee3bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("roles", sa.Text(), nullable=True))
    op.drop_table("members")


def downgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.VARCHAR(36), nullable=False),
        sa.Column("member_id", sa.VARCHAR(100), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("callsign", sa.VARCHAR(20), nullable=True),
        sa.Column("role", sa.VARCHAR(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact", sa.VARCHAR(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id"),
    )
    with op.batch_alter_table("user_profiles", schema=None) as batch_op:
        batch_op.drop_column("roles")
