"""Tests for data cleanup functionality."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meshcore_hub.collector.cleanup import (
    cleanup_inactive_nodes,
    cleanup_old_data,
    cleanup_orphaned_node_relations,
    CleanupStats,
)
from meshcore_hub.common.models import (
    Advertisement,
    EventLog,
    EventObserver,
    Message,
    Node,
    NodeTag,
    Telemetry,
    TracePath,
)
from meshcore_hub.common.models.user_profile_node import UserProfileNode
from meshcore_hub.common.models.user_profile import UserProfile


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
        observer_node_id=node.id,
        message_type="channel",
        text="old message",
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_msg)

    old_telemetry = Telemetry(
        observer_node_id=node.id,
        node_id=node.id,
        node_public_key=node.public_key,
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_telemetry)

    old_trace = TracePath(
        observer_node_id=node.id,
        initiator_tag="test",
        created_at=old_date,
        updated_at=old_date,
    )
    async_db_session.add(old_trace)

    old_event = EventLog(
        observer_node_id=node.id,
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


@pytest.mark.asyncio
async def test_cleanup_inactive_nodes_cascades(async_db_session: AsyncSession) -> None:
    """Test that deleting inactive nodes cascades to dependent tables."""
    old_date = datetime.now(timezone.utc) - timedelta(days=60)

    node = Node(
        public_key="a" * 64,
        name="Stale Node",
        last_seen=old_date,
    )
    async_db_session.add(node)
    await async_db_session.flush()

    profile = UserProfile(user_id="cascade-test-user", name="Test")
    async_db_session.add(profile)
    await async_db_session.flush()

    adoption = UserProfileNode(
        user_profile_id=profile.id,
        node_id=node.id,
    )
    async_db_session.add(adoption)

    tag = NodeTag(node_id=node.id, key="role", value="gateway")
    async_db_session.add(tag)

    observer = EventObserver(
        event_type="message",
        event_hash="abc123def456abc123def456abc12345",
        observer_node_id=node.id,
    )
    async_db_session.add(observer)

    await async_db_session.commit()

    deleted = await cleanup_inactive_nodes(
        async_db_session, inactivity_days=30, dry_run=False
    )
    assert deleted == 1

    assert await async_db_session.scalar(select(func.count()).select_from(Node)) == 0
    assert (
        await async_db_session.scalar(select(func.count()).select_from(UserProfileNode))
        == 0
    )
    assert await async_db_session.scalar(select(func.count()).select_from(NodeTag)) == 0
    assert (
        await async_db_session.scalar(select(func.count()).select_from(EventObserver))
        == 0
    )

    assert (
        await async_db_session.scalar(select(func.count()).select_from(UserProfile))
        == 1
    )


@pytest.mark.asyncio
async def test_cleanup_orphaned_node_relations(
    async_db_session: AsyncSession,
) -> None:
    """Test orphan cleanup deletes rows referencing non-existent nodes."""
    from sqlalchemy import text

    node = Node(
        public_key="o" * 64,
        name="Temporary Node",
    )
    async_db_session.add(node)
    await async_db_session.flush()

    profile = UserProfile(user_id="orphan-test-user", name="Test")
    async_db_session.add(profile)
    await async_db_session.flush()

    adoption = UserProfileNode(
        user_profile_id=profile.id,
        node_id=node.id,
    )
    async_db_session.add(adoption)

    tag = NodeTag(node_id=node.id, key="role", value="gateway")
    async_db_session.add(tag)

    observer = EventObserver(
        event_type="message",
        event_hash="abc123def456abc123def456abc12399",
        observer_node_id=node.id,
    )
    async_db_session.add(observer)

    await async_db_session.commit()

    await async_db_session.execute(text("PRAGMA foreign_keys=OFF"))
    await async_db_session.execute(
        text("DELETE FROM nodes WHERE id = :id"), {"id": node.id}
    )
    await async_db_session.commit()
    await async_db_session.execute(text("PRAGMA foreign_keys=ON"))

    counts = await cleanup_orphaned_node_relations(async_db_session, dry_run=False)

    assert counts["user_profile_nodes"] == 1
    assert counts["event_observers"] == 1
    assert counts["node_tags"] == 1

    assert (
        await async_db_session.scalar(select(func.count()).select_from(UserProfileNode))
        == 0
    )
    assert await async_db_session.scalar(select(func.count()).select_from(NodeTag)) == 0
    assert (
        await async_db_session.scalar(select(func.count()).select_from(EventObserver))
        == 0
    )


@pytest.mark.asyncio
async def test_cleanup_orphaned_node_relations_dry_run(
    async_db_session: AsyncSession,
) -> None:
    """Test orphan dry-run counts but does not delete."""
    from sqlalchemy import text

    node = Node(
        public_key="p" * 64,
        name="Dry Run Node",
    )
    async_db_session.add(node)
    await async_db_session.flush()

    profile = UserProfile(user_id="orphan-dryrun-user", name="Test")
    async_db_session.add(profile)
    await async_db_session.flush()

    adoption = UserProfileNode(
        user_profile_id=profile.id,
        node_id=node.id,
    )
    async_db_session.add(adoption)
    await async_db_session.commit()

    await async_db_session.execute(text("PRAGMA foreign_keys=OFF"))
    await async_db_session.execute(
        text("DELETE FROM nodes WHERE id = :id"), {"id": node.id}
    )
    await async_db_session.commit()
    await async_db_session.execute(text("PRAGMA foreign_keys=ON"))

    counts = await cleanup_orphaned_node_relations(async_db_session, dry_run=True)

    assert counts["user_profile_nodes"] == 1

    assert (
        await async_db_session.scalar(select(func.count()).select_from(UserProfileNode))
        == 1
    )


@pytest.mark.asyncio
async def test_cleanup_clears_stale_observer_flags(
    async_db_session: AsyncSession,
) -> None:
    """A node whose only events are pruned gets is_observer cleared; an active
    observer keeps its flag."""
    old_date = datetime.now(timezone.utc) - timedelta(days=60)
    recent_date = datetime.now(timezone.utc) - timedelta(days=5)

    stale = Node(public_key="s" * 64, name="Stale Observer", is_observer=True)
    active = Node(public_key="b" * 64, name="Active Observer", is_observer=True)
    async_db_session.add_all([stale, active])
    await async_db_session.flush()

    # Stale observer's only event is old and will be pruned
    async_db_session.add(
        Advertisement(
            public_key=stale.public_key,
            observer_node_id=stale.id,
            created_at=old_date,
            updated_at=old_date,
        )
    )
    # Active observer has a recent event that survives cleanup
    async_db_session.add(
        Advertisement(
            public_key=active.public_key,
            observer_node_id=active.id,
            created_at=recent_date,
            updated_at=recent_date,
        )
    )
    await async_db_session.commit()

    stats = await cleanup_old_data(async_db_session, retention_days=30, dry_run=False)

    assert stats.observers_cleared == 1

    await async_db_session.rollback()  # Refresh from DB
    stale_flag = await async_db_session.scalar(
        select(Node.is_observer).where(Node.id == stale.id)
    )
    active_flag = await async_db_session.scalar(
        select(Node.is_observer).where(Node.id == active.id)
    )
    assert stale_flag is False
    assert active_flag is True
