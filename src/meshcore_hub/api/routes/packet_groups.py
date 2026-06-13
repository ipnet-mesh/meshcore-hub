"""Grouped raw packet routes — one entry per unique packet_hash."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.api.channel_visibility import (
    get_max_visibility_level,
    get_visible_channel_indices,
    resolve_user_role,
)
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node, RawPacket
from meshcore_hub.common.schemas.raw_packets import (
    GroupedPacketList,
    GroupedPacketRead,
    PacketReceptionInfo,
)

router = APIRouter()

SEARCH_DEFAULT_WINDOW_DAYS = 7
VALID_SORT_COLUMNS = {"time", "event_type", "reception_count"}


def _group_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"packet_groups:role={role}:{sorted_query_string(request)}"


def _extract_path_hashes(decoded: dict[str, Any] | None) -> list[str] | None:
    """Extract the routing path (per-hop node hash bytes) from a decoded packet.

    The path lives at the top level as ``decoded.path`` for normal packets
    (flood/advertisement/etc.). Trace-style packets instead carry it at
    ``decoded.payload.decoded.pathHashes``, so that is used as a fallback.
    """
    if not decoded:
        return None
    path = decoded.get("path")
    if isinstance(path, list) and path:
        return path
    payload = decoded.get("payload") or {}
    inner = payload.get("decoded") or {}
    hashes = inner.get("pathHashes")
    return hashes if isinstance(hashes, list) else None


def _get_tag_name(node: Optional[Node]) -> Optional[str]:
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "name":
            return tag.value
    return None


@router.get("", response_model=GroupedPacketList)
@cached("packet_groups", key_builder=_group_key_builder)
def list_packet_groups(
    _: RequireRead,
    session: DbSession,
    request: Request,
    search: Optional[str] = Query(
        None, description="Search in packet hash or observer name"
    ),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    channel_idx: Optional[int] = Query(None, description="Filter by channel index"),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    sort: Optional[str] = Query(
        None, description="Sort column: time, event_type, reception_count"
    ),
    order: Optional[str] = Query(None, description="asc or desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> GroupedPacketList:
    """List deduplicated packet groups — one row per unique packet_hash.

    Rows with no packet_hash are excluded (they cannot be meaningfully grouped).
    The 7-day default window applies unless ``since`` is provided.
    """
    sort = sort if sort in VALID_SORT_COLUMNS else "time"
    order = order if order in ("asc", "desc") else "desc"

    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

    # Default time window — keeps GROUP BY bounded when no explicit since/until.
    if since is None:
        if search:
            since = datetime.now(timezone.utc) - timedelta(
                days=SEARCH_DEFAULT_WINDOW_DAYS
            )
        else:
            since = datetime.now(timezone.utc) - timedelta(
                days=SEARCH_DEFAULT_WINDOW_DAYS
            )

    ObserverNode = aliased(Node)

    # ── Phase 1: GROUP BY packet_hash to paginate over distinct groups ────────
    group_query = (
        select(
            RawPacket.packet_hash,
            func.count(RawPacket.id).label("reception_count"),
            func.count(RawPacket.observer_node_id.distinct()).label("observer_count"),
            func.min(RawPacket.received_at).label("first_seen"),
        )
        .outerjoin(ObserverNode, RawPacket.observer_node_id == ObserverNode.id)
        .where(RawPacket.packet_hash.is_not(None))
        .where(RawPacket.received_at >= since)
    )

    if search:
        pattern = f"%{search}%"
        group_query = group_query.where(
            or_(
                RawPacket.packet_hash.ilike(pattern),
                ObserverNode.name.ilike(pattern),
            )
        )

    if event_type:
        group_query = group_query.where(RawPacket.event_type == event_type)

    if channel_idx is not None:
        group_query = group_query.where(RawPacket.channel_idx == channel_idx)

    if until:
        group_query = group_query.where(RawPacket.received_at <= until)

    group_query = group_query.group_by(RawPacket.packet_hash)

    count_query = select(func.count()).select_from(group_query.subquery())
    total = session.execute(count_query).scalar() or 0

    sort_exprs: dict[str, Any] = {
        "time": func.min(RawPacket.received_at),
        "event_type": func.min(RawPacket.event_type),
        "reception_count": func.count(RawPacket.id),
    }
    sort_col = sort_exprs[sort]
    group_query = group_query.order_by(
        desc(sort_col) if order == "desc" else asc(sort_col)
    )
    group_query = group_query.offset(offset).limit(limit)

    group_rows = session.execute(group_query).all()
    hashes = [r.packet_hash for r in group_rows]

    if not hashes:
        return GroupedPacketList(items=[], total=total, limit=limit, offset=offset)

    # ── Phase 2: Lightweight metadata fetch — no raw_hex, no decoded ──────────
    meta_query = (
        select(
            RawPacket.id,
            RawPacket.packet_hash,
            RawPacket.event_type,
            RawPacket.channel_idx,
            RawPacket.packet_type,
            RawPacket.payload_type,
            RawPacket.route_type,
            RawPacket.source_pubkey_prefix,
            RawPacket.received_at,
        )
        .where(RawPacket.packet_hash.in_(hashes))
        .order_by(RawPacket.received_at.asc())
    )

    meta_rows = session.execute(meta_query).all()

    # Pick first (oldest) row per hash as the representative display row
    representative: dict[str, Any] = {}
    for row in meta_rows:
        if row.packet_hash not in representative:
            representative[row.packet_hash] = row

    group_counts = {r.packet_hash: r for r in group_rows}

    items = []
    for h in hashes:
        rep = representative.get(h)
        grp = group_counts[h]
        is_redacted = bool(
            rep is not None
            and rep.channel_idx is not None
            and rep.channel_idx not in visible_indices
        )
        items.append(
            GroupedPacketRead(
                packet_hash=h,
                event_type=rep.event_type if rep else None,
                channel_idx=rep.channel_idx if rep else None,
                packet_type=rep.packet_type if rep else None,
                payload_type=rep.payload_type if rep else None,
                route_type=rep.route_type if rep else None,
                source_pubkey_prefix=(
                    None if is_redacted else (rep.source_pubkey_prefix if rep else None)
                ),
                reception_count=grp.reception_count,
                observer_count=grp.observer_count,
                receptions=[],
                first_seen=grp.first_seen,
                redacted=is_redacted,
                raw_hex=None,
                decoded=None,
            )
        )

    return GroupedPacketList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{packet_hash}", response_model=GroupedPacketRead)
def get_packet_group(
    _: RequireRead,
    session: DbSession,
    request: Request,
    packet_hash: str,
) -> GroupedPacketRead:
    """Full detail for a packet group, including all (observer, path) receptions."""
    ObserverNode = aliased(Node)

    rows = session.execute(
        select(
            RawPacket,
            ObserverNode.public_key.label("observer_pk"),
            ObserverNode.name.label("observer_name"),
            ObserverNode.id.label("observer_id"),
        )
        .outerjoin(ObserverNode, RawPacket.observer_node_id == ObserverNode.id)
        .where(RawPacket.packet_hash == packet_hash)
        .order_by(RawPacket.received_at.asc())
    ).all()

    if not rows:
        raise HTTPException(status_code=404, detail="Packet group not found")

    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

    observer_ids = {row.observer_id for row in rows if row.observer_id}
    nodes_by_id: dict[str, Node] = {}
    if observer_ids:
        nodes = (
            session.execute(
                select(Node)
                .where(Node.id.in_(observer_ids))
                .options(selectinload(Node.tags))
            )
            .scalars()
            .all()
        )
        nodes_by_id = {n.id: n for n in nodes}

    receptions: list[PacketReceptionInfo] = []
    for row in rows:
        packet = row[0]
        is_redacted = (
            packet.channel_idx is not None and packet.channel_idx not in visible_indices
        )
        observer_node = nodes_by_id.get(row.observer_id) if row.observer_id else None
        receptions.append(
            PacketReceptionInfo(
                packet_id=packet.id,
                observed_by=row.observer_pk,
                observer_name=row.observer_name,
                observer_tag_name=_get_tag_name(observer_node),
                snr=packet.snr,
                path_len=packet.path_len,
                path_hashes=(
                    None if is_redacted else _extract_path_hashes(packet.decoded)
                ),
                received_at=packet.received_at,
                redacted=is_redacted,
            )
        )

    first_packet = rows[0][0]
    all_redacted = all(r.redacted for r in receptions)
    unique_observers = len({r.observed_by for r in receptions if r.observed_by})

    # Use first non-redacted row for the shared raw_hex/decoded panel
    rep_packet = None
    for row in rows:
        p = row[0]
        if p.channel_idx is None or p.channel_idx in visible_indices:
            rep_packet = p
            break

    return GroupedPacketRead(
        packet_hash=packet_hash,
        event_type=first_packet.event_type,
        channel_idx=first_packet.channel_idx,
        packet_type=first_packet.packet_type,
        payload_type=first_packet.payload_type,
        route_type=first_packet.route_type,
        source_pubkey_prefix=(
            None if all_redacted else first_packet.source_pubkey_prefix
        ),
        reception_count=len(receptions),
        observer_count=unique_observers,
        receptions=receptions,
        first_seen=first_packet.received_at,
        redacted=all_redacted,
        raw_hex=rep_packet.raw_hex if rep_packet else None,
        decoded=rep_packet.decoded if rep_packet else None,
    )
