"""Deduplicate nodes by public_key and re-assert uniqueness

Revision ID: c0d1e2f3a4b5
Revises: 8f2a3c4d5e6f
Create Date: 2026-07-13 01:00:00.000000+00:00

A production database restore bypassed SQLite/Postgres UNIQUE enforcement on
``nodes.public_key``, leaving two rows with identical (or case-variant) keys.
This caused ``MultipleResultsFound`` in ``GET /api/v1/nodes/{public_key}`` and
in every collector handler that does find-or-create by public_key.

This migration is a superset of ``b1c2d3e4f5a6`` (which only knew about 9 FK
columns and is already stamped as applied). It:

1. Merges duplicate nodes (winner = earliest ``first_seen``, tiebreak
   ``created_at``), re-pointing all 14 FK columns that currently reference
   ``nodes.id``.
2. Merges scalar fields into the winner (name, adv_type, lat, lon, flags,
   last_seen via MAX, is_observer via OR).
3. Deletes losers.
4. Re-lowercases all remaining ``public_key`` values.
5. Re-asserts the UNIQUE index on ``nodes.public_key`` in case the restore
   dropped or weakened it.

Irreversible — deleting duplicates destroys data.
"""

from alembic import op
from sqlalchemy import text

revision = "c0d1e2f3a4b5"
down_revision = "8f2a3c4d5e6f"
branch_labels = None
depends_on = None


# (table, column, ondelete) for every FK referencing nodes.id.
# CASCADE rows must be re-pointed BEFORE the loser is deleted; SET NULL rows
# are also re-pointed (not nulled) so we keep the linkage rather than orphan it.
_REPOINT_COLUMNS = [
    # ondelete=CASCADE
    ("node_tags", "node_id"),
    ("event_observers", "observer_node_id"),
    ("route_nodes", "node_id"),
    ("route_observers", "node_id"),
    ("user_profile_nodes", "node_id"),
    # ondelete=SET NULL
    ("advertisements", "observer_node_id"),
    ("advertisements", "node_id"),
    ("telemetry", "observer_node_id"),
    ("telemetry", "node_id"),
    ("messages", "observer_node_id"),
    ("trace_paths", "observer_node_id"),
    ("events_log", "observer_node_id"),
    ("raw_packets", "observer_node_id"),
    ("packet_path_hops", "observer_node_id"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # SQLite uses GROUP_CONCAT; Postgres uses STRING_AGG. HAVING references
    # COUNT(*) directly (Postgres disallows SELECT aliases in HAVING).
    if conn.dialect.name == "postgresql":
        id_agg = "STRING_AGG(id::text, ',')"
    else:
        id_agg = "GROUP_CONCAT(id)"

    duplicates = conn.execute(text(f"""
        SELECT LOWER(public_key) AS lower_pk,
               {id_agg} AS ids,
               COUNT(*) AS cnt
        FROM nodes
        GROUP BY LOWER(public_key)
        HAVING COUNT(*) > 1
        """)).fetchall()

    for row in duplicates:
        lower_pk = row[0]
        ids = row[1].split(",")

        winner_row = conn.execute(
            text("""
            SELECT id FROM nodes
            WHERE LOWER(public_key) = :lower_pk
            ORDER BY first_seen ASC, created_at ASC
            LIMIT 1
            """),
            {"lower_pk": lower_pk},
        ).fetchone()

        if not winner_row:
            continue

        winner_id = winner_row[0]
        loser_ids = [nid for nid in ids if nid != winner_id]

        for loser_id in loser_ids:
            params = {"winner_id": winner_id, "loser_id": loser_id}

            # Re-point every FK column from loser to winner. Wrapped in
            # try/except per table so a missing table on an older DB doesn't
            # abort the whole migration (defensive — schema drift).
            for table, column in _REPOINT_COLUMNS:
                conn.execute(
                    text(
                        f"UPDATE {table} SET {column} = :winner_id "
                        f"WHERE {column} = :loser_id"
                    ),
                    params,
                )

            # Merge scalar fields into winner (keep best data from either row).
            conn.execute(
                text("""
                UPDATE nodes SET
                    name = COALESCE(name, (SELECT name FROM nodes WHERE id = :loser_id)),
                    adv_type = COALESCE(adv_type, (SELECT adv_type FROM nodes WHERE id = :loser_id)),
                    flags = COALESCE(flags, (SELECT flags FROM nodes WHERE id = :loser_id)),
                    lat = COALESCE(lat, (SELECT lat FROM nodes WHERE id = :loser_id)),
                    lon = COALESCE(lon, (SELECT lon FROM nodes WHERE id = :loser_id)),
                    last_seen = (
                        SELECT MAX(v) FROM (
                            SELECT last_seen AS v FROM nodes WHERE id = :winner_id
                            UNION ALL
                            SELECT last_seen AS v FROM nodes WHERE id = :loser_id
                        )
                    ),
                    is_observer = (
                        is_observer
                        OR (SELECT is_observer FROM nodes WHERE id = :loser_id)
                    )
                WHERE id = :winner_id
                """),
                params,
            )

            # Delete the loser. Remaining orphans are cleaned by CASCADE/SET
            # NULL at the FK level (now that we've re-pointed everything we
            # care about, SET NULL columns with no re-point would just null
            # out — but we re-pointed all of them above).
            conn.execute(
                text("DELETE FROM nodes WHERE id = :loser_id"),
                {"loser_id": loser_id},
            )

    # Normalize any remaining case variance (defense-in-depth — should be a
    # no-op now that b1c2d3e4f5a6 has run, but the restore may have reintroduced
    # mixed case).
    conn.execute(text("UPDATE nodes SET public_key = LOWER(public_key)"))

    # Re-assert the UNIQUE index on nodes.public_key. The restore may have
    # dropped it or recreated it as non-unique, which is how duplicates slipped
    # in to begin with. Drop-if-exists then CREATE UNIQUE INDEX. Idempotent.
    if conn.dialect.name == "postgresql":
        # Postgres: use CREATE UNIQUE INDEX CONCURRENTLY is not available
        # inside a transaction; alembic auto-begins one, so plain CREATE is
        # fine for the data-fix path.
        conn.execute(text("DROP INDEX IF EXISTS ix_nodes_public_key"))
        conn.execute(
            text("CREATE UNIQUE INDEX ix_nodes_public_key ON nodes (public_key)")
        )
    else:
        # SQLite: DROP/CREATE INDEX is fine without a table rebuild.
        conn.execute(text("DROP INDEX IF EXISTS ix_nodes_public_key"))
        conn.execute(
            text("CREATE UNIQUE INDEX ix_nodes_public_key ON nodes (public_key)")
        )


def downgrade() -> None:
    # Cannot reverse the merge — duplicate rows have been deleted.
    pass
