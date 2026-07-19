"""Dashboard API routes."""

from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from fastapi import APIRouter, Request
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.api.channel_visibility import (
    get_max_visibility_level,
    get_visible_channel_indices,
    resolve_user_role,
)
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.observer_utils import (
    fetch_observers_for_events,
    resolve_sender_names,
)
from meshcore_hub.common.config import get_collector_settings
from meshcore_hub.common.models import (
    Advertisement,
    Message,
    Node,
    NodeTag,
    RawPacket,
    Route,
    RouteVisibility,
    UserProfile,
)
from meshcore_hub.common.models.route_result_history import RouteResultHistory
from meshcore_hub.common.schemas.messages import (
    BreakdownBucket,
    ChannelMessage,
    DailyActivity,
    DailyActivityPoint,
    DashboardStats,
    MessageActivity,
    NodeCountHistory,
    PacketBreakdown,
    RecentActivity,
    RecentAdvertisement,
)
from meshcore_hub.common.schemas.routes import (
    RouteDayQuality,
    RouteOverviewEntry,
    RoutesOverview,
)

router = APIRouter()

_FLOOD_ROUTE_TYPES = {"flood", "transport_flood"}


def _dashboard_stats_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"dashboard/stats:role={role}:{sorted_query_string(request)}"


def _dashboard_msg_activity_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"dashboard/message-activity:role={role}:{sorted_query_string(request)}"


def _dashboard_recent_activity_key_builder(request: Request) -> str:
    """Role-scoped key for ``GET /dashboard/recent-activity``.

    The response filters channel messages by visibility, so the cache key
    must vary by role — otherwise an anonymous GET would fill the cache
    with a redacted response served to a subsequent admin GET.
    """
    role = resolve_user_role(request) or "anonymous"
    return f"dashboard/recent-activity:role={role}:{sorted_query_string(request)}"


def _dashboard_routes_overview_key_builder(request: Request) -> str:
    """Role-agnostic key for ``GET /dashboard/routes-overview``.

    The endpoint surfaces only ``community``-visibility routes regardless
    of the caller's role, so the response is identical for anonymous,
    member, operator, and admin callers — no role dimension in the key.
    """
    return f"dashboard/routes-overview:{sorted_query_string(request)}"


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


