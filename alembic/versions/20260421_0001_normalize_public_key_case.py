"""Normalize public_key to lowercase and merge duplicate nodes

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-21

Before this migration, public_key values could be stored in mixed case:
- tag_import.py stored them as lowercase (via validate_public_key)
- letsmesh_normalizer.py stored them as UPPERCASE (via _normalize_full_public_key)
- MQTT topic paths stored them as-is

This caused duplicate nodes for the same physical device, with tags
linked to one and mesh events linked to another.

This migration:
1. Merges duplicate nodes (picking the one with the earliest first_seen)
2. Re-points all FK references to the winner node
3. Deletes the loser nodes
4. Normalizes all remaining public_keys to lowercase
5. Also lowercases public_key columns in child tables (advertisements, telemetry)
"""

from alembic import op
from sqlalchemy import text

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find groups of duplicate nodes (same lowercase public_key, different actual case)
    duplicates = conn.execute(text("""
        SELECT LOWER(public_key) AS lower_pk,
               GROUP_CONCAT(id) AS ids,
               COUNT(*) AS cnt
        FROM nodes
        GROUP BY LOWER(public_key)
        HAVING cnt > 1
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

            # For CASCADE tables, move records to winner first
            conn.execute(
                text(
                    "UPDATE node_tags SET node_id = :winner_id WHERE node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE event_observers SET observer_node_id = :winner_id WHERE observer_node_id = :loser_id"
                ),
                params,
            )

            # For SET NULL tables, re-point to winner instead of losing the link
            conn.execute(
                text(
                    "UPDATE advertisements SET observer_node_id = :winner_id WHERE observer_node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE advertisements SET node_id = :winner_id WHERE node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE telemetry SET observer_node_id = :winner_id WHERE observer_node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE telemetry SET node_id = :winner_id WHERE node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE messages SET observer_node_id = :winner_id WHERE observer_node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE trace_paths SET observer_node_id = :winner_id WHERE observer_node_id = :loser_id"
                ),
                params,
            )
            conn.execute(
                text(
                    "UPDATE events_log SET observer_node_id = :winner_id WHERE observer_node_id = :loser_id"
                ),
                params,
            )

            # Merge scalar fields into winner (keep best data)
            conn.execute(
                text("""
                UPDATE nodes SET
                    name = COALESCE(name, (SELECT name FROM nodes WHERE id = :loser_id)),
                    adv_type = COALESCE(adv_type, (SELECT adv_type FROM nodes WHERE id = :loser_id)),
                    last_seen = (
                        SELECT MAX(v) FROM (
                            SELECT last_seen AS v FROM nodes WHERE id = :winner_id
                            UNION ALL
                            SELECT last_seen AS v FROM nodes WHERE id = :loser_id
                        )
                    ),
                    lat = COALESCE(lat, (SELECT lat FROM nodes WHERE id = :loser_id)),
                    lon = COALESCE(lon, (SELECT lon FROM nodes WHERE id = :loser_id))
                WHERE id = :winner_id
                """),
                params,
            )

            # Delete the loser (CASCADE will clean up any remaining orphans)
            conn.execute(
                text("DELETE FROM nodes WHERE id = :loser_id"), {"loser_id": loser_id}
            )

    # Now normalize all remaining public_keys to lowercase
    conn.execute(text("UPDATE nodes SET public_key = LOWER(public_key)"))

    # Also lowercase public_key in child tables that store their own copy
    conn.execute(text("UPDATE advertisements SET public_key = LOWER(public_key)"))
    conn.execute(text("UPDATE telemetry SET node_public_key = LOWER(node_public_key)"))


def downgrade() -> None:
    # Cannot reverse the merge (duplicate data has been deleted).
    # The public_key normalization to lowercase is also irreversible
    # since we don't know the original case.
    pass
