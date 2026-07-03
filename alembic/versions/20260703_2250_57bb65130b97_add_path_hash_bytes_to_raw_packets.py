"""add path_hash_bytes to raw_packets

Revision ID: 57bb65130b97
Revises: 38abdf4651fc
Create Date: 2026-07-03 22:50:33.598167+00:00

Adds a nullable ``path_hash_bytes`` column to ``raw_packets`` (widest
path-hash prefix width: 1/2/3, or NULL when no path hashes are present).
The collector computes this at ingest going forward; this migration
backfills historical rows from their stored ``decoded`` JSON using a
self-contained, frozen copy of the dual-path extraction logic.

"""

from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "57bb65130b97"
down_revision: Union[str, None] = "38abdf4651fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BATCH_SIZE = 1000

# Declared with a sa.JSON-typed column so the SQLAlchemy type adapter
# deserializes ``decoded`` to a Python dict consistently on both SQLite
# (TEXT storage) and Postgres.  Using raw text("SELECT decoded ...") would
# bypass the adapter and make deserialization driver-dependent.
_raw_packets = sa.table(
    "raw_packets",
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("decoded", sa.JSON),
    sa.Column("path_hash_bytes", sa.Integer),
)


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


def _compute_path_hash_byte_width(decoded: Any) -> int | None:
    """Frozen copy of the dual-path extraction + max(len//2) logic.

    Path hashes live at ``decoded.path`` for normal packets, with
    ``decoded.payload.decoded.pathHashes`` as the trace-style fallback.
    Returns the widest prefix width in bytes, or None when no path hashes
    are present/decodable.
    """
    if not isinstance(decoded, dict):
        return None
    hashes = _normalize_hash_list(decoded.get("path"))
    if not hashes:
        payload = decoded.get("payload") or {}
        inner = payload.get("decoded") or {}
        hashes = _normalize_hash_list(inner.get("pathHashes"))
    if not hashes:
        return None
    return max(len(h) // 2 for h in hashes)


def upgrade() -> None:
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("path_hash_bytes", sa.Integer(), nullable=True))

    conn = op.get_bind()

    # Keyset-paginated backfill over all rows so rows whose ``decoded`` is
    # NULL (uncomputable) are visited once and left NULL without causing an
    # infinite loop.
    last_id: str | None = None
    while True:
        query = (
            sa.select(_raw_packets.c.id, _raw_packets.c.decoded)
            .order_by(_raw_packets.c.id)
            .limit(_BATCH_SIZE)
        )
        if last_id is not None:
            query = query.where(_raw_packets.c.id > last_id)

        batch = conn.execute(query).all()
        if not batch:
            break

        for row in batch:
            last_id = row.id
            width = _compute_path_hash_byte_width(row.decoded)
            if width is not None:
                conn.execute(
                    sa.update(_raw_packets)
                    .where(_raw_packets.c.id == row.id)
                    .values(path_hash_bytes=width)
                )


def downgrade() -> None:
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.drop_column("path_hash_bytes")
