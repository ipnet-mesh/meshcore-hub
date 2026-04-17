"""Message API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import EventObserver, Message, Node, NodeTag
from meshcore_hub.common.schemas.messages import MessageList, MessageRead, ObserverInfo

router = APIRouter()


def _get_tag_name(node: Optional[Node]) -> Optional[str]:
    """Extract name tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "name":
            return tag.value
    return None


def _fetch_observers_for_events(
    session: DbSession,
    event_type: str,
    event_hashes: list[str],
) -> dict[str, list[ObserverInfo]]:
    """Fetch receiver info for a list of events by their hashes.

    Args:
        session: Database session
        event_type: Type of event ('message', 'advertisement', etc.)
        event_hashes: List of event hashes to fetch observers for

    Returns:
        Dict mapping event_hash to list of ObserverInfo objects
    """
    if not event_hashes:
        return {}

    # Query event_observers with receiver node info
    query = (
        select(
            EventObserver.event_hash,
            EventObserver.snr,
            EventObserver.observed_at,
            Node.id.label("node_id"),
            Node.public_key,
            Node.name,
        )
        .join(Node, EventObserver.observer_node_id == Node.id)
        .where(EventObserver.event_type == event_type)
        .where(EventObserver.event_hash.in_(event_hashes))
        .order_by(EventObserver.observed_at)
    )

    results = session.execute(query).all()

    # Group by event_hash
    observers_by_hash: dict[str, list[ObserverInfo]] = {}

    # Get tag names for receiver nodes
    node_ids = [r.node_id for r in results]
    tag_names: dict[str, str] = {}
    if node_ids:
        tag_query = (
            select(NodeTag.node_id, NodeTag.value)
            .where(NodeTag.node_id.in_(node_ids))
            .where(NodeTag.key == "name")
        )
        for node_id, value in session.execute(tag_query).all():
            tag_names[node_id] = value

    for row in results:
        if row.event_hash not in observers_by_hash:
            observers_by_hash[row.event_hash] = []

        observers_by_hash[row.event_hash].append(
            ObserverInfo(
                node_id=row.node_id,
                public_key=row.public_key,
                name=row.name,
                tag_name=tag_names.get(row.node_id),
                snr=row.snr,
                observed_at=row.observed_at,
            )
        )

    return observers_by_hash


