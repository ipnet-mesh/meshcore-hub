"""add route health monitoring (consolidated)

Revision ID: ec40c67c8c83
Revises: 57bb65130b97
Create Date: 2026-07-16 20:43:00.000000+00:00

Consolidation of four formerly-separate migrations into one clean
migration that builds the final schema directly:

* ``8f2a3c4d5e6f`` — create five route health tables + backfill
  ``packet_path_hops`` from ``raw_packets.decoded``.
* ``76513f4c57e9`` — standalone ``ix_packet_path_hops_received_at`` index.
* ``71f6e01e4bf6`` — rename ``degraded_threshold`` -> ``clear_threshold``
  on ``routes`` and ``effective_degraded`` -> ``effective_clear`` on
  ``route_results``.  These columns are born with their final names here,
  so no rename runs.
* ``c0d1e2f3a4b5`` — deduplicate ``nodes`` by ``public_key`` and re-assert
  the UNIQUE index.  Idempotent (no-op on a clean DB) but retained so a
  restored backup with duplicate keys is repaired before route tables
  reference them.

Creates five tables for route health monitoring:
``routes``, ``route_nodes``, ``route_observers``, ``route_results`` and
``packet_path_hops``.  Routes are identified by endpoint labels
(``from_label`` / ``to_label``) with a composite unique index, and each
route carries a ``reversible`` flag so the matching engine can also accept
reverse-ordered paths.

The hop table is backfilled from ``raw_packets.decoded`` using a frozen
copy of the dual-path extraction logic (``_normalize_hash_list`` +
``decoded.path`` / ``payload.decoded.pathHashes`` fallback), mirroring
migration ``57bb65130b97``.

"""

from datetime import datetime, timezone
from typing import Any, Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec40c67c8c83"
down_revision: Union[str, None] = "57bb65130b97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BATCH_SIZE = 1000

# (table, column) for every FK referencing nodes.id.
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


def _normalize_hash_list(value: Any) -> list[str] | None:
    """Frozen copy of LetsMeshNormalizer._normalize_hash_list.

    Accepts even-length hex strings of 2 or more characters.
    Each string is uppercased and validated as hexadecimal.
    """
    if not isinstance(value, list):
        return None
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        token = item.strip().upper()
        if len(token) < 2 or len(token) % 2 != 0:
            continue
        if any(ch not in "0123456789ABCDEF" for ch in token):
            continue
        normalized.append(token)
    return normalized or None


def _extract_path_hashes(decoded: Any) -> list[str] | None:
    """Frozen copy of the dual-path extraction logic.

    Path hashes live at ``decoded.path`` for normal packets, with
    ``decoded.payload.decoded.pathHashes`` as the trace-style fallback.
    Returns the normalized list or None when no path hashes are present.
    """
    if not isinstance(decoded, dict):
        return None
    hashes = _normalize_hash_list(decoded.get("path"))
    if not hashes:
        payload = decoded.get("payload") or {}
        inner = payload.get("decoded") or {}
        hashes = _normalize_hash_list(inner.get("pathHashes"))
    return hashes or None


# Declared with sa.JSON-typed column so the SQLAlchemy type adapter
# deserializes ``decoded`` to a Python dict consistently on both backends.
_raw_packets = sa.table(
    "raw_packets",
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("decoded", sa.JSON),
    sa.Column("packet_hash", sa.String),
    sa.Column("received_at", sa.DateTime),
    sa.Column("observer_node_id", sa.String),
)


