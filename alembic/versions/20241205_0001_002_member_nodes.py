"""Add member_nodes association table

Revision ID: 002
Revises: 001
Create Date: 2024-12-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create member_nodes table
    op.create_table(
        "member_nodes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(36), nullable=False),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("node_role", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_member_nodes_member_id", "member_nodes", ["member_id"])
    op.create_index("ix_member_nodes_public_key", "member_nodes", ["public_key"])
    op.create_index(
        "ix_member_nodes_member_public_key",
        "member_nodes",
        ["member_id", "public_key"],
    )

    # Migrate existing public_key data from members to member_nodes
    # Get all members with a public_key
    connection = op.get_bind()
    members_with_keys = connection.execute(
        sa.text("SELECT id, public_key FROM members WHERE public_key IS NOT NULL")
    ).fetchall()

    # Insert into member_nodes
    for member_id, public_key in members_with_keys:
        # Generate a UUID for the new row
        import uuid

        node_id = str(uuid.uuid4())
        connection.execute(
            sa.text(
                """
                INSERT INTO member_nodes (id, member_id, public_key, created_at, updated_at)
                VALUES (:id, :member_id, :public_key, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {"id": node_id, "member_id": member_id, "public_key": public_key},
        )

    # Drop the public_key column from members
    op.drop_index("ix_members_public_key", table_name="members")
    op.drop_column("members", "public_key")


def downgrade() -> None:
    # Add public_key column back to members
    op.add_column(
        "members",
        sa.Column("public_key", sa.String(64), nullable=True),
    )
    op.create_index("ix_members_public_key", "members", ["public_key"])

    # Migrate data back - take the first node for each member
    connection = op.get_bind()
    member_nodes = connection.execute(
        sa.text(
            """
            SELECT DISTINCT member_id, public_key
            FROM member_nodes
            WHERE (member_id, created_at) IN (
                SELECT member_id, MIN(created_at)
                FROM member_nodes
                GROUP BY member_id
            )
            """
        )
    ).fetchall()

    for member_id, public_key in member_nodes:
        connection.execute(
            sa.text(
                "UPDATE members SET public_key = :public_key WHERE id = :member_id"
            ),
            {"public_key": public_key, "member_id": member_id},
        )

    # Drop member_nodes table
    op.drop_table("member_nodes")
