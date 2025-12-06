"""Dashboard API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.hash_utils import (
    compute_advertisement_hash,
    compute_message_hash,
)
from meshcore_hub.common.models import Advertisement, Message, Node, NodeTag
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


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    _: RequireRead,
    session: DbSession,
) -> DashboardStats:
    """Get dashboard statistics."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)

    # Total nodes
    total_nodes = session.execute(select(func.count()).select_from(Node)).scalar() or 0

    # Active nodes (last 24h)
    active_nodes = (
        session.execute(
            select(func.count()).select_from(Node).where(Node.last_seen >= yesterday)
        ).scalar()
        or 0
    )

    # Total messages (deduplicated by content hash)
    distinct_messages = (
        select(
            Message.text,
            Message.pubkey_prefix,
            Message.channel_idx,
            Message.sender_timestamp,
            Message.txt_type,
        )
        .distinct()
        .subquery()
    )
    total_messages = (
        session.execute(select(func.count()).select_from(distinct_messages)).scalar()
        or 0
    )

    # Messages today (deduplicated)
    distinct_messages_today = (
        select(
            Message.text,
            Message.pubkey_prefix,
            Message.channel_idx,
            Message.sender_timestamp,
            Message.txt_type,
        )
        .where(Message.received_at >= today_start)
        .distinct()
        .subquery()
    )
    messages_today = (
        session.execute(
            select(func.count()).select_from(distinct_messages_today)
        ).scalar()
        or 0
    )

    # Total advertisements (deduplicated by public_key + 5min time bucket)
    distinct_advertisements = (
        select(
            Advertisement.public_key,
            Advertisement.name,
            Advertisement.adv_type,
            Advertisement.flags,
            (func.strftime("%s", Advertisement.received_at) / 300).label("time_bucket"),
        )
        .distinct()
        .subquery()
    )
    total_advertisements = (
        session.execute(
            select(func.count()).select_from(distinct_advertisements)
        ).scalar()
        or 0
    )

    # Advertisements in last 24h (deduplicated)
    distinct_advertisements_24h = (
        select(
            Advertisement.public_key,
            Advertisement.name,
            Advertisement.adv_type,
            Advertisement.flags,
            (func.strftime("%s", Advertisement.received_at) / 300).label("time_bucket"),
        )
        .where(Advertisement.received_at >= yesterday)
        .distinct()
        .subquery()
    )
    advertisements_24h = (
        session.execute(
            select(func.count()).select_from(distinct_advertisements_24h)
        ).scalar()
        or 0
    )

    # Recent advertisements (last 10, deduplicated)
    # Fetch more to ensure we have 10 unique after deduplication
    recent_ads_raw = (
        session.execute(
            select(Advertisement).order_by(Advertisement.received_at.desc()).limit(30)
        )
        .scalars()
        .all()
    )

    # Deduplicate by hash
    seen_ad_hashes: set[str] = set()
    recent_ads = []
    for ad in recent_ads_raw:
        ad_hash = compute_advertisement_hash(
            public_key=ad.public_key,
            name=ad.name,
            adv_type=ad.adv_type,
            flags=ad.flags,
            received_at=ad.received_at,
            bucket_minutes=5,
        )
        if ad_hash not in seen_ad_hashes:
            seen_ad_hashes.add(ad_hash)
            recent_ads.append(ad)
            if len(recent_ads) >= 10:
                break

    # Get node names, adv_types, and friendly_name tags for the advertised nodes
    ad_public_keys = [ad.public_key for ad in recent_ads]
    node_names: dict[str, str] = {}
    node_adv_types: dict[str, str] = {}
    friendly_names: dict[str, str] = {}
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

        # Get friendly_name tags
        friendly_name_query = (
            select(Node.public_key, NodeTag.value)
            .join(NodeTag, Node.id == NodeTag.node_id)
            .where(Node.public_key.in_(ad_public_keys))
            .where(NodeTag.key == "friendly_name")
        )
        for public_key, value in session.execute(friendly_name_query).all():
            friendly_names[public_key] = value

    recent_advertisements = [
        RecentAdvertisement(
            public_key=ad.public_key,
            name=ad.name or node_names.get(ad.public_key),
            friendly_name=friendly_names.get(ad.public_key),
            adv_type=ad.adv_type or node_adv_types.get(ad.public_key),
            received_at=ad.received_at,
        )
        for ad in recent_ads
    ]

    # Channel message counts (deduplicated)
    distinct_channel_messages = (
        select(
            Message.channel_idx,
            Message.text,
            Message.pubkey_prefix,
            Message.sender_timestamp,
            Message.txt_type,
        )
        .where(Message.message_type == "channel")
        .where(Message.channel_idx.isnot(None))
        .distinct()
        .subquery()
    )
    channel_counts_query = select(
        distinct_channel_messages.c.channel_idx, func.count()
    ).group_by(distinct_channel_messages.c.channel_idx)
    channel_results = session.execute(channel_counts_query).all()
    channel_message_counts = {
        int(channel): int(count) for channel, count in channel_results
    }

    # Get latest 5 messages for each channel that has messages (deduplicated)
    channel_messages: dict[int, list[ChannelMessage]] = {}
    for channel_idx, _ in channel_results:
        # Fetch more messages to deduplicate
        messages_query = (
            select(Message)
            .where(Message.message_type == "channel")
            .where(Message.channel_idx == channel_idx)
            .order_by(Message.received_at.desc())
            .limit(15)
        )
        channel_msgs_raw = session.execute(messages_query).scalars().all()

        # Deduplicate
        seen_msg_hashes: set[str] = set()
        channel_msgs = []
        for m in channel_msgs_raw:
            msg_hash = compute_message_hash(
                text=m.text,
                pubkey_prefix=m.pubkey_prefix,
                channel_idx=m.channel_idx,
                sender_timestamp=m.sender_timestamp,
                txt_type=m.txt_type,
            )
            if msg_hash not in seen_msg_hashes:
                seen_msg_hashes.add(msg_hash)
                channel_msgs.append(m)
                if len(channel_msgs) >= 5:
                    break

        # Look up sender names for these messages
        msg_prefixes = [m.pubkey_prefix for m in channel_msgs if m.pubkey_prefix]
        msg_sender_names: dict[str, str] = {}
        msg_friendly_names: dict[str, str] = {}
        if msg_prefixes:
            for prefix in set(msg_prefixes):
                sender_node_query = select(Node.public_key, Node.name).where(
                    Node.public_key.startswith(prefix)
                )
                for public_key, name in session.execute(sender_node_query).all():
                    if name:
                        msg_sender_names[public_key[:12]] = name

                sender_friendly_query = (
                    select(Node.public_key, NodeTag.value)
                    .join(NodeTag, Node.id == NodeTag.node_id)
                    .where(Node.public_key.startswith(prefix))
                    .where(NodeTag.key == "friendly_name")
                )
                for public_key, value in session.execute(sender_friendly_query).all():
                    msg_friendly_names[public_key[:12]] = value

        channel_messages[int(channel_idx)] = [
            ChannelMessage(
                text=m.text,
                sender_name=(
                    msg_sender_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
                ),
                sender_friendly_name=(
                    msg_friendly_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
                ),
                pubkey_prefix=m.pubkey_prefix,
                received_at=m.received_at,
            )
            for m in channel_msgs
        ]

    return DashboardStats(
        total_nodes=total_nodes,
        active_nodes=active_nodes,
        total_messages=total_messages,
        messages_today=messages_today,
        total_advertisements=total_advertisements,
        advertisements_24h=advertisements_24h,
        recent_advertisements=recent_advertisements,
        channel_message_counts=channel_message_counts,
        channel_messages=channel_messages,
    )


