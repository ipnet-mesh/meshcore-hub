"""Raw packet API routes."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import String, cast, func, or_, select
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
from meshcore_hub.common.schemas.raw_packets import RawPacketList, RawPacketRead

router = APIRouter()

VALID_PACKET_SORT_COLUMNS = {"time", "event_type", "packet_type", "snr", "path_len"}
DISABLE_FILTER_VALUES = {"all", "none", ""}

# Unanchored substring search over raw_hex cannot use an index (full scan). When
# the caller supplies no explicit time window we bound the scan to this many days
# so search runs against a recent slice rather than the whole table (see TR-17).
SEARCH_DEFAULT_WINDOW_DAYS = 7


def _packets_key_builder(request: Request) -> str:
    """Role-aware cache key so redacted responses never leak across roles."""
    role = resolve_user_role(request) or "anonymous"
    return f"packets:role={role}:{sorted_query_string(request)}"


def _get_tag_name(node: Optional[Node]) -> Optional[str]:
    """Extract name tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "name":
            return tag.value
    return None


def _csv_set(value: Optional[str]) -> set[str]:
    """Split a comma-separated filter value into a normalized set."""
    if not value:
        return set()
    return {t.strip() for t in value.split(",") if t.strip()}


@router.get("", response_model=RawPacketList)
@cached("packets", key_builder=_packets_key_builder)
def list_raw_packets(
    _: RequireRead,
    session: DbSession,
    request: Request,
    search: Optional[str] = Query(
        None, description="Search in packet hash, raw hex, or observer name/key"
    ),
    event_type: Optional[str] = Query(
        None, description="Comma-separated classification filter"
    ),
    packet_type: Optional[str] = Query(
        None, description="Comma-separated wire packet type filter"
    ),
    packet_hash: Optional[str] = Query(
        None,
        description="Filter by exact wire packet hash (links from adverts/messages)",
    ),
    channel_idx: Optional[int] = Query(None, description="Filter by channel index"),
    route_type: Optional[str] = Query(
        None,
        description="Comma-separated route types. Use 'all'/'none' to disable.",
    ),
    public_key: Optional[str] = Query(
        None, description="Filter by source public key prefix"
    ),
    pubkey_prefix: Optional[str] = Query(
        None, description="Filter by source public key prefix"
    ),
    observed_by: Optional[list[str]] = Query(
        None, description="Filter by receiver node public keys"
    ),
    decryptable: Optional[bool] = Query(
        None, description="Only packets whose payload decrypted (or the inverse)"
    ),
    min_snr: Optional[float] = Query(None, description="Minimum SNR"),
    max_snr: Optional[float] = Query(None, description="Maximum SNR"),
    min_path_len: Optional[int] = Query(None, description="Minimum hop count"),
    max_path_len: Optional[int] = Query(None, description="Maximum hop count"),
    redacted: Optional[bool] = Query(
        None, description="Include only / exclude redacted (metadata-only) rows"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    sort: Optional[str] = Query(None, description="Sort column"),
    order: Optional[str] = Query(None, description="Sort direction: asc or desc"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> RawPacketList:
    """List raw packets with filtering, redaction, and pagination."""
    ObserverNode = aliased(Node)

    query = select(
        RawPacket,
        ObserverNode.public_key.label("observer_pk"),
        ObserverNode.name.label("observer_name"),
        ObserverNode.id.label("observer_id"),
    ).outerjoin(ObserverNode, RawPacket.observer_node_id == ObserverNode.id)

    # Bound an unindexed substring search to a recent window when unconstrained.
    if search and since is None:
        since = datetime.now(timezone.utc) - timedelta(days=SEARCH_DEFAULT_WINDOW_DAYS)

    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                RawPacket.packet_hash.ilike(pattern),
                RawPacket.raw_hex.ilike(pattern),
                ObserverNode.name.ilike(pattern),
                ObserverNode.public_key.ilike(pattern),
            )
        )

    event_types = _csv_set(event_type)
    if event_types:
        query = query.where(RawPacket.event_type.in_(event_types))

    packet_types = {int(t) for t in _csv_set(packet_type) if t.lstrip("-").isdigit()}
    if packet_types:
        query = query.where(RawPacket.packet_type.in_(packet_types))

    if packet_hash:
        query = query.where(RawPacket.packet_hash == packet_hash)

    if channel_idx is not None:
        query = query.where(RawPacket.channel_idx == channel_idx)

    if route_type and route_type.strip().lower() not in DISABLE_FILTER_VALUES:
        requested = {t.lower() for t in _csv_set(route_type)}
        if requested:
            query = query.where(RawPacket.route_type.in_(requested))

    source_prefix = public_key or pubkey_prefix
    if source_prefix:
        query = query.where(RawPacket.source_pubkey_prefix == source_prefix)

    if observed_by:
        query = query.where(ObserverNode.public_key.in_(observed_by))

    if decryptable is not None:
        # Best-effort: the decoder only emits a "decrypted" object when
        # decryption succeeds. Match on the serialized JSON text.
        decoded_text = cast(RawPacket.decoded, String)
        has_decrypted = decoded_text.ilike('%"decrypted":%') & ~decoded_text.ilike(
            '%"decrypted": null%'
        )
        query = query.where(has_decrypted if decryptable else ~has_decrypted)

    if min_snr is not None:
        query = query.where(RawPacket.snr >= min_snr)
    if max_snr is not None:
        query = query.where(RawPacket.snr <= max_snr)
    if min_path_len is not None:
        query = query.where(RawPacket.path_len >= min_path_len)
    if max_path_len is not None:
        query = query.where(RawPacket.path_len <= max_path_len)

    if since:
        query = query.where(RawPacket.received_at >= since)
    if until:
        query = query.where(RawPacket.received_at <= until)

    # Channel-visibility: a row is "redacted" when it is a channel packet on a
    # channel the role cannot see. Apply the `redacted` filter at SQL level (not
    # post-fetch) so pagination counts stay stable.
    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

    is_redacted = RawPacket.channel_idx.is_not(None) & RawPacket.channel_idx.not_in(
        visible_indices
    )
    if redacted is True:
        query = query.where(is_redacted)
    elif redacted is False:
        query = query.where(~is_redacted)

    # Total count over the filtered subquery
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Sorting
    sort = sort if sort in VALID_PACKET_SORT_COLUMNS else "time"
    order = order if order in ("asc", "desc") else "desc"
    sort_column = {
        "time": RawPacket.received_at,
        "event_type": RawPacket.event_type,
        "packet_type": RawPacket.packet_type,
        "snr": RawPacket.snr,
        "path_len": RawPacket.path_len,
    }[sort]
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    query = query.offset(offset).limit(limit)
    results = session.execute(query).all()

    # Hydrate observer tags
    observer_ids = {row.observer_id for row in results if row.observer_id}
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

    items = [
        _build_read(
            row[0],
            observer_pk=row.observer_pk,
            observer_name=row.observer_name,
            observer_node=nodes_by_id.get(row.observer_id) if row.observer_id else None,
            visible_indices=visible_indices,
        )
        for row in results
    ]

    return RawPacketList(items=items, total=total, limit=limit, offset=offset)


def _build_read(
    packet: RawPacket,
    observer_pk: Optional[str],
    observer_name: Optional[str],
    observer_node: Optional[Node],
    visible_indices: set[int],
) -> RawPacketRead:
    """Build a RawPacketRead, applying channel-visibility redaction."""
    redacted = (
        packet.channel_idx is not None and packet.channel_idx not in visible_indices
    )
    return RawPacketRead(
        id=packet.id,
        observed_by=observer_pk,
        observer_name=observer_name,
        observer_tag_name=_get_tag_name(observer_node),
        packet_hash=packet.packet_hash,
        raw_hex=None if redacted else packet.raw_hex,
        packet_type=packet.packet_type,
        payload_type=packet.payload_type,
        event_type=packet.event_type,
        channel_idx=packet.channel_idx,
        source_pubkey_prefix=None if redacted else packet.source_pubkey_prefix,
        route_type=packet.route_type,
        path_len=packet.path_len,
        snr=packet.snr,
        decoded=None if redacted else packet.decoded,
        redacted=redacted,
        received_at=packet.received_at,
        created_at=packet.created_at,
    )


@router.get("/{packet_id}", response_model=RawPacketRead)
def get_raw_packet(
    _: RequireRead,
    session: DbSession,
    request: Request,
    packet_id: str,
) -> RawPacketRead:
    """Get a single raw packet by ID, subject to redaction rules."""
    ObserverNode = aliased(Node)
    result = session.execute(
        select(
            RawPacket,
            ObserverNode.public_key.label("observer_pk"),
            ObserverNode.name.label("observer_name"),
            ObserverNode.id.label("observer_id"),
        )
        .outerjoin(ObserverNode, RawPacket.observer_node_id == ObserverNode.id)
        .where(RawPacket.id == packet_id)
    ).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Raw packet not found")

    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)

    observer_node = None
    if result.observer_id:
        observer_node = (
            session.execute(
                select(Node)
                .where(Node.id == result.observer_id)
                .options(selectinload(Node.tags))
            )
            .scalars()
            .one_or_none()
        )

    return _build_read(
        result[0],
        observer_pk=result.observer_pk,
        observer_name=result.observer_name,
        observer_node=observer_node,
        visible_indices=visible_indices,
    )
