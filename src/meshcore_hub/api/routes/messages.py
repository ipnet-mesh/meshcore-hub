"""Message API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased, selectinload

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
from meshcore_hub.common.models import Message, Node
from meshcore_hub.common.schemas.messages import MessageList, MessageRead

router = APIRouter()

VALID_MSG_SORT_COLUMNS = {"time", "type", "from", "message"}


def _messages_key_builder(request: Request) -> str:
    role = resolve_user_role(request) or "anonymous"
    return f"messages:role={role}:{sorted_query_string(request)}"


def _get_tag_name(node: Optional[Node]) -> Optional[str]:
    """Extract name tag from a node's tags."""
    if not node or not node.tags:
        return None
    for tag in node.tags:
        if tag.key == "name":
            return tag.value
    return None


@router.get("", response_model=MessageList)
@cached("messages", key_builder=_messages_key_builder)
def list_messages(
    _: RequireRead,
    session: DbSession,
    request: Request,
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    pubkey_prefix: Optional[str] = Query(None, description="Filter by sender prefix"),
    channel_idx: Optional[int] = Query(None, description="Filter by channel"),
    observed_by: Optional[list[str]] = Query(
        None, description="Filter by receiver node public keys"
    ),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    search: Optional[str] = Query(None, description="Search in message text"),
    sort: Optional[str] = Query(None, description="Sort column"),
    order: Optional[str] = Query(None, description="Sort direction: asc or desc"),
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
        query = query.where(ObserverNode.public_key.in_(observed_by))

    if since:
        query = query.where(Message.received_at >= since)

    if until:
        query = query.where(Message.received_at <= until)

    if search:
        query = query.where(Message.text.ilike(f"%{search}%"))

    # Apply channel visibility filtering
    role = resolve_user_role(request)
    max_level = get_max_visibility_level(role)
    visible_indices = get_visible_channel_indices(session, max_level)
    query = query.where(
        or_(
            Message.message_type != "channel",
            Message.channel_idx.is_(None),
            Message.channel_idx.in_(visible_indices),
        )
    )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.execute(count_query).scalar() or 0

    # Resolve sort column and direction
    sort = sort if sort in VALID_MSG_SORT_COLUMNS else "time"
    order = order if order in ("asc", "desc") else "desc"

    if sort == "type":
        query = query.order_by(
            Message.message_type.desc()
            if order == "desc"
            else Message.message_type.asc()
        )
    elif sort == "from":
        query = query.order_by(
            Message.pubkey_prefix.desc()
            if order == "desc"
            else Message.pubkey_prefix.asc()
        )
    elif sort == "message":
        query = query.order_by(
            Message.text.desc() if order == "desc" else Message.text.asc()
        )
    else:
        query = query.order_by(
            Message.received_at.desc() if order == "desc" else Message.received_at.asc()
        )

    # Apply pagination
    query = query.offset(offset).limit(limit)

    # Execute
    results = session.execute(query).all()

    # Look up sender names and tag names for senders with pubkey_prefix
    pubkey_prefixes = [r[0].pubkey_prefix for r in results if r[0].pubkey_prefix]
    sender_names, sender_tag_names = resolve_sender_names(session, pubkey_prefixes)

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
    observers_by_hash = fetch_observers_for_events(session, "message", event_hashes)

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
            "packet_hash": m.packet_hash,
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
def get_message(
    _: RequireRead,
    session: DbSession,
    request: Request,
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

    # Apply channel visibility filter
    if message.message_type == "channel" and message.channel_idx is not None:
        role = resolve_user_role(request)
        max_level = get_max_visibility_level(role)
        visible_indices = get_visible_channel_indices(session, max_level)
        if message.channel_idx not in visible_indices:
            raise HTTPException(status_code=404, detail="Message not found")

    # Fetch observers for this message
    observers = []
    if message.event_hash:
        observers_by_hash = fetch_observers_for_events(
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
        "packet_hash": message.packet_hash,
        "observers": observers,
    }
    return MessageRead(**data)
