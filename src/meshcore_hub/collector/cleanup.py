"""Data retention and cleanup service for MeshCore Hub.

This module provides functionality to delete old event data and inactive nodes
based on configured retention policies.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meshcore_hub.common.models import (
    Advertisement,
    EventLog,
    Message,
    Node,
    Telemetry,
    TracePath,
)

logger = logging.getLogger(__name__)


class CleanupStats:
    """Statistics from a cleanup operation."""

    def __init__(self) -> None:
        self.advertisements_deleted: int = 0
        self.messages_deleted: int = 0
        self.telemetry_deleted: int = 0
        self.trace_paths_deleted: int = 0
        self.event_logs_deleted: int = 0
        self.nodes_deleted: int = 0
        self.total_deleted: int = 0

    def __repr__(self) -> str:
        return (
            f"CleanupStats(total={self.total_deleted}, "
            f"advertisements={self.advertisements_deleted}, "
            f"messages={self.messages_deleted}, "
            f"telemetry={self.telemetry_deleted}, "
            f"trace_paths={self.trace_paths_deleted}, "
            f"event_logs={self.event_logs_deleted}, "
            f"nodes={self.nodes_deleted})"
        )


async def cleanup_old_data(
    db: AsyncSession,
    retention_days: int,
    dry_run: bool = False,
) -> CleanupStats:
    """Delete event data older than the retention period.

    Args:
        db: Database session
        retention_days: Number of days to retain data
        dry_run: If True, only count records without deleting

    Returns:
        CleanupStats object with deletion counts
    """
    stats = CleanupStats()
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    logger.info(
        "Starting data cleanup (dry_run=%s, retention_days=%d, cutoff=%s)",
        dry_run,
        retention_days,
        cutoff_date.isoformat(),
    )

    # Clean up advertisements
    stats.advertisements_deleted = await _cleanup_table(
        db, Advertisement, cutoff_date, "advertisements", dry_run
    )

    # Clean up messages
    stats.messages_deleted = await _cleanup_table(
        db, Message, cutoff_date, "messages", dry_run
    )

    # Clean up telemetry
    stats.telemetry_deleted = await _cleanup_table(
        db, Telemetry, cutoff_date, "telemetry", dry_run
    )

    # Clean up trace paths
    stats.trace_paths_deleted = await _cleanup_table(
        db, TracePath, cutoff_date, "trace_paths", dry_run
    )

    # Clean up event logs
    stats.event_logs_deleted = await _cleanup_table(
        db, EventLog, cutoff_date, "event_logs", dry_run
    )

    stats.total_deleted = (
        stats.advertisements_deleted
        + stats.messages_deleted
        + stats.telemetry_deleted
        + stats.trace_paths_deleted
        + stats.event_logs_deleted
    )

    if not dry_run:
        await db.commit()
        logger.info("Cleanup completed: %s", stats)
    else:
        logger.info("Cleanup dry run completed: %s", stats)

    return stats


async def _cleanup_table(
    db: AsyncSession,
    model: type,
    cutoff_date: datetime,
    table_name: str,
    dry_run: bool,
) -> int:
    """Delete old records from a specific table.

    Args:
        db: Database session
        model: SQLAlchemy model class
        cutoff_date: Delete records older than this date
        table_name: Name of table for logging
        dry_run: If True, only count without deleting

    Returns:
        Number of records deleted (or would be deleted in dry_run)
    """
    from sqlalchemy import select

    if dry_run:
        # Count records that would be deleted
        stmt = (
            select(func.count())
            .select_from(model)
            .where(model.created_at < cutoff_date)  # type: ignore[attr-defined]
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        logger.debug(
            "[DRY RUN] Would delete %d records from %s older than %s",
            count,
            table_name,
            cutoff_date.isoformat(),
        )
        return count
    else:
        # Delete old records
        result = await db.execute(delete(model).where(model.created_at < cutoff_date))  # type: ignore[attr-defined]
        count = result.rowcount or 0  # type: ignore[attr-defined]
        logger.debug(
            "Deleted %d records from %s older than %s",
            count,
            table_name,
            cutoff_date.isoformat(),
        )
        return count


async def cleanup_inactive_nodes(
    db: AsyncSession,
    inactivity_days: int,
    dry_run: bool = False,
) -> int:
    """Delete nodes that haven't been seen for the specified number of days.

    Only deletes nodes where last_seen is older than the cutoff date.
    Nodes with last_seen=NULL are NOT deleted (never seen on network).

    Args:
        db: Database session
        inactivity_days: Delete nodes not seen for this many days
        dry_run: If True, only count without deleting

    Returns:
        Number of nodes deleted (or would be deleted in dry_run)
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=inactivity_days)

    logger.info(
        "Starting node cleanup (dry_run=%s, inactivity_days=%d, cutoff=%s)",
        dry_run,
        inactivity_days,
        cutoff_date.isoformat(),
    )

    if dry_run:
        # Count nodes that would be deleted
        # Only count nodes with last_seen < cutoff (excludes NULL last_seen)
        stmt = (
            select(func.count())
            .select_from(Node)
            .where(Node.last_seen < cutoff_date)
            .where(Node.last_seen.isnot(None))
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        logger.info(
            "[DRY RUN] Would delete %d nodes not seen since %s",
            count,
            cutoff_date.isoformat(),
        )
        return count
    else:
        # Delete inactive nodes
        # Only delete nodes with last_seen < cutoff (excludes NULL last_seen)
        result = await db.execute(
            delete(Node)
            .where(Node.last_seen < cutoff_date)
            .where(Node.last_seen.isnot(None))
        )
        await db.commit()
        count = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info(
            "Deleted %d nodes not seen since %s",
            count,
            cutoff_date.isoformat(),
        )
        return count
