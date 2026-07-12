"""add route health monitoring tables

Revision ID: 8f2a3c4d5e6f
Revises: 57bb65130b97
Create Date: 2026-07-12 23:30:00.000000+00:00

Creates five tables for route health monitoring:
``routes``, ``route_nodes``, ``route_observers``, ``route_results`` and
``packet_path_hops``.  The hop table is backfilled from
``raw_packets.decoded`` using a frozen copy of the dual-path extraction logic
(``_normalize_hash_list`` + ``decoded.path`` / ``payload.decoded.pathHashes``
fallback), mirroring migration ``57bb65130b97``.

"""

from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8f2a3c4d5e6f"
down_revision: Union[str, None] = "57bb65130b97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BATCH_SIZE = 1000


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
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("match_width", sa.Integer, nullable=False),
        sa.Column("window_hours", sa.Integer, nullable=False),
        sa.Column("packet_count_threshold", sa.Integer, nullable=False),
        sa.Column("degraded_threshold", sa.Integer, nullable=True),
        sa.Column("max_hop_span", sa.Integer, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
    )
    op.create_index("ix_routes_name", "routes", ["name"], unique=True)

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
        sa.Column("effective_degraded", sa.Integer, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("route_id", name="uq_route_results_route_id"),
    )
    op.create_index("ix_route_results_route_id", "route_results", ["route_id"])

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

    from uuid import uuid4
    from datetime import datetime, timezone

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


def downgrade() -> None:
    op.drop_table("packet_path_hops")
    op.drop_table("route_results")
    op.drop_table("route_observers")
    op.drop_table("route_nodes")
    op.drop_table("routes")
