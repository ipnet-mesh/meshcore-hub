"""add event_hash to raw packets and path hops

Revision ID: 6b3430fd84f4
Revises: ec40c67c8c83
Create Date: 2026-07-18 12:00:00.000000+00:00

Adds a nullable ``event_hash`` column to ``raw_packets`` and
``packet_path_hops``.  The column denormalizes the underlying structured
event's identity (advertisement / message / telemetry / trace
``event_hash``) so the route evaluator can deduplicate matches by their
underlying event rather than by per-transmission wire hash.

Background: a single advert or message retransmitted (or flooded) through
the mesh produces one ``RawPacket`` row per on-air copy, each with a
fresh wire ``packet_hash``.  Counting those as distinct matches let a
single underlying event satisfy ``packet_count_threshold`` within seconds
and bias the route's health.  Joining through ``event_hash`` collapses
all receptions of the same underlying event into one match.

Rows captured before this migration (and any unclassified wire packets)
keep ``event_hash IS NULL``; the evaluator falls back to the wire
``packet_hash`` for those, preserving today's behaviour until they age
out of the configured ``window_hours``.  No data backfill is performed.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6b3430fd84f4"
down_revision: Union[str, None] = "ec40c67c8c83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("event_hash", sa.String(length=32), nullable=True)
        )
        batch_op.create_index("ix_raw_packets_event_hash", ["event_hash"], unique=False)

    with op.batch_alter_table("packet_path_hops", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("event_hash", sa.String(length=32), nullable=True)
        )
        batch_op.create_index(
            "ix_packet_path_hops_event_hash_received_at",
            ["event_hash", "received_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("packet_path_hops", schema=None) as batch_op:
        batch_op.drop_index("ix_packet_path_hops_event_hash_received_at")
        batch_op.drop_column("event_hash")

    with op.batch_alter_table("raw_packets", schema=None) as batch_op:
        batch_op.drop_index("ix_raw_packets_event_hash")
        batch_op.drop_column("event_hash")
