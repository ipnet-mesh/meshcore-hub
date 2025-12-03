"""Message API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Message
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

    return MessageList(
        items=[MessageRead.model_validate(m) for m in messages],
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
