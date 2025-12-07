"""Message API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import EventReceiver, Message, Node, NodeTag
from meshcore_hub.common.schemas.messages import MessageList, MessageRead, ReceiverInfo

router = APIRouter()


def _get_tag_name(node: Optional[Node]) -> Optional[str]:
    """Extract name tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "name":
            return tag.value
    return None


def _fetch_receivers_for_events(
    session: DbSession,
    event_type: str,
    event_hashes: list[str],
) -> dict[str, list[ReceiverInfo]]:
    """Fetch receiver info for a list of events by their hashes.

    Args:
        session: Database session
        event_type: Type of event ('message', 'advertisement', etc.)
        event_hashes: List of event hashes to fetch receivers for

    Returns:
        Dict mapping event_hash to list of ReceiverInfo objects
    """
    if not event_hashes:
        return {}

    # Query event_receivers with receiver node info
    query = (
        select(
            EventReceiver.event_hash,
            EventReceiver.snr,
            EventReceiver.received_at,
            Node.id.label("node_id"),
            Node.public_key,
            Node.name,
        )
        .join(Node, EventReceiver.receiver_node_id == Node.id)
        .where(EventReceiver.event_type == event_type)
        .where(EventReceiver.event_hash.in_(event_hashes))
        .order_by(EventReceiver.received_at)
    )

    results = session.execute(query).all()

    # Group by event_hash
    receivers_by_hash: dict[str, list[ReceiverInfo]] = {}

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
        if row.event_hash not in receivers_by_hash:
            receivers_by_hash[row.event_hash] = []

        receivers_by_hash[row.event_hash].append(
            ReceiverInfo(
                node_id=row.node_id,
                public_key=row.public_key,
                name=row.name,
                tag_name=tag_names.get(row.node_id),
                snr=row.snr,
                received_at=row.received_at,
            )
        )

    return receivers_by_hash


@router.get("", response_model=MessageList)
async def list_messages(
    _: RequireRead,
    session: DbSession,
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    pubkey_prefix: Optional[str] = Query(None, description="Filter by sender prefix"),
    channel_idx: Optional[int] = Query(None, description="Filter by channel"),
    received_by: Optional[str] = Query(
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
    ReceiverNode = aliased(Node)

    # Build query with receiver node join
    query = select(
        Message,
        ReceiverNode.public_key.label("receiver_pk"),
        ReceiverNode.name.label("receiver_name"),
        ReceiverNode.id.label("receiver_id"),
    ).outerjoin(ReceiverNode, Message.receiver_node_id == ReceiverNode.id)

    if message_type:
        query = query.where(Message.message_type == message_type)

    if pubkey_prefix:
        query = query.where(Message.pubkey_prefix == pubkey_prefix)

    if channel_idx is not None:
        query = query.where(Message.channel_idx == channel_idx)

    if received_by:
        query = query.where(ReceiverNode.public_key == received_by)

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
    receiver_ids = set()
    for row in results:
        if row.receiver_id:
            receiver_ids.add(row.receiver_id)

    # Fetch receiver nodes with tags
    receivers_by_id: dict[str, Node] = {}
    if receiver_ids:
        receivers_query = (
            select(Node)
            .where(Node.id.in_(receiver_ids))
            .options(selectinload(Node.tags))
        )
        receivers = session.execute(receivers_query).scalars().all()
        receivers_by_id = {n.id: n for n in receivers}

    # Fetch all receivers for these messages
    event_hashes = [r[0].event_hash for r in results if r[0].event_hash]
    receivers_by_hash = _fetch_receivers_for_events(session, "message", event_hashes)

    # Build response with sender info and received_by
    items = []
    for row in results:
        m = row[0]
        receiver_pk = row.receiver_pk
        receiver_name = row.receiver_name
        receiver_node = (
            receivers_by_id.get(row.receiver_id) if row.receiver_id else None
        )

        msg_dict = {
            "id": m.id,
            "receiver_node_id": m.receiver_node_id,
            "received_by": receiver_pk,
            "receiver_name": receiver_name,
            "receiver_tag_name": _get_tag_name(receiver_node),
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
            "receivers": (
                receivers_by_hash.get(m.event_hash, []) if m.event_hash else []
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
    ReceiverNode = aliased(Node)
    query = (
        select(Message, ReceiverNode.public_key.label("receiver_pk"))
        .outerjoin(ReceiverNode, Message.receiver_node_id == ReceiverNode.id)
        .where(Message.id == message_id)
    )
    result = session.execute(query).one_or_none()

    if not result:
        raise HTTPException(status_code=404, detail="Message not found")

    message, receiver_pk = result

    # Fetch receivers for this message
    receivers = []
    if message.event_hash:
        receivers_by_hash = _fetch_receivers_for_events(
            session, "message", [message.event_hash]
        )
        receivers = receivers_by_hash.get(message.event_hash, [])

    data = {
        "id": message.id,
        "receiver_node_id": message.receiver_node_id,
        "received_by": receiver_pk,
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
        "receivers": receivers,
    }
    return MessageRead(**data)
