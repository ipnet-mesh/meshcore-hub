"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2024-12-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create nodes table
    op.create_table(
        "nodes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("adv_type", sa.String(20), nullable=True),
        sa.Column("flags", sa.Integer(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_key"),
    )
    op.create_index("ix_nodes_public_key", "nodes", ["public_key"])
    op.create_index("ix_nodes_last_seen", "nodes", ["last_seen"])
    op.create_index("ix_nodes_adv_type", "nodes", ["adv_type"])

    # Create node_tags table
    op.create_table(
        "node_tags",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(20), nullable=False, server_default="string"),
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
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "key", name="uq_node_tags_node_key"),
    )
    op.create_index("ix_node_tags_node_id", "node_tags", ["node_id"])
    op.create_index("ix_node_tags_key", "node_tags", ["key"])

    # Create members table
    op.create_table(
        "members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("callsign", sa.String(20), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(255), nullable=True),
        sa.Column("public_key", sa.String(64), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_members_name", "members", ["name"])
    op.create_index("ix_members_public_key", "members", ["public_key"])

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("receiver_node_id", sa.String(), nullable=True),
        sa.Column("message_type", sa.String(20), nullable=False),
        sa.Column("pubkey_prefix", sa.String(12), nullable=True),
        sa.Column("channel_idx", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("path_len", sa.Integer(), nullable=True),
        sa.Column("txt_type", sa.Integer(), nullable=True),
        sa.Column("signature", sa.String(8), nullable=True),
        sa.Column("snr", sa.Float(), nullable=True),
        sa.Column("sender_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["receiver_node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_receiver_node_id", "messages", ["receiver_node_id"])
    op.create_index("ix_messages_message_type", "messages", ["message_type"])
    op.create_index("ix_messages_pubkey_prefix", "messages", ["pubkey_prefix"])
    op.create_index("ix_messages_channel_idx", "messages", ["channel_idx"])
    op.create_index("ix_messages_received_at", "messages", ["received_at"])

    # Create advertisements table
    op.create_table(
        "advertisements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("receiver_node_id", sa.String(), nullable=True),
        sa.Column("node_id", sa.String(), nullable=True),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("adv_type", sa.String(20), nullable=True),
        sa.Column("flags", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["receiver_node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_advertisements_receiver_node_id", "advertisements", ["receiver_node_id"]
    )
    op.create_index("ix_advertisements_node_id", "advertisements", ["node_id"])
    op.create_index("ix_advertisements_public_key", "advertisements", ["public_key"])
    op.create_index("ix_advertisements_received_at", "advertisements", ["received_at"])

    # Create trace_paths table
    op.create_table(
        "trace_paths",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("receiver_node_id", sa.String(), nullable=True),
        sa.Column("initiator_tag", sa.BigInteger(), nullable=False),
        sa.Column("path_len", sa.Integer(), nullable=True),
        sa.Column("flags", sa.Integer(), nullable=True),
        sa.Column("auth", sa.Integer(), nullable=True),
        sa.Column("path_hashes", sa.JSON(), nullable=True),
        sa.Column("snr_values", sa.JSON(), nullable=True),
        sa.Column("hop_count", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["receiver_node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trace_paths_receiver_node_id", "trace_paths", ["receiver_node_id"]
    )
    op.create_index("ix_trace_paths_initiator_tag", "trace_paths", ["initiator_tag"])
    op.create_index("ix_trace_paths_received_at", "trace_paths", ["received_at"])

    # Create telemetry table
    op.create_table(
        "telemetry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("receiver_node_id", sa.String(), nullable=True),
        sa.Column("node_id", sa.String(), nullable=True),
        sa.Column("node_public_key", sa.String(64), nullable=False),
        sa.Column("lpp_data", sa.LargeBinary(), nullable=True),
        sa.Column("parsed_data", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["receiver_node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telemetry_receiver_node_id", "telemetry", ["receiver_node_id"])
    op.create_index("ix_telemetry_node_id", "telemetry", ["node_id"])
    op.create_index("ix_telemetry_node_public_key", "telemetry", ["node_public_key"])
    op.create_index("ix_telemetry_received_at", "telemetry", ["received_at"])

    # Create events_log table
    op.create_table(
        "events_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("receiver_node_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["receiver_node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_events_log_receiver_node_id", "events_log", ["receiver_node_id"]
    )
    op.create_index("ix_events_log_event_type", "events_log", ["event_type"])
    op.create_index("ix_events_log_received_at", "events_log", ["received_at"])


def downgrade() -> None:
    op.drop_table("events_log")
    op.drop_table("telemetry")
    op.drop_table("trace_paths")
    op.drop_table("advertisements")
    op.drop_table("messages")
    op.drop_table("members")
    op.drop_table("node_tags")
    op.drop_table("nodes")
