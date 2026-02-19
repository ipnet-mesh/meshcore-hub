"""Prometheus metrics endpoint for MeshCore Hub API."""

import base64
import logging
import time
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from sqlalchemy import func, select

from meshcore_hub.common.models import (
    Advertisement,
    EventLog,
    Member,
    Message,
    Node,
    NodeTag,
    Telemetry,
    TracePath,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level cache
_cache: dict[str, Any] = {"output": b"", "expires_at": 0.0}


def verify_basic_auth(request: Request) -> bool:
    """Verify HTTP Basic Auth credentials for metrics endpoint.

    Uses username 'metrics' and the API read key as password.
    Returns True if no read key is configured (public access).

    Args:
        request: FastAPI request

    Returns:
        True if authentication passes
    """
    read_key = getattr(request.app.state, "read_key", None)

    # No read key configured = public access
    if not read_key:
        return True

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
        return username == "metrics" and password == read_key
    except Exception:
        return False


def collect_metrics(session: Any) -> bytes:
    """Collect all metrics from the database and generate Prometheus output.

    Creates a fresh CollectorRegistry per call to avoid global state issues.

    Args:
        session: SQLAlchemy database session

    Returns:
        Prometheus text exposition format as bytes
    """
    from meshcore_hub import __version__

    registry = CollectorRegistry()

    # -- Info gauge --
    info_gauge = Gauge(
        "meshcore_info",
        "MeshCore Hub application info",
        ["version"],
        registry=registry,
    )
    info_gauge.labels(version=__version__).set(1)

    # -- Nodes total --
    nodes_total = Gauge(
        "meshcore_nodes_total",
        "Total number of nodes",
        registry=registry,
    )
    count = session.execute(select(func.count(Node.id))).scalar() or 0
    nodes_total.set(count)

    # -- Nodes active by time window --
    nodes_active = Gauge(
        "meshcore_nodes_active",
        "Number of active nodes in time window",
        ["window"],
        registry=registry,
    )
    for window, hours in [("1h", 1), ("24h", 24), ("7d", 168), ("30d", 720)]:
        cutoff = time.time() - (hours * 3600)
        from datetime import datetime, timezone

        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        count = (
            session.execute(
                select(func.count(Node.id)).where(Node.last_seen >= cutoff_dt)
            ).scalar()
            or 0
        )
        nodes_active.labels(window=window).set(count)

    # -- Nodes by type --
    nodes_by_type = Gauge(
        "meshcore_nodes_by_type",
        "Number of nodes by advertisement type",
        ["adv_type"],
        registry=registry,
    )
    type_counts = session.execute(
        select(Node.adv_type, func.count(Node.id)).group_by(Node.adv_type)
    ).all()
    for adv_type, count in type_counts:
        nodes_by_type.labels(adv_type=adv_type or "unknown").set(count)

    # -- Nodes with location --
    nodes_with_location = Gauge(
        "meshcore_nodes_with_location",
        "Number of nodes with GPS coordinates",
        registry=registry,
    )
    count = (
        session.execute(
            select(func.count(Node.id)).where(
                Node.lat.isnot(None), Node.lon.isnot(None)
            )
        ).scalar()
        or 0
    )
    nodes_with_location.set(count)

    # -- Node last seen timestamp --
    node_last_seen = Gauge(
        "meshcore_node_last_seen_timestamp_seconds",
        "Unix timestamp of when the node was last seen",
        ["public_key", "node_name", "adv_type", "role"],
        registry=registry,
    )
    role_subq = (
        select(NodeTag.node_id, NodeTag.value.label("role"))
        .where(NodeTag.key == "role")
        .subquery()
    )
    nodes_with_last_seen = session.execute(
        select(
            Node.public_key,
            Node.name,
            Node.adv_type,
            Node.last_seen,
            role_subq.c.role,
        )
        .outerjoin(role_subq, Node.id == role_subq.c.node_id)
        .where(Node.last_seen.isnot(None))
    ).all()
    for public_key, name, adv_type, last_seen, role in nodes_with_last_seen:
        node_last_seen.labels(
            public_key=public_key,
            node_name=name or "",
            adv_type=adv_type or "unknown",
            role=role or "",
        ).set(last_seen.timestamp())

    # -- Messages total by type --
    messages_total = Gauge(
        "meshcore_messages_total",
        "Total number of messages by type",
        ["type"],
        registry=registry,
    )
    msg_type_counts = session.execute(
        select(Message.message_type, func.count(Message.id)).group_by(
            Message.message_type
        )
    ).all()
    for msg_type, count in msg_type_counts:
        messages_total.labels(type=msg_type).set(count)

    # -- Messages received by type and window --
    messages_received = Gauge(
        "meshcore_messages_received",
        "Messages received in time window by type",
        ["type", "window"],
        registry=registry,
    )
    for window, hours in [("1h", 1), ("24h", 24), ("7d", 168), ("30d", 720)]:
        cutoff = time.time() - (hours * 3600)
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        window_counts = session.execute(
            select(Message.message_type, func.count(Message.id))
            .where(Message.received_at >= cutoff_dt)
            .group_by(Message.message_type)
        ).all()
        for msg_type, count in window_counts:
            messages_received.labels(type=msg_type, window=window).set(count)

    # -- Advertisements total --
    advertisements_total = Gauge(
        "meshcore_advertisements_total",
        "Total number of advertisements",
        registry=registry,
    )
    count = session.execute(select(func.count(Advertisement.id))).scalar() or 0
    advertisements_total.set(count)

    # -- Advertisements received by window --
    advertisements_received = Gauge(
        "meshcore_advertisements_received",
        "Advertisements received in time window",
        ["window"],
        registry=registry,
    )
    for window, hours in [("1h", 1), ("24h", 24), ("7d", 168), ("30d", 720)]:
        cutoff = time.time() - (hours * 3600)
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        count = (
            session.execute(
                select(func.count(Advertisement.id)).where(
                    Advertisement.received_at >= cutoff_dt
                )
            ).scalar()
            or 0
        )
        advertisements_received.labels(window=window).set(count)

    # -- Telemetry total --
    telemetry_total = Gauge(
        "meshcore_telemetry_total",
        "Total number of telemetry records",
        registry=registry,
    )
    count = session.execute(select(func.count(Telemetry.id))).scalar() or 0
    telemetry_total.set(count)

    # -- Trace paths total --
    trace_paths_total = Gauge(
        "meshcore_trace_paths_total",
        "Total number of trace path records",
        registry=registry,
    )
    count = session.execute(select(func.count(TracePath.id))).scalar() or 0
    trace_paths_total.set(count)

    # -- Events by type --
    events_total = Gauge(
        "meshcore_events_total",
        "Total events by type from event log",
        ["event_type"],
        registry=registry,
    )
    event_counts = session.execute(
        select(EventLog.event_type, func.count(EventLog.id)).group_by(
            EventLog.event_type
        )
    ).all()
    for event_type, count in event_counts:
        events_total.labels(event_type=event_type).set(count)

    # -- Members total --
    members_total = Gauge(
        "meshcore_members_total",
        "Total number of network members",
        registry=registry,
    )
    count = session.execute(select(func.count(Member.id))).scalar() or 0
    members_total.set(count)

    output: bytes = generate_latest(registry)
    return output


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text exposition format.
    Supports HTTP Basic Auth with username 'metrics' and API read key as password.
    Results are cached with a configurable TTL to reduce database load.
    """
    # Check authentication
    if not verify_basic_auth(request):
        return PlainTextResponse(
            "Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )

    # Check cache
    cache_ttl = getattr(request.app.state, "metrics_cache_ttl", 60)
    now = time.time()

    if _cache["output"] and now < _cache["expires_at"]:
        return Response(
            content=_cache["output"],
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # Collect fresh metrics
    try:
        from meshcore_hub.api.app import get_db_manager

        db_manager = get_db_manager()
        with db_manager.session_scope() as session:
            output = collect_metrics(session)

        # Update cache
        _cache["output"] = output
        _cache["expires_at"] = now + cache_ttl

        return Response(
            content=output,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    except Exception as e:
        logger.exception("Failed to collect metrics: %s", e)
        return PlainTextResponse(
            f"# Error collecting metrics: {e}\n",
            status_code=500,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
