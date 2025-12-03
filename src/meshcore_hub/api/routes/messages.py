"""Message API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Message, Node, NodeTag
from meshcore_hub.common.schemas.messages import MessageList, MessageRead

router = APIRouter()


@router.get("", response_model=MessageList)
async def list_messages(
    _: RequireRead,
    session: DbSession,
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    pubkey_prefix: Optional[str] = Query(None, description="Filter by sender prefix"),
    channel_idx: Optional[int] = Query(None, description="Filter by channel"),
    since: Optional[datetime] = Query(None, description="Start timestamp"),
    until: Optional[datetime] = Query(None, description="End timestamp"),
    search: Optional[str] = Query(None, description="Search in message text"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> MessageList:
    """List messages with filtering and pagination."""
    # Build query
    query = select(Message)

    if message_type:
        query = query.where(Message.message_type == message_type)

    if pubkey_prefix:
        query = query.where(Message.pubkey_prefix == pubkey_prefix)

    if channel_idx is not None:
        query = query.where(Message.channel_idx == channel_idx)

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
    messages = session.execute(query).scalars().all()

    # Look up friendly_names for senders with pubkey_prefix
    pubkey_prefixes = [m.pubkey_prefix for m in messages if m.pubkey_prefix]
    friendly_names: dict[str, str] = {}
    if pubkey_prefixes:
        # Find nodes whose public_key starts with any of these prefixes
        for prefix in set(pubkey_prefixes):
            friendly_name_query = (
                select(Node.public_key, NodeTag.value)
                .join(NodeTag, Node.id == NodeTag.node_id)
                .where(Node.public_key.startswith(prefix))
                .where(NodeTag.key == "friendly_name")
            )
            for public_key, value in session.execute(friendly_name_query).all():
                # Map the prefix to the friendly_name
                friendly_names[public_key[:12]] = value

    # Build response with friendly_names
    items = []
    for m in messages:
        msg_dict = {
            "id": m.id,
            "receiver_node_id": m.receiver_node_id,
            "message_type": m.message_type,
            "pubkey_prefix": m.pubkey_prefix,
            "sender_friendly_name": (
                friendly_names.get(m.pubkey_prefix) if m.pubkey_prefix else None
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
    query = select(Message).where(Message.id == message_id)
    message = session.execute(query).scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    return MessageRead.model_validate(message)
