"""Rename receiver_node_id to observer_node_id and event_receivers to event_observers

Revision ID: a1b2c3d4e5f6
Revises: 4e2e787a1660
Create Date: 2026-04-12

Note: The unique constraint on event_observers retains its original name
(uq_event_receivers_hash_node) since SQLite does not support renaming
constraints without fully recreating the table with explicit DDL. The
constraint correctly references the renamed column (observer_node_id)
and the ORM uses column-based conflict resolution, so this has no
functional impact.

"""

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "4e2e787a1660"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("event_receivers", "event_observers")

    op.drop_index("ix_event_receivers_event_hash", table_name="event_observers")
    op.drop_index("ix_event_receivers_receiver_node_id", table_name="event_observers")
    op.drop_index("ix_event_receivers_type_hash", table_name="event_observers")

    with op.batch_alter_table("event_observers", recreate="always") as batch_op:
        batch_op.alter_column("receiver_node_id", new_column_name="observer_node_id")
        batch_op.alter_column("received_at", new_column_name="observed_at")

    op.create_index("ix_event_observers_event_hash", "event_observers", ["event_hash"])
    op.create_index(
        "ix_event_observers_observer_node_id", "event_observers", ["observer_node_id"]
    )
    op.create_index(
        "ix_event_observers_type_hash", "event_observers", ["event_type", "event_hash"]
    )

    op.drop_index("ix_advertisements_receiver_node_id", table_name="advertisements")
    with op.batch_alter_table("advertisements") as batch_op:
        batch_op.alter_column("receiver_node_id", new_column_name="observer_node_id")
    op.create_index(
        "ix_advertisements_observer_node_id", "advertisements", ["observer_node_id"]
    )

    op.drop_index("ix_messages_receiver_node_id", table_name="messages")
    with op.batch_alter_table("messages") as batch_op:
        batch_op.alter_column("receiver_node_id", new_column_name="observer_node_id")
    op.create_index("ix_messages_observer_node_id", "messages", ["observer_node_id"])

    op.drop_index("ix_trace_paths_receiver_node_id", table_name="trace_paths")
    with op.batch_alter_table("trace_paths") as batch_op:
        batch_op.alter_column("receiver_node_id", new_column_name="observer_node_id")
    op.create_index(
        "ix_trace_paths_observer_node_id", "trace_paths", ["observer_node_id"]
    )

    op.drop_index("ix_telemetry_receiver_node_id", table_name="telemetry")
    with op.batch_alter_table("telemetry") as batch_op:
        batch_op.alter_column("receiver_node_id", new_column_name="observer_node_id")
    op.create_index("ix_telemetry_observer_node_id", "telemetry", ["observer_node_id"])

    op.drop_index("ix_events_log_receiver_node_id", table_name="events_log")
    with op.batch_alter_table("events_log") as batch_op:
        batch_op.alter_column("receiver_node_id", new_column_name="observer_node_id")
    op.create_index(
        "ix_events_log_observer_node_id", "events_log", ["observer_node_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_events_log_observer_node_id", table_name="events_log")
    with op.batch_alter_table("events_log") as batch_op:
        batch_op.alter_column("observer_node_id", new_column_name="receiver_node_id")
    op.create_index(
        "ix_events_log_receiver_node_id", "events_log", ["receiver_node_id"]
    )

    op.drop_index("ix_telemetry_observer_node_id", table_name="telemetry")
    with op.batch_alter_table("telemetry") as batch_op:
        batch_op.alter_column("observer_node_id", new_column_name="receiver_node_id")
    op.create_index("ix_telemetry_receiver_node_id", "telemetry", ["receiver_node_id"])

    op.drop_index("ix_trace_paths_observer_node_id", table_name="trace_paths")
    with op.batch_alter_table("trace_paths") as batch_op:
        batch_op.alter_column("observer_node_id", new_column_name="receiver_node_id")
    op.create_index(
        "ix_trace_paths_receiver_node_id", "trace_paths", ["receiver_node_id"]
    )

    op.drop_index("ix_messages_observer_node_id", table_name="messages")
    with op.batch_alter_table("messages") as batch_op:
        batch_op.alter_column("observer_node_id", new_column_name="receiver_node_id")
    op.create_index("ix_messages_receiver_node_id", "messages", ["receiver_node_id"])

    op.drop_index("ix_advertisements_observer_node_id", table_name="advertisements")
    with op.batch_alter_table("advertisements") as batch_op:
        batch_op.alter_column("observer_node_id", new_column_name="receiver_node_id")
    op.create_index(
        "ix_advertisements_receiver_node_id", "advertisements", ["receiver_node_id"]
    )

    op.drop_index("ix_event_observers_event_hash", table_name="event_observers")
    op.drop_index("ix_event_observers_observer_node_id", table_name="event_observers")
    op.drop_index("ix_event_observers_type_hash", table_name="event_observers")

    with op.batch_alter_table("event_observers", recreate="always") as batch_op:
        batch_op.alter_column("observer_node_id", new_column_name="receiver_node_id")
        batch_op.alter_column("observed_at", new_column_name="received_at")

    op.create_index("ix_event_receivers_event_hash", "event_observers", ["event_hash"])
    op.create_index(
        "ix_event_receivers_receiver_node_id", "event_observers", ["receiver_node_id"]
    )
    op.create_index(
        "ix_event_receivers_type_hash", "event_observers", ["event_type", "event_hash"]
    )

    op.rename_table("event_observers", "event_receivers")
