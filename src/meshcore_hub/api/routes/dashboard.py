"""Dashboard API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Advertisement, Message, Node, NodeTag
from meshcore_hub.common.schemas.messages import DashboardStats, RecentAdvertisement

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

    # Total messages
    total_messages = (
        session.execute(select(func.count()).select_from(Message)).scalar() or 0
    )

    # Messages today
    messages_today = (
        session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.received_at >= today_start)
        ).scalar()
        or 0
    )

    # Total advertisements
    total_advertisements = (
        session.execute(select(func.count()).select_from(Advertisement)).scalar() or 0
    )

    # Advertisements in last 24h
    advertisements_24h = (
        session.execute(
            select(func.count())
            .select_from(Advertisement)
            .where(Advertisement.received_at >= yesterday)
        ).scalar()
        or 0
    )

    # Recent advertisements (last 10)
    recent_ads = (
        session.execute(
            select(Advertisement).order_by(Advertisement.received_at.desc()).limit(10)
        )
        .scalars()
        .all()
    )

    # Get friendly_name tags for the advertised nodes
    ad_public_keys = [ad.public_key for ad in recent_ads]
    friendly_names: dict[str, str] = {}
    if ad_public_keys:
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
            name=ad.name,
            friendly_name=friendly_names.get(ad.public_key),
            adv_type=ad.adv_type,
            received_at=ad.received_at,
        )
        for ad in recent_ads
    ]

    # Channel message counts
    channel_counts_query = (
        select(Message.channel_idx, func.count())
        .where(Message.message_type == "channel")
        .where(Message.channel_idx.isnot(None))
        .group_by(Message.channel_idx)
    )
    channel_results = session.execute(channel_counts_query).all()
    channel_message_counts = {
        int(channel): int(count) for channel, count in channel_results
    }

    return DashboardStats(
        total_nodes=total_nodes,
        active_nodes=active_nodes,
        total_messages=total_messages,
        messages_today=messages_today,
        total_advertisements=total_advertisements,
        advertisements_24h=advertisements_24h,
        recent_advertisements=recent_advertisements,
        channel_message_counts=channel_message_counts,
    )


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
