"""Dashboard API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.api.channel_visibility import (
    get_max_visibility_level,
    get_visible_channel_indices,
    resolve_user_role,
)
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.observer_utils import resolve_sender_names
from meshcore_hub.common.models import (
    Advertisement,
    Message,
    Node,
    NodeTag,
    UserProfile,
)
from meshcore_hub.common.schemas.messages import (
    ChannelMessage,
    DailyActivity,
    DailyActivityPoint,
    DashboardStats,
    MessageActivity,
    NodeCountHistory,
    RecentAdvertisement,
)

router = APIRouter()

_FLOOD_ROUTE_TYPES = {"flood", "transport_flood"}


def _dashboard_stats_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"dashboard/stats:role={role}:{sorted_query_string(request)}"


def _dashboard_msg_activity_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"dashboard/message-activity:role={role}:{sorted_query_string(request)}"


def _flood_only_filter(
    ad_model: type[Advertisement],
) -> ColumnElement[bool]:
    """Build a flood-only filter clause for advertisement queries.

    Includes flood/transport_flood records and NULL (historical) records.
    """
    return or_(
        ad_model.route_type.in_(_FLOOD_ROUTE_TYPES),
        ad_model.route_type.is_(None),
    )


@router.get("/stats", response_model=DashboardStats)
@cached(
    "dashboard/stats",
    ttl_setting="redis_cache_ttl_dashboard",
    key_builder=_dashboard_stats_key_builder,
)
def get_stats(
    _: RequireRead,
    session: DbSession,
    request: Request,
) -> DashboardStats:
    """Get dashboard statistics."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)
    seven_days_ago = now - timedelta(days=7)

    # Resolve channel visibility
    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

    # Build channel message visibility filter
    def _channel_visible_filter(
        model: type[Message] = Message,
    ) -> ColumnElement[bool]:
        return or_(
            model.message_type != "channel",
            model.channel_idx.is_(None),
            model.channel_idx.in_(visible_indices),
        )

    # Total nodes
    total_nodes = session.execute(select(func.count()).select_from(Node)).scalar() or 0

    # Active nodes (last 24h)
    active_nodes = (
        session.execute(
            select(func.count()).select_from(Node).where(Node.last_seen >= yesterday)
        ).scalar()
        or 0
    )

    # Total messages
    total_messages = (
        session.execute(
            select(func.count()).select_from(Message).where(_channel_visible_filter())
        ).scalar()
        or 0
    )

    # Messages today
    messages_today = (
        session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.received_at >= today_start)
            .where(_channel_visible_filter())
        ).scalar()
        or 0
    )

    # Total advertisements (flood-only)
    total_advertisements = (
        session.execute(
            select(func.count())
            .select_from(Advertisement)
            .where(_flood_only_filter(Advertisement))
        ).scalar()
        or 0
    )

    # Advertisements in last 24h (flood-only)
    advertisements_24h = (
        session.execute(
            select(func.count())
            .select_from(Advertisement)
            .where(Advertisement.received_at >= yesterday)
            .where(_flood_only_filter(Advertisement))
        ).scalar()
        or 0
    )

    # Advertisements in last 7 days (flood-only)
    advertisements_7d = (
        session.execute(
            select(func.count())
            .select_from(Advertisement)
            .where(Advertisement.received_at >= seven_days_ago)
            .where(_flood_only_filter(Advertisement))
        ).scalar()
        or 0
    )

    # Messages in last 7 days
    messages_7d = (
        session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.received_at >= seven_days_ago)
            .where(_channel_visible_filter())
        ).scalar()
        or 0
    )

    # Recent advertisements (last 10, flood-only)
    recent_ads = (
        session.execute(
            select(Advertisement)
            .where(_flood_only_filter(Advertisement))
            .order_by(Advertisement.received_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    # Get node names, adv_types, and name tags for the advertised nodes
    ad_public_keys = [ad.public_key for ad in recent_ads]
    node_names: dict[str, str] = {}
    node_adv_types: dict[str, str] = {}
    tag_names: dict[str, str] = {}
    if ad_public_keys:
        # Get node names and adv_types from Node table
        node_query = select(Node.public_key, Node.name, Node.adv_type).where(
            Node.public_key.in_(ad_public_keys)
        )
        for public_key, name, adv_type in session.execute(node_query).all():
            if name:
                node_names[public_key] = name
            if adv_type:
                node_adv_types[public_key] = adv_type

        # Get name tags
        tag_name_query = (
            select(Node.public_key, NodeTag.value)
            .join(NodeTag, Node.id == NodeTag.node_id)
            .where(Node.public_key.in_(ad_public_keys))
            .where(NodeTag.key == "name")
        )
        for public_key, value in session.execute(tag_name_query).all():
            tag_names[public_key] = value

    recent_advertisements = [
        RecentAdvertisement(
            public_key=ad.public_key,
            name=ad.name or node_names.get(ad.public_key),
            tag_name=tag_names.get(ad.public_key),
            adv_type=ad.adv_type or node_adv_types.get(ad.public_key),
            received_at=ad.received_at,
        )
        for ad in recent_ads
    ]

    # Channel message counts (only visible channels)
    channel_counts_query = (
        select(Message.channel_idx, func.count())
        .where(Message.message_type == "channel")
        .where(Message.channel_idx.isnot(None))
        .where(Message.channel_idx.in_(visible_indices))
        .group_by(Message.channel_idx)
    )
    channel_results = session.execute(channel_counts_query).all()
    channel_message_counts = {
        int(channel): int(count) for channel, count in channel_results
    }

    # Get latest 5 messages for each channel that has messages
    channel_messages: dict[int, list[ChannelMessage]] = {}
    for channel_idx, _ in channel_results:
        messages_query = (
            select(Message)
            .where(Message.message_type == "channel")
            .where(Message.channel_idx == channel_idx)
            .order_by(Message.received_at.desc())
            .limit(5)
        )
        channel_msgs = session.execute(messages_query).scalars().all()

        # Look up sender names for these messages
        msg_prefixes = [m.pubkey_prefix for m in channel_msgs if m.pubkey_prefix]
        msg_sender_names, msg_tag_names = resolve_sender_names(session, msg_prefixes)

        channel_messages[int(channel_idx)] = [
            ChannelMessage(
                text=m.text,
                sender_name=(
                    msg_sender_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
                ),
                sender_tag_name=(
                    msg_tag_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
                ),
                pubkey_prefix=m.pubkey_prefix,
                received_at=m.received_at,
            )
            for m in channel_msgs
        ]

    from meshcore_hub.common.config import get_web_settings

    web_settings = get_web_settings()
    operator_role = web_settings.oidc_role_operator
    member_role = web_settings.oidc_role_member
    test_role = web_settings.oidc_role_test

    total_operators_query = (
        select(func.count())
        .select_from(UserProfile)
        .where(UserProfile.roles.contains(operator_role))
    )
    if test_role:
        total_operators_query = total_operators_query.where(
            ~UserProfile.roles.contains(test_role)
        )
    total_operators = session.execute(total_operators_query).scalar() or 0

    total_members_query = (
        select(func.count())
        .select_from(UserProfile)
        .where(UserProfile.roles.contains(member_role))
    )
    if test_role:
        total_members_query = total_members_query.where(
            ~UserProfile.roles.contains(test_role)
        )
    total_members = session.execute(total_members_query).scalar() or 0

    return DashboardStats(
        total_nodes=total_nodes,
        active_nodes=active_nodes,
        total_messages=total_messages,
        messages_today=messages_today,
        messages_7d=messages_7d,
        total_advertisements=total_advertisements,
        advertisements_24h=advertisements_24h,
        advertisements_7d=advertisements_7d,
        recent_advertisements=recent_advertisements,
        channel_message_counts=channel_message_counts,
        channel_messages=channel_messages,
        total_operators=total_operators,
        total_members=total_members,
    )


@router.get("/activity", response_model=DailyActivity)
@cached("dashboard/activity", ttl_setting="redis_cache_ttl_dashboard")
def get_activity(
    _: RequireRead,
    session: DbSession,
    request: Request,
    days: int = 30,
) -> DailyActivity:
    """Get daily advertisement activity for the specified period.

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Daily advertisement counts for each day in the period (excluding today)
    """
    # Limit to max 90 days
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    # End at start of today (exclude today's incomplete data)
    end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    # Query advertisement counts grouped by date
    # Use SQLite's date() function for grouping (returns string 'YYYY-MM-DD')
    date_expr = func.date(Advertisement.received_at)

    query = (
        select(
            date_expr.label("date"),
            func.count().label("count"),
        )
        .where(Advertisement.received_at >= start_date)
        .where(Advertisement.received_at < end_date)
        .where(_flood_only_filter(Advertisement))
        .group_by(date_expr)
        .order_by(date_expr)
    )

    results = session.execute(query).all()

    # Build a dict of date -> count from results (date is already a string)
    counts_by_date = {row.date: row.count for row in results}

    # Generate all dates in the range, filling in zeros for missing days
    data = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        count = counts_by_date.get(date_str, 0)
        data.append(DailyActivityPoint(date=date_str, count=count))

    return DailyActivity(days=days, data=data)


@router.get("/message-activity", response_model=MessageActivity)
@cached(
    "dashboard/message-activity",
    ttl_setting="redis_cache_ttl_dashboard",
    key_builder=_dashboard_msg_activity_key_builder,
)
def get_message_activity(
    _: RequireRead,
    session: DbSession,
    request: Request,
    days: int = 30,
) -> MessageActivity:
    """Get daily message activity for the specified period.

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Daily message counts for each day in the period (excluding today)
    """
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

    date_expr = func.date(Message.received_at)

    query = (
        select(
            date_expr.label("date"),
            func.count().label("count"),
        )
        .where(Message.received_at >= start_date)
        .where(Message.received_at < end_date)
        .where(
            or_(
                Message.message_type != "channel",
                Message.channel_idx.is_(None),
                Message.channel_idx.in_(visible_indices),
            )
        )
        .group_by(date_expr)
        .order_by(date_expr)
    )

    results = session.execute(query).all()
    counts_by_date = {row.date: row.count for row in results}

    # Generate all dates in the range, filling in zeros for missing days
    data = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        count = counts_by_date.get(date_str, 0)
        data.append(DailyActivityPoint(date=date_str, count=count))

    return MessageActivity(days=days, data=data)


@router.get("/node-count", response_model=NodeCountHistory)
@cached("dashboard/node-count", ttl_setting="redis_cache_ttl_dashboard")
def get_node_count_history(
    _: RequireRead,
    session: DbSession,
    request: Request,
    days: int = 30,
) -> NodeCountHistory:
    """Get cumulative node count over time.

    For each day, shows the total number of nodes that existed by that date
    (based on their created_at timestamp).

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Cumulative node count for each day in the period (excluding today)
    """
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    # End at start of today (exclude today's incomplete data)
    end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    # Cumulative count: seed the running total with every node that already
    # existed before the window, then add each day's new nodes as we walk it.
    # This replaces a per-day COUNT(*) loop (up to 90 full scans) with two
    # queries.
    baseline = (
        session.execute(
            select(func.count()).select_from(Node).where(Node.created_at < start_date)
        ).scalar()
        or 0
    )

    # New nodes per calendar day within the window.
    date_expr = func.date(Node.created_at)
    per_day_query = (
        select(date_expr.label("date"), func.count().label("count"))
        .where(Node.created_at >= start_date)
        .where(Node.created_at < end_date)
        .group_by(date_expr)
    )
    new_by_date: dict[str, int] = {
        row[0]: row[1] for row in session.execute(per_day_query).all()
    }

    data = []
    running = baseline
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        running += new_by_date.get(date_str, 0)
        data.append(DailyActivityPoint(date=date_str, count=running))

    return NodeCountHistory(days=days, data=data)