def _date_bucket_key(value: str | date | None) -> str | None:
    """Coerce a DB-returned date bucket key to a canonical ``%Y-%m-%d`` string.

    SQLite's ``func.date()`` returns a ``str``; Postgres returns a
    ``datetime.date``. This normalizes both to the same string key so dict
    lookups by ``"%Y-%m-%d"`` succeed on either backend. ``None`` passes
    through unchanged.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


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

    # Node counts (total + active in the last 24h) in a single pass.
    node_row = session.execute(
        select(
            func.count(),
            func.sum(case((Node.last_seen >= yesterday, 1), else_=0)),
        ).select_from(Node)
    ).one()
    total_nodes = node_row[0] or 0
    active_nodes = node_row[1] or 0

    # Message counts (total + today + last 7 days), channel-visible only,
    # via conditional aggregation so it's one query instead of three.
    msg_row = session.execute(
        select(
            func.count(),
            func.sum(case((Message.received_at >= today_start, 1), else_=0)),
            func.sum(case((Message.received_at >= seven_days_ago, 1), else_=0)),
        )
        .select_from(Message)
        .where(_channel_visible_filter())
    ).one()
    total_messages = msg_row[0] or 0
    messages_today = msg_row[1] or 0
    messages_7d = msg_row[2] or 0

    # Advertisement counts (total + last 24h + last 7 days), flood-only,
    # again folded into one query.
    adv_row = session.execute(
        select(
            func.count(),
            func.sum(case((Advertisement.received_at >= yesterday, 1), else_=0)),
            func.sum(case((Advertisement.received_at >= seven_days_ago, 1), else_=0)),
        )
        .select_from(Advertisement)
        .where(_flood_only_filter(Advertisement))
    ).one()
    total_advertisements = adv_row[0] or 0
    advertisements_24h = adv_row[1] or 0
    advertisements_7d = adv_row[2] or 0

    # Raw-packet counts (total + last 7 days), observer-level volume metric
    # with no role/channel filter (payload redaction lives on list/detail only).
    packet_row = session.execute(
        select(
            func.count(RawPacket.id).label("total_packets"),
            func.sum(case((RawPacket.received_at >= seven_days_ago, 1), else_=0)).label(
                "packets_7d"
            ),
        ).select_from(RawPacket)
    ).one()
    total_packets = packet_row[0] or 0
    packets_7d = packet_row[1] or 0

    # Channel message counts (only visible channels). The recent messages
    # themselves live on /dashboard/recent-activity so they can carry a
    # shorter cache TTL than these aggregate counts.
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

    from meshcore_hub.common.config import get_web_settings

    web_settings = get_web_settings()
    operator_role = web_settings.oidc_role_operator
    member_role = web_settings.oidc_role_member
    test_role = web_settings.oidc_role_test

    # Operator + member counts in one query. The optional test-role exclusion
    # is folded into each conditional branch.
    operator_cond = UserProfile.roles.contains(operator_role)
    member_cond = UserProfile.roles.contains(member_role)
    if test_role:
        not_test = ~UserProfile.roles.contains(test_role)
        operator_cond = and_(operator_cond, not_test)
        member_cond = and_(member_cond, not_test)

    profile_row = session.execute(
        select(
            func.sum(case((operator_cond, 1), else_=0)),
            func.sum(case((member_cond, 1), else_=0)),
        ).select_from(UserProfile)
    ).one()
    total_operators = profile_row[0] or 0
    total_members = profile_row[1] or 0

    return DashboardStats(
        total_nodes=total_nodes,
        active_nodes=active_nodes,
        total_messages=total_messages,
        messages_today=messages_today,
        messages_7d=messages_7d,
        total_advertisements=total_advertisements,
        advertisements_24h=advertisements_24h,
        advertisements_7d=advertisements_7d,
        channel_message_counts=channel_message_counts,
        total_operators=total_operators,
        total_members=total_members,
        total_packets=total_packets,
        packets_7d=packets_7d,
    )


@router.get("/recent-activity", response_model=RecentActivity)
@cached(
    "dashboard/recent-activity",
    key_builder=_dashboard_recent_activity_key_builder,
)
def get_recent_activity(
    _: RequireRead,
    session: DbSession,
    request: Request,
) -> RecentActivity:
    """Get the recent-adverts and recent-channel-messages lists.

    Split out of ``GET /dashboard/stats`` so they can be cached at the
    default ``redis_cache_ttl`` (30 s) instead of the much longer
    ``redis_cache_ttl_dashboard`` that covers the aggregate counts — the
    Recent Adverts / Recent Channel Messages panels are the only
    dashboard widgets that need minute-level freshness.

    Role-visibility filtered the same way as the rest of the dashboard:
    anonymous viewers see only public-channel messages, while operators
    see every channel. Cache key is role-scoped accordingly.
    """
    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

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

    # Batch-resolve observers (via event_observers) and the legacy
    # observed_by public key for the recent adverts, mirroring the
    # advertisements list endpoint.
    ad_event_hashes = [ad.event_hash for ad in recent_ads if ad.event_hash]
    observers_by_hash = fetch_observers_for_events(
        session, "advertisement", ad_event_hashes
    )

    observer_node_ids = [
        ad.observer_node_id for ad in recent_ads if ad.observer_node_id
    ]
    observer_pk_map: dict[str, str] = {}
    if observer_node_ids:
        obs_query = select(Node.id, Node.public_key).where(
            Node.id.in_(observer_node_ids)
        )
        for node_id, public_key in session.execute(obs_query).all():
            observer_pk_map[node_id] = public_key

    recent_advertisements = [
        RecentAdvertisement(
            public_key=ad.public_key,
            name=ad.name or node_names.get(ad.public_key),
            tag_name=tag_names.get(ad.public_key),
            adv_type=ad.adv_type or node_adv_types.get(ad.public_key),
            received_at=ad.received_at,
            route_type=ad.route_type,
            observers=observers_by_hash.get(ad.event_hash, []) if ad.event_hash else [],
            observed_by=(
                observer_pk_map.get(ad.observer_node_id)
                if ad.observer_node_id
                else None
            ),
        )
        for ad in recent_ads
    ]

    # Channel messages for each visible channel (up to 5 latest each).
    # The per-channel counts stay on /dashboard/stats (they're aggregate
    # counts, not a "recent" list); only the message bodies live here.
    channel_messages: dict[int, list[ChannelMessage]] = {}
    for channel_idx in visible_indices:
        messages_query = (
            select(Message)
            .where(Message.message_type == "channel")
            .where(Message.channel_idx == channel_idx)
            .order_by(Message.received_at.desc())
            .limit(5)
        )
        channel_msgs = session.execute(messages_query).scalars().all()
        if not channel_msgs:
            continue

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

    return RecentActivity(
        recent_advertisements=recent_advertisements,
        channel_messages=channel_messages,
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

    # Build a dict of date -> count, normalizing the key to a string so it
    # works on both SQLite (func.date() returns str) and Postgres (returns date).
    counts_by_date = {_date_bucket_key(row.date): row.count for row in results}

    # Generate all dates in the range, filling in zeros for missing days
    data = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        count = counts_by_date.get(date_str, 0)
        data.append(DailyActivityPoint(date=date_str, count=count))

    return DailyActivity(days=days, data=data)


@router.get("/packet-activity", response_model=DailyActivity)
@cached("dashboard/packet-activity", ttl_setting="redis_cache_ttl_dashboard")
def get_packet_activity(
    _: RequireRead,
    session: DbSession,
    request: Request,
    days: int = 30,
) -> DailyActivity:
    """Get daily raw-packet activity for the specified period.

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Daily raw-packet counts for each day in the period (excluding today)
    """
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    date_expr = func.date(RawPacket.received_at)

    query = (
        select(
            date_expr.label("date"),
            func.count().label("count"),
        )
        .where(RawPacket.received_at >= start_date)
        .where(RawPacket.received_at < end_date)
        .group_by(date_expr)
        .order_by(date_expr)
    )

    results = session.execute(query).all()
    counts_by_date = {_date_bucket_key(row.date): row.count for row in results}

    data = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        count = counts_by_date.get(date_str, 0)
        data.append(DailyActivityPoint(date=date_str, count=count))

    return DailyActivity(days=days, data=data)


# Max number of distinct event-type buckets shown verbatim; remaining values
# are rolled into a single "other" bucket so the chart stays legible.
_PACKET_BREAKDOWN_TOP_N = 6


@router.get("/packet-breakdown", response_model=PacketBreakdown)
@cached("dashboard/packet-breakdown", ttl_setting="redis_cache_ttl_dashboard")
def get_packet_breakdown(
    _: RequireRead,
    session: DbSession,
    request: Request,
    days: int = 7,
) -> PacketBreakdown:
    """Get raw-packet composition (by event type and path-hash width).

    Args:
        days: Number of days to include (default 7, max 90)

    Returns:
        Counts bucketed by event type (top 6 + "other") and by path-hash
        byte width (1b/2b/3b, NULL excluded) for the period (excluding today).
    """
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    window_clauses = (
        RawPacket.received_at >= start_date,
        RawPacket.received_at < end_date,
    )

    # Event-type breakdown: top N by count, remainder rolled into "other".
    event_rows = session.execute(
        select(RawPacket.event_type, func.count().label("count"))
        .where(*window_clauses)
        .group_by(RawPacket.event_type)
        .order_by(func.count().desc())
    ).all()

    by_event_type: list[BreakdownBucket] = []
    other_total = 0
    for label, count in event_rows[:_PACKET_BREAKDOWN_TOP_N]:
        by_event_type.append(
            BreakdownBucket(
                label=label if label is not None else "unknown", count=count
            )
        )
    if len(event_rows) > _PACKET_BREAKDOWN_TOP_N:
        for _, count in event_rows[_PACKET_BREAKDOWN_TOP_N:]:
            other_total += count
        by_event_type.append(BreakdownBucket(label="other", count=other_total))

    # Path-width breakdown: fixed 1b/2b/3b order, NULL excluded, zero-filled.
    width_rows = session.execute(
        select(RawPacket.path_hash_bytes, func.count().label("count"))
        .where(*window_clauses)
        .where(RawPacket.path_hash_bytes.isnot(None))
        .group_by(RawPacket.path_hash_bytes)
    ).all()
    width_counts = {row[0]: row[1] for row in width_rows}

    by_path_width = [
        BreakdownBucket(label="1b", count=width_counts.get(1, 0)),
        BreakdownBucket(label="2b", count=width_counts.get(2, 0)),
        BreakdownBucket(label="3b", count=width_counts.get(3, 0)),
    ]

    return PacketBreakdown(
        days=days,
        by_event_type=by_event_type,
        by_path_width=by_path_width,
    )


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
    counts_by_date = {_date_bucket_key(row.date): row.count for row in results}

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
    new_by_date = {
        _date_bucket_key(row.date): row._mapping["count"]
        for row in session.execute(per_day_query).all()
    }

    data = []
    running = baseline
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        running += new_by_date.get(date_str, 0)
        data.append(DailyActivityPoint(date=date_str, count=running))

    return NodeCountHistory(days=days, data=data)


@router.get("/routes-overview", response_model=RoutesOverview)
@cached(
    "dashboard/routes-overview",
    ttl_setting="redis_cache_ttl_dashboard",
    key_builder=_dashboard_routes_overview_key_builder,
)
def get_routes_overview(
    _: RequireRead,
    session: DbSession,
    request: Request,
    days: int = 7,
) -> RoutesOverview:
    """Get an aggregate snapshot of route fleet health for the dashboard.

    Returns:

    - ``by_state``: route counts bucketed by their current ``state``
      (clear / marginal / failing / no_coverage / disabled).
    - ``routes``: one entry per visible route carrying its current
      ``state``/``quality``/``matched_count`` (from the latest
      ``RouteResult`` written by the background evaluator) plus a
      ``days``-long history (includes today) for the trend chart and
      per-route strip grid.

    The dashboard widget only surfaces ``community``-visibility routes,
    regardless of the caller's role — operators and admins still see
    member/operator/admin-tier routes on the dedicated ``/routes`` page,
    but the dashboard is intentionally limited to the community fleet.
    ``days`` is clamped to the configured raw-packet retention window so
    history queries can't scan purged data.

    History is read in a single bulk query against ``route_result_history``
    for every visible route — no per-route scans of ``packet_path_hops``
    on the hot path. Missing historical days pad with ``unknown`` /
    ``no_coverage`` / ``0`` (matching the disabled-route semantics).
    """
    days = min(days, 90)
    retention = get_collector_settings().effective_raw_packet_retention_days
    days = min(days, retention)

    routes = (
        session.execute(
            select(Route)
            .where(Route.visibility == RouteVisibility.COMMUNITY.value)
            .order_by(Route.from_label)
        )
        .scalars()
        .all()
    )
    visible = list(routes)

    # Bulk-load precomputed history for every visible route in one indexed
    # query. ``read_route_history_from_db`` pads missing days and appends
    # the today rolling-window segment sourced from each route's
    # ``route_result`` (so the rightmost chart point matches the badge).
    history_by_route = _bulk_read_history(session, visible, days)

    # State buckets — ``disabled`` for switched-off routes, otherwise the
    # evaluator's last persisted state (falling back to ``no_coverage``
    # when no result exists yet, e.g. a freshly created route).
    state_counts: dict[str, int] = {}
    entries: list[RouteOverviewEntry] = []
    for route in visible:
        history_tuples = history_by_route.get(route.id, [])
        history = [
            RouteDayQuality(date=d, quality=q, state=s, matched_count=c)
            for d, q, s, c in history_tuples
        ]

        if not route.enabled:
            state = "disabled"
            quality = "disabled"
            matched: int | None = None
        elif route.route_result is not None:
            state = route.route_result.state or "no_coverage"
            quality = route.route_result.quality or "no_coverage"
            matched = route.route_result.matched_count
        else:
            state = "no_coverage"
            quality = "no_coverage"
            matched = None

        state_counts[state] = state_counts.get(state, 0) + 1
        entries.append(
            RouteOverviewEntry(
                id=str(route.id),
                from_label=route.from_label,
                to_label=route.to_label,
                visibility=route.visibility,
                enabled=route.enabled,
                state=state,
                quality=quality,
                matched_count=matched,
                history=history,
            )
        )

    # Stable, UI-friendly bucket order. State values come from the
    # evaluator's ``RouteState`` enum (``healthy`` / ``unhealthy`` /
    # ``no_coverage``) plus the synthetic ``disabled`` we emit for
    # switched-off routes. Any unknown state sorts after the known set.
    preferred_order = [
        "healthy",
        "unhealthy",
        "no_coverage",
        "disabled",
    ]
    by_state: list[BreakdownBucket] = []
    for label in preferred_order:
        count = state_counts.pop(label, 0)
        if count:
            by_state.append(BreakdownBucket(label=label, count=count))
    for label, count in sorted(state_counts.items()):
        by_state.append(BreakdownBucket(label=label, count=count))

    return RoutesOverview(days=days, by_state=by_state, routes=entries)


def _bulk_read_history(
    session: DbSession,
    routes: list[Route],
    days: int,
) -> dict[str, list[tuple[date, str, str, int]]]:
    """Bulk-load precomputed history for ``routes`` over the last ``days`` days.

    Returns ``{route_id: [(date, quality, state, matched_count), ...]}``
    keyed by route id. Each route's list has ``days + 1`` entries (the
    historical UTC calendar days plus a synthetic today segment sourced
    from ``route_result``, matching ``read_route_history_from_db``'s
    ``include_today=True`` semantics). Disabled routes get all-unknown
    padding without hitting the DB.
    """
    if not routes:
        return {}

    now = datetime.now(timezone.utc)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = today_midnight.date()
    oldest = (today_midnight - timedelta(days=days)).date()

    enabled_ids = [r.id for r in routes if r.enabled]
    history_rows: Sequence[tuple[str, date, str, str, int]] = []
    if enabled_ids:
        history_rows = (
            session.execute(
                select(
                    RouteResultHistory.route_id,
                    RouteResultHistory.date,
                    RouteResultHistory.quality,
                    RouteResultHistory.state,
                    RouteResultHistory.matched_count,
                )
                .where(RouteResultHistory.route_id.in_(enabled_ids))
                .where(RouteResultHistory.date >= oldest)
                .where(RouteResultHistory.date < today)
                .order_by(RouteResultHistory.route_id, RouteResultHistory.date)
            )
            .tuples()
            .all()
        )

    by_route: dict[str, dict[date, tuple[str, str, int]]] = {}
    for route_id, day, quality, state, matched_count in history_rows:
        by_route.setdefault(route_id, {})[day] = (quality, state, matched_count)

    day_dates = [(oldest + timedelta(days=i)) for i in range(days)]
    history_by_route: dict[str, list[tuple[date, str, str, int]]] = {}
    for route in routes:
        if not route.enabled:
            results = [(d, "unknown", "no_coverage", 0) for d in day_dates]
            results.append((today, "unknown", "no_coverage", 0))
            history_by_route[route.id] = results
            continue

        rows_by_date = by_route.get(route.id, {})
        results = [
            (
                d,
                *rows_by_date.get(d, ("unknown", "no_coverage", 0)),
            )
            for d in day_dates
        ]
        rr = route.route_result
        if rr is not None:
            results.append((today, rr.quality, rr.state, rr.matched_count))
        else:
            results.append((today, "unknown", "no_coverage", 0))
        history_by_route[route.id] = results

    return history_by_route
