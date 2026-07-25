"""route evaluator performance remediation

Revision ID: a59611449e2a
Revises: da69304d8106
Create Date: 2026-07-25 12:00:00.000000+00:00

Two performance-focused changes backing the route-evaluator remediation:

1. **Clamp ``routes.window_hours`` to the new maximum (12).** The schema
   validation now caps the evaluation window at 12h (default 6h) so the
   candidate set fed to ``fetch_candidate_paths`` stays bounded. Any
   pre-existing route configured above 12h is clamped down to 12h to
   remain valid under the new constraint. The clamp is one-way: original
   values are not recoverable on downgrade. Clamped routes are printed to
   stdout during upgrade as an audit trail.

2. **Covering index on ``packet_path_hops``.** Recreate
   ``ix_packet_path_hops_raw_packet_id_position`` with INCLUDE columns
   (``node_hash``, ``packet_hash``, ``event_hash``, ``received_at``,
   ``observer_node_id``) on PostgreSQL so the route evaluator's outer
   Merge Join scan becomes an index-only scan instead of heap-fetching
   every row. SQLite does not support INCLUDE; its existing plain index
   is left untouched (SQLite is dev/test-scale only).

Note: the index rebuild runs CONCURRENTLY on PostgreSQL (no write
blocking) and therefore uses an autocommit block.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a59611449e2a"
down_revision: Union[str, None] = "da69304d8106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


_WINDOW_HOURS_MAX = 12
_INDEX_NAME = "ix_packet_path_hops_raw_packet_id_position"
_TABLE = "packet_path_hops"
_INCLUDE_COLS = [
    "node_hash",
    "packet_hash",
    "event_hash",
    "received_at",
    "observer_node_id",
]


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Audit + clamp routes.window_hours to the new max ---
    clamped = bind.execute(
        sa.text(
            "SELECT id, window_hours FROM routes "
            "WHERE window_hours > :max ORDER BY window_hours DESC"
        ).bindparams(max=_WINDOW_HOURS_MAX)
    ).fetchall()
    if clamped:
        print(
            f"  [route perf] clamping {len(clamped)} route(s) "
            f"with window_hours > {_WINDOW_HOURS_MAX} -> {_WINDOW_HOURS_MAX}:"
        )
        for row in clamped:
            print(f"    {row.id}: {row.window_hours}h -> {_WINDOW_HOURS_MAX}h")
    op.execute(
        sa.text(
            "UPDATE routes SET window_hours = :max WHERE window_hours > :max"
        ).bindparams(max=_WINDOW_HOURS_MAX)
    )

    # --- 2. Covering index on packet_path_hops (PostgreSQL only) ---
    # SQLite (and other backends) do not support INCLUDE; their existing
    # plain index is retained unchanged.
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(_INDEX_NAME, table_name=_TABLE)
            op.create_index(
                _INDEX_NAME,
                _TABLE,
                ["raw_packet_id", "position"],
                postgresql_include=_INCLUDE_COLS,
                postgresql_concurrently=True,
            )


def downgrade() -> None:
    # Restore the plain (non-covering) index on PostgreSQL. The
    # window_hours clamp is one-way: original values are not recoverable.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(_INDEX_NAME, table_name=_TABLE)
            op.create_index(
                _INDEX_NAME,
                _TABLE,
                ["raw_packet_id", "position"],
                postgresql_concurrently=True,
            )