@router.get("/activity", response_model=DailyActivity)
async def get_activity(
    _: RequireRead,
    session: DbSession,
    days: int = 30,
) -> DailyActivity:
    """Get daily advertisement activity for the specified period.

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Daily advertisement counts for each day in the period
    """
    # Limit to max 90 days
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Query advertisement counts grouped by date
    # Use SQLite's date() function for grouping (returns string 'YYYY-MM-DD')
    date_expr = func.date(Advertisement.received_at)

    query = (
        select(
            date_expr.label("date"),
            func.count().label("count"),
        )
        .where(Advertisement.received_at >= start_date)
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
async def get_message_activity(
    _: RequireRead,
    session: DbSession,
    days: int = 30,
) -> MessageActivity:
    """Get daily message activity for the specified period.

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Daily message counts for each day in the period
    """
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Query message counts grouped by date
    date_expr = func.date(Message.received_at)

    query = (
        select(
            date_expr.label("date"),
            func.count().label("count"),
        )
        .where(Message.received_at >= start_date)
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
async def get_node_count_history(
    _: RequireRead,
    session: DbSession,
    days: int = 30,
) -> NodeCountHistory:
    """Get cumulative node count over time.

    For each day, shows the total number of nodes that existed by that date
    (based on their created_at timestamp).

    Args:
        days: Number of days to include (default 30, max 90)

    Returns:
        Cumulative node count for each day in the period
    """
    days = min(days, 90)

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Get all nodes with their creation dates
    # Count nodes created on or before each date
    data = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        date_str = date.strftime("%Y-%m-%d")

        # Count nodes created on or before this date
        count = (
            session.execute(
                select(func.count())
                .select_from(Node)
                .where(Node.created_at <= end_of_day)
            ).scalar()
            or 0
        )
        data.append(DailyActivityPoint(date=date_str, count=count))

    return NodeCountHistory(days=days, data=data)


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: DbSession,
) -> HTMLResponse:
    """Simple HTML dashboard page."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)

    # Get stats
    total_nodes = session.execute(select(func.count()).select_from(Node)).scalar() or 0

    active_nodes = (
        session.execute(
            select(func.count()).select_from(Node).where(Node.last_seen >= yesterday)
        ).scalar()
        or 0
    )

    total_messages = (
        session.execute(select(func.count()).select_from(Message)).scalar() or 0
    )

    messages_today = (
        session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.received_at >= today_start)
        ).scalar()
        or 0
    )

    # Get recent nodes
    recent_nodes = (
        session.execute(select(Node).order_by(Node.last_seen.desc()).limit(10))
        .scalars()
        .all()
    )

    # Get recent messages
    recent_messages = (
        session.execute(select(Message).order_by(Message.received_at.desc()).limit(10))
        .scalars()
        .all()
    )

    # Build HTML
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>MeshCore Hub Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        h1 {{ color: #2c3e50; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-card h3 {{ margin: 0 0 10px 0; color: #666; font-size: 14px; }}
        .stat-card .value {{ font-size: 32px; font-weight: bold; color: #2c3e50; }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .text-muted {{ color: #666; }}
        .truncate {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>MeshCore Hub Dashboard</h1>
        <p class="text-muted">Last updated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

        <div class="stats">
            <div class="stat-card">
                <h3>Total Nodes</h3>
                <div class="value">{total_nodes}</div>
            </div>
            <div class="stat-card">
                <h3>Active Nodes (24h)</h3>
                <div class="value">{active_nodes}</div>
            </div>
            <div class="stat-card">
                <h3>Total Messages</h3>
                <div class="value">{total_messages}</div>
            </div>
            <div class="stat-card">
                <h3>Messages Today</h3>
                <div class="value">{messages_today}</div>
            </div>
        </div>

        <div class="section">
            <h2>Recent Nodes</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Public Key</th>
                        <th>Type</th>
                        <th>Last Seen</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f'''
                    <tr>
                        <td>{n.name or '-'}</td>
                        <td class="truncate">{n.public_key[:16]}...</td>
                        <td>{n.adv_type or '-'}</td>
                        <td>{n.last_seen.strftime('%Y-%m-%d %H:%M') if n.last_seen else '-'}</td>
                    </tr>
                    ''' for n in recent_nodes)}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>Recent Messages</h2>
            <table>
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>From/Channel</th>
                        <th>Text</th>
                        <th>Received</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f'''
                    <tr>
                        <td>{m.message_type}</td>
                        <td>{m.pubkey_prefix or f'Ch {m.channel_idx}' or '-'}</td>
                        <td class="truncate">{m.text[:50]}{'...' if len(m.text) > 50 else ''}</td>
                        <td>{m.received_at.strftime('%Y-%m-%d %H:%M') if m.received_at else '-'}</td>
                    </tr>
                    ''' for m in recent_messages)}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html)