def upgrade() -> None:
    # --- routes ---
    op.create_table(
        "routes",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("from_label", sa.String(255), nullable=False),
        sa.Column("to_label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("match_width", sa.Integer, nullable=False),
        sa.Column("window_hours", sa.Integer, nullable=False),
        sa.Column("packet_count_threshold", sa.Integer, nullable=False),
        sa.Column("clear_threshold", sa.Integer, nullable=True),
        sa.Column("max_hop_span", sa.Integer, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column(
            "reversible",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index(
        "ix_routes_from_to",
        "routes",
        ["from_label", "to_label"],
        unique=True,
    )

    # --- route_nodes ---
    op.create_table(
        "route_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("route_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("expected_hash", sa.String(6), nullable=True),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_route_nodes_route_id", "route_nodes", ["route_id"])
    op.create_index("ix_route_nodes_node_id", "route_nodes", ["node_id"])

    # --- route_observers ---
    op.create_table(
        "route_observers",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("route_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_route_observers_route_id", "route_observers", ["route_id"])
    op.create_index("ix_route_observers_node_id", "route_observers", ["node_id"])

    # --- route_results ---
    op.create_table(
        "route_results",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("route_id", sa.String(36), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("quality", sa.String(20), nullable=False),
        sa.Column("matched_count", sa.Integer, nullable=False),
        sa.Column("threshold", sa.Integer, nullable=False),
        sa.Column("effective_clear", sa.Integer, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_route_results_route_id",
        "route_results",
        ["route_id"],
        unique=True,
    )

    # --- packet_path_hops ---
    op.create_table(
        "packet_path_hops",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("raw_packet_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("node_hash", sa.String(6), nullable=False),
        sa.Column("packet_hash", sa.String(32), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observer_node_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(
            ["raw_packet_id"], ["raw_packets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["observer_node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_packet_path_hops_node_hash_received_at",
        "packet_path_hops",
        ["node_hash", "received_at"],
    )
    op.create_index(
        "ix_packet_path_hops_raw_packet_id_position",
        "packet_path_hops",
        ["raw_packet_id", "position"],
    )
    op.create_index(
        "ix_packet_path_hops_received_at",
        "packet_path_hops",
        ["received_at"],
    )

    # --- Backfill packet_path_hops from raw_packets.decoded ---
    conn = op.get_bind()

    _packet_path_hops = sa.table(
        "packet_path_hops",
        sa.Column("id", sa.String),
        sa.Column("raw_packet_id", sa.String),
        sa.Column("position", sa.Integer),
        sa.Column("node_hash", sa.String),
        sa.Column("packet_hash", sa.String),
        sa.Column("received_at", sa.DateTime),
        sa.Column("observer_node_id", sa.String),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    last_id: str | None = None
    while True:
        query = (
            sa.select(
                _raw_packets.c.id,
                _raw_packets.c.decoded,
                _raw_packets.c.packet_hash,
                _raw_packets.c.received_at,
                _raw_packets.c.observer_node_id,
            )
            .order_by(_raw_packets.c.id)
            .limit(_BATCH_SIZE)
        )
        if last_id is not None:
            query = query.where(_raw_packets.c.id > last_id)

        batch = conn.execute(query).all()
        if not batch:
            break

        rows_to_insert: list[dict[str, Any]] = []
        for row in batch:
            last_id = row.id
            hashes = _extract_path_hashes(row.decoded)
            if not hashes:
                continue
            now = datetime.now(timezone.utc)
            for position, node_hash in enumerate(hashes):
                rows_to_insert.append(
                    {
                        "id": str(uuid4()),
                        "raw_packet_id": row.id,
                        "position": position,
                        "node_hash": node_hash,
                        "packet_hash": row.packet_hash,
                        "received_at": row.received_at,
                        "observer_node_id": row.observer_node_id,
                        "created_at": now,
                        "updated_at": now,
                    }
                )

        if rows_to_insert:
            conn.execute(_packet_path_hops.insert(), rows_to_insert)

    # --- Deduplicate nodes by public_key (idempotent data fix) ---
    # Merges duplicate nodes (winner = earliest first_seen, tiebreak
    # created_at), re-pointing every FK column that references nodes.id,
    # then re-asserts the UNIQUE index.  No-op on a clean database.
    from sqlalchemy import text

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
                try:
                    conn.execute(
                        text(
                            f"UPDATE {table} SET {column} = :winner_id "
                            f"WHERE {column} = :loser_id"
                        ),
                        params,
                    )
                except Exception:
                    pass

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

            # Delete the loser.
            conn.execute(
                text("DELETE FROM nodes WHERE id = :loser_id"),
                {"loser_id": loser_id},
            )

    # Normalize any remaining case variance (defense-in-depth).
    conn.execute(text("UPDATE nodes SET public_key = LOWER(public_key)"))

    # Re-assert the UNIQUE index on nodes.public_key (idempotent).
    conn.execute(text("DROP INDEX IF EXISTS ix_nodes_public_key"))
    conn.execute(text("CREATE UNIQUE INDEX ix_nodes_public_key ON nodes (public_key)"))


def downgrade() -> None:
    # The nodes dedup is irreversible (duplicate rows were deleted).
    op.drop_table("packet_path_hops")
    op.drop_table("route_results")
    op.drop_table("route_observers")
    op.drop_table("route_nodes")
    op.drop_table("routes")