@router.get("", response_model=MessageList)
async def list_messages(
    _: RequireRead,
    session: DbSession,
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    pubkey_prefix: Optional[str] = Query(None, description="Filter by sender prefix"),
    channel_idx: Optional[int] = Query(None, description="Filter by channel"),
    observed_by: Optional[str] = Query(
        None, description="Filter by receiver node public key"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    search: Optional[str] = Query(None, description="Search in message text"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> MessageList:
    """List messages with filtering and pagination."""
    # Alias for receiver node join
    ObserverNode = aliased(Node)

    # Build query with receiver node join
    query = select(
        Message,
        ObserverNode.public_key.label("observer_pk"),
        ObserverNode.name.label("observer_name"),
        ObserverNode.id.label("receiver_id"),
    ).outerjoin(ObserverNode, Message.observer_node_id == ObserverNode.id)

    if message_type:
        query = query.where(Message.message_type == message_type)

    if pubkey_prefix:
        query = query.where(Message.pubkey_prefix == pubkey_prefix)

    if channel_idx is not None:
        query = query.where(Message.channel_idx == channel_idx)

    if observed_by:
        query = query.where(ObserverNode.public_key == observed_by)

    if since:
        query = query.where(Message.received_at >= since)

    if until:
        query = query.where(Message.received_at <= until)

    if search:
        query = query.where(Message.text.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Apply pagination
    query = query.order_by(Message.received_at.desc()).offset(offset).limit(limit)

    # Execute
    results = session.execute(query).all()

    # Look up sender names and tag names for senders with pubkey_prefix
    pubkey_prefixes = [r[0].pubkey_prefix for r in results if r[0].pubkey_prefix]
    sender_names: dict[str, str] = {}
    sender_tag_names: dict[str, str] = {}
    if pubkey_prefixes:
        # Find nodes whose public_key starts with any of these prefixes
        for prefix in set(pubkey_prefixes):
            # Get node name
            node_query = select(Node.public_key, Node.name).where(
                Node.public_key.startswith(prefix)
            )
            for public_key, name in session.execute(node_query).all():
                if name:
                    sender_names[public_key[:12]] = name

            # Get name tag
            tag_name_query = (
                select(Node.public_key, NodeTag.value)
                .join(NodeTag, Node.id == NodeTag.node_id)
                .where(Node.public_key.startswith(prefix))
                .where(NodeTag.key == "name")
            )
            for public_key, value in session.execute(tag_name_query).all():
                sender_tag_names[public_key[:12]] = value

    # Collect receiver node IDs to fetch tags
    observer_ids = set()
    for row in results:
        if row.receiver_id:
            observer_ids.add(row.receiver_id)

    # Fetch receiver nodes with tags
    observers_by_id: dict[str, Node] = {}
    if observer_ids:
        observers_query = (
            select(Node)
            .where(Node.id.in_(observer_ids))
            .options(selectinload(Node.tags))
        )
        observers = session.execute(observers_query).scalars().all()
        observers_by_id = {n.id: n for n in observers}

    # Fetch all observers for these messages
    event_hashes = [r[0].event_hash for r in results if r[0].event_hash]
    observers_by_hash = _fetch_observers_for_events(session, "message", event_hashes)

    # Build response with sender info and observed_by
    items = []
    for row in results:
        m = row[0]
        observer_pk = row.observer_pk
        observer_name = row.observer_name
        observer_node = (
            observers_by_id.get(row.receiver_id) if row.receiver_id else None
        )

        msg_dict = {
            "id": m.id,
            "observer_node_id": m.observer_node_id,
            "observed_by": observer_pk,
            "observer_name": observer_name,
            "observer_tag_name": _get_tag_name(observer_node),
            "message_type": m.message_type,
            "pubkey_prefix": m.pubkey_prefix,
            "sender_name": (
                sender_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
            ),
            "sender_tag_name": (
                sender_tag_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
            ),
            "channel_idx": m.channel_idx,
            "text": m.text,
            "path_len": m.path_len,
            "txt_type": m.txt_type,
            "signature": m.signature,
            "snr": m.snr,
            "sender_timestamp": m.sender_timestamp,
            "received_at": m.received_at,
            "created_at": m.created_at,
            "observers": (
                observers_by_hash.get(m.event_hash, []) if m.event_hash else []
            ),
        }
        items.append(MessageRead(**msg_dict))

    return MessageList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(
    _: RequireRead,
    session: DbSession,
    message_id: str,
) -> MessageRead:
    """Get a single message by ID."""
    ObserverNode = aliased(Node)
    query = (
        select(Message, ObserverNode.public_key.label("observer_pk"))
        .outerjoin(ObserverNode, Message.observer_node_id == ObserverNode.id)
        .where(Message.id == message_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Message not found")

    message, observer_pk = result

    # Fetch observers for this message
    observers = []
    if message.event_hash:
        observers_by_hash = _fetch_observers_for_events(
            session, "message", [message.event_hash]
        )
        observers = observers_by_hash.get(message.event_hash, [])

    data = {
        "id": message.id,
        "observer_node_id": message.observer_node_id,
        "observed_by": observer_pk,
        "message_type": message.message_type,
        "pubkey_prefix": message.pubkey_prefix,
        "channel_idx": message.channel_idx,
        "text": message.text,
        "path_len": message.path_len,
        "txt_type": message.txt_type,
        "signature": message.signature,
        "snr": message.snr,
        "sender_timestamp": message.sender_timestamp,
        "received_at": message.received_at,
        "created_at": message.created_at,
        "observers": observers,
    }
    return MessageRead(**data)
