"""Tests for data cleanup functionality."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from meshcore_hub.collector.cleanup import cleanup_old_data, CleanupStats
from meshcore_hub.common.models import (
    Advertisement,
    EventLog,
    Message,
    Node,
    Telemetry,
    TracePath,
)


@pytest.mark.asyncio
async def test_cleanup_old_data_dry_run(async_db_session: AsyncSession) -> None:
    """Test cleanup in dry-run mode."""
    # Create test node
    node = Node(
        public_key="a" * 64,
        name="Test Node",
    )
    async_db_session.add(node)
    await async_db_session.flush()

    # Create old advertisement (60 days ago)
    old_date = datetime.now(timezone.utc) - timedelta(days=60)
    old_adv = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_adv)

    # Create recent advertisement (10 days ago)
    recent_date = datetime.now(timezone.utc) - timedelta(days=10)
    recent_adv = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=recent_date,
        updated_at=recent_date,
    )
    async_db_session.add(recent_adv)

    await async_db_session.commit()

    # Run cleanup in dry-run mode with 30-day retention
    stats = await cleanup_old_data(async_db_session, retention_days=30, dry_run=True)

    # Should report 1 advertisement would be deleted
    assert stats.advertisements_deleted == 1
    assert stats.total_deleted == 1

    # Verify no data was actually deleted
    await async_db_session.rollback()  # Refresh from DB
    from sqlalchemy import select, func

    count = await async_db_session.scalar(
        select(func.count()).select_from(Advertisement)
    )
    assert count == 2  # Both still exist


@pytest.mark.asyncio
async def test_cleanup_old_data_live(async_db_session: AsyncSession) -> None:
    """Test cleanup in live mode."""
    # Create test node
    node = Node(
        public_key="b" * 64,
        name="Test Node",
    )
    async_db_session.add(node)
    await async_db_session.flush()

    # Create old records (60 days ago)
    old_date = datetime.now(timezone.utc) - timedelta(days=60)

    old_adv = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_adv)

    old_msg = Message(
        receiver_node_id=node.id,
        message_type="channel",
        text="old message",
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_msg)

    old_telemetry = Telemetry(
        receiver_node_id=node.id,
        node_id=node.id,
        node_public_key=node.public_key,
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_telemetry)

    old_trace = TracePath(
        receiver_node_id=node.id,
        initiator_tag="test",
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_trace)

    old_event = EventLog(
        receiver_node_id=node.id,
        event_type="test_event",
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_event)

    # Create recent records (10 days ago)
    recent_date = datetime.now(timezone.utc) - timedelta(days=10)

    recent_adv = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=recent_date,
        updated_at=recent_date,
    )
    async_db_session.add(recent_adv)

    await async_db_session.commit()

    # Run cleanup with 30-day retention
    stats = await cleanup_old_data(async_db_session, retention_days=30, dry_run=False)

    # Verify statistics
    assert stats.advertisements_deleted == 1
    assert stats.messages_deleted == 1
    assert stats.telemetry_deleted == 1
    assert stats.trace_paths_deleted == 1
    assert stats.event_logs_deleted == 1
    assert stats.total_deleted == 5

    # Verify old data was deleted
    from sqlalchemy import select, func

    adv_count = await async_db_session.scalar(
        select(func.count()).select_from(Advertisement)
    )
    assert adv_count == 1  # Only recent one remains

    msg_count = await async_db_session.scalar(select(func.count()).select_from(Message))
    assert msg_count == 0  # Old one deleted

    # Verify node still exists
    from sqlalchemy import select

    node_result = await async_db_session.scalar(select(Node).where(Node.id == node.id))
    assert node_result is not None


@pytest.mark.asyncio
async def test_cleanup_respects_retention_period(
    async_db_session: AsyncSession,
) -> None:
    """Test that cleanup respects the retention period."""
    # Create test node
    node = Node(
        public_key="d" * 64,
        name="Test Node",
    )
    async_db_session.add(node)
    await async_db_session.flush()

    # Create advertisements at different ages
    now = datetime.now(timezone.utc)

    # 90 days old - should be deleted with 30-day retention
    very_old = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=now - timedelta(days=90),
        updated_at=now - timedelta(days=90),
    )
    async_db_session.add(very_old)

    # 40 days old - should be deleted with 30-day retention
    old = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=now - timedelta(days=40),
        updated_at=now - timedelta(days=40),
    )
    async_db_session.add(old)

    # 20 days old - should be kept
    recent = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=now - timedelta(days=20),
        updated_at=now - timedelta(days=20),
    )
    async_db_session.add(recent)

    # 5 days old - should be kept
    very_recent = Advertisement(
        node_id=node.id,
        public_key=node.public_key,
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=5),
    )
    async_db_session.add(very_recent)

    await async_db_session.commit()

    # Run cleanup with 30-day retention
    stats = await cleanup_old_data(async_db_session, retention_days=30, dry_run=False)

    # Should delete the 2 old ones, keep the 2 recent ones
    assert stats.advertisements_deleted == 2
    assert stats.total_deleted == 2

    # Verify count
    from sqlalchemy import select, func

    adv_count = await async_db_session.scalar(
        select(func.count()).select_from(Advertisement)
    )
    assert adv_count == 2


@pytest.mark.asyncio
async def test_cleanup_stats_repr() -> None:
    """Test CleanupStats string representation."""
    stats = CleanupStats()
    stats.advertisements_deleted = 10
    stats.messages_deleted = 5
    stats.telemetry_deleted = 3
    stats.trace_paths_deleted = 2
    stats.event_logs_deleted = 1
    stats.total_deleted = 21

    repr_str = repr(stats)
    assert "total=21" in repr_str
    assert "advertisements=10" in repr_str
    assert "messages=5" in repr_str
