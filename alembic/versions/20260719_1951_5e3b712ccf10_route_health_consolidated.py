"""route health monitoring (consolidated)

Revision ID: 5e3b712ccf10
Revises: 57bb65130b97
Create Date: 2026-07-19 19:51:00.000000+00:00

Single-step build of the route-health schema on top of the production
head ``57bb65130b97``.  Creates seven tables (``routes``, ``route_nodes``,
``route_observers``, ``route_results``, ``packet_path_hops``,
``route_result_history``, ``route_recent_matches``), adds an nullable
``event_hash`` column to the pre-existing ``raw_packets`` table, and runs
three idempotent backfills: ``packet_path_hops`` from
``raw_packets.decoded``, ``nodes`` deduplication by ``public_key``, and
``route_result_history`` + ``route_results.quality_avg`` for any enabled
routes.

Supersedes (and replaces) the formerly separate revisions
``ec40c67c8c83``, ``6b3430fd84f4`` and ``cf8dd7eaba9b``.
"""

from datetime import datetime, timezone
from typing import Any, Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e3b712ccf10"
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

    # --- route_results (quality_avg baked in from cf8dd7eaba9b) ---
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
        sa.Column("quality_avg", sa.String(20), nullable=True),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_route_results_route_id",
        "route_results",
        ["route_id"],
        unique=True,
    )

    # --- packet_path_hops (event_hash baked in from 6b3430fd84f4) ---
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
        sa.Column("event_hash", sa.String(32), nullable=True),
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
    op.create_index(
        "ix_packet_path_hops_event_hash_received_at",
        "packet_path_hops",
        ["event_hash", "received_at"],
    )

    # --- route_result_history (from cf8dd7eaba9b) ---
    op.create_table(
        "route_result_history",
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
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("quality", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("matched_count", sa.Integer, nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "route_id", "date", name="uq_route_result_history_route_date"
        ),
    )
    op.create_index(
        "ix_route_result_history_route_id",
        "route_result_history",
        ["route_id"],
    )
    op.create_index(
        "ix_route_result_history_route_id_date",
        "route_result_history",
        ["route_id", "date"],
    )

    # --- route_recent_matches (from cf8dd7eaba9b) ---
    op.create_table(
        "route_recent_matches",
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
        sa.Column("raw_packet_id", sa.String(36), nullable=False),
        sa.Column("first_position", sa.Integer, nullable=False),
        sa.Column("last_position", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["raw_packet_id"], ["raw_packets.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "route_id", "raw_packet_id", name="uq_route_recent_matches_route_packet"
        ),
    )
    op.create_index(
        "ix_route_recent_matches_route_id",
        "route_recent_matches",
        ["route_id"],
    )

    # --- raw_packets.event_hash (table pre-exists at 57bb65130b97) ---
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("event_hash", sa.String(length=32), nullable=True)
        )
        batch_op.create_index("ix_raw_packets_event_hash", ["event_hash"], unique=False)

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

    # --- Backfill route_result_history + quality_avg for enabled routes ---
    # Defensive: a backfill failure on any single route (or globally) must
    # never block the schema change. The periodic sweep repairs missing
    # rows on its next tick. On a freshly-restored production snapshot
    # there are zero routes, so this is effectively a no-op; the loop is
    # retained so a restore from a dev backup that DOES have routes
    # backfills correctly.
    try:
        _backfill_history()
    except Exception as e:  # noqa: BLE001 — never abort the migration
        print(f"[route health precompute] backfill skipped: {e}")


def downgrade() -> None:
    # The nodes dedup is irreversible (duplicate rows were deleted).
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.drop_index("ix_raw_packets_event_hash")
        batch_op.drop_column("event_hash")

    op.drop_index(
        "ix_route_recent_matches_route_id",
        table_name="route_recent_matches",
    )
    op.drop_table("route_recent_matches")

    op.drop_index(
        "ix_route_result_history_route_id_date",
        table_name="route_result_history",
    )
    op.drop_index(
        "ix_route_result_history_route_id",
        table_name="route_result_history",
    )
    op.drop_table("route_result_history")

    op.drop_index(
        "ix_packet_path_hops_event_hash_received_at",
        table_name="packet_path_hops",
    )
    op.drop_index(
        "ix_packet_path_hops_received_at",
        table_name="packet_path_hops",
    )
    op.drop_index(
        "ix_packet_path_hops_raw_packet_id_position",
        table_name="packet_path_hops",
    )
    op.drop_index(
        "ix_packet_path_hops_node_hash_received_at",
        table_name="packet_path_hops",
    )
    op.drop_table("packet_path_hops")

    op.drop_index("ix_route_results_route_id", table_name="route_results")
    op.drop_table("route_results")

    op.drop_index("ix_route_observers_node_id", table_name="route_observers")
    op.drop_index("ix_route_observers_route_id", table_name="route_observers")
    op.drop_table("route_observers")

    op.drop_index("ix_route_nodes_node_id", table_name="route_nodes")
    op.drop_index("ix_route_nodes_route_id", table_name="route_nodes")
    op.drop_table("route_nodes")

    op.drop_index("ix_routes_from_to", table_name="routes")
    op.drop_table("routes")


def _backfill_history() -> None:
    """Populate history rows and ``quality_avg`` for existing enabled routes.

    Imports the live route-evaluation helpers from the application code
    rather than freezing copies — the new code is in place when this
    migration runs, and the helpers cover edge cases (reversible match,
    dedup by event_hash, per-day existence checks) that would be unsafe
    to duplicate.
    """
    import logging
    from datetime import datetime, timezone
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from meshcore_hub.collector.routes import (
        compute_average_quality,
        evaluate_route_history,
    )
    from meshcore_hub.common.config import get_collector_settings
    from meshcore_hub.common.models.route import Route
    from meshcore_hub.common.models.route_result import RouteResult
    from meshcore_hub.common.models.route_result_history import RouteResultHistory

    logger = logging.getLogger("alembic.route_health_consolidated")

    conn = op.get_bind()
    settings = get_collector_settings()
    retention_days = settings.effective_raw_packet_retention_days

    now = datetime.now(timezone.utc)
    today = now.date()

    with Session(bind=conn) as session:
        routes = (
            session.execute(sa.select(Route).where(Route.enabled.is_(True)))
            .scalars()
            .all()
        )

        if not routes:
            return

        for route in routes:
            try:
                # Evaluate the retention window EXCLUDING today — the
                # today bucket is the evaluator's job and would be stale
                # the moment a new packet arrives. Leaving it for the
                # first sweep keeps the migration fast.
                history_tuples = evaluate_route_history(
                    session, route, retention_days, include_today=False
                )

                # Bulk-insert (skip today if the engine already produced it
                # because window_hours happens to land on today's UTC day).
                rows_to_insert = []
                for day, quality, state, matched_count in history_tuples:
                    if day >= today:
                        continue
                    rows_to_insert.append(
                        {
                            "id": str(uuid4()),
                            "route_id": route.id,
                            "date": day,
                            "quality": quality,
                            "state": state,
                            "matched_count": matched_count,
                            "evaluated_at": now,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )

                if rows_to_insert:
                    conn.execute(
                        sa.insert(RouteResultHistory.__table__), rows_to_insert
                    )

                # Compute quality_avg from the last 7 history rows
                # (today is excluded — falls back to route_result.quality
                # at read time when missing, matching existing semantics).
                last_seven = history_tuples[-7:] if history_tuples else []
                avg = compute_average_quality(
                    last_seven,
                    fallback=None,
                )

                # Only stamp quality_avg when we actually have history;
                # otherwise let the first evaluator tick fill it.
                if last_seven:
                    conn.execute(
                        sa.update(RouteResult.__table__)
                        .where(RouteResult.__table__.c.route_id == route.id)
                        .values(quality_avg=avg)
                    )

            except Exception as route_err:
                logger.warning(
                    "Backfill failed for route %s -> %s: %s",
                    getattr(route, "from_label", "?"),
                    getattr(route, "to_label", "?"),
                    route_err,
                )
