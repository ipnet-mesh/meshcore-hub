"""Rename degraded_threshold to clear_threshold.

Revision ID: 71f6e01e4bf6
Revises: 76513f4c57e9
Create Date: 2026-07-15 23:00:00
"""

from alembic import op

revision = "71f6e01e4bf6"
down_revision = "76513f4c57e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "routes",
        "degraded_threshold",
        new_column_name="clear_threshold",
    )
    op.alter_column(
        "route_results",
        "effective_degraded",
        new_column_name="effective_clear",
    )


def downgrade() -> None:
    op.alter_column(
        "route_results",
        "effective_clear",
        new_column_name="effective_degraded",
    )
    op.alter_column(
        "routes",
        "clear_threshold",
        new_column_name="degraded_threshold",
    )
