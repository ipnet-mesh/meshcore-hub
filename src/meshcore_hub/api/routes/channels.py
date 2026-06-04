"""Channel API routes."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from meshcore_hub.api.auth import RequireAdmin, RequireRead
from meshcore_hub.api.channel_visibility import (
    VISIBILITY_LEVELS,
    get_max_visibility_level,
    resolve_user_role,
)
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models.channel import Channel
from meshcore_hub.common.schemas.channels import (
    ChannelCreate,
    ChannelList,
    ChannelRead,
    ChannelUpdate,
)

router = APIRouter()


def _channel_to_read(channel: Channel, include_key: bool = False) -> ChannelRead:
    """Convert a Channel model to ChannelRead schema."""

    return ChannelRead(
        id=channel.id,
        name=channel.name,
        channel_hash=channel.channel_hash,
        visibility=channel.visibility,
        enabled=channel.enabled,
        masked_key=channel.masked_key,
        key_hex=channel.key_hex if include_key else None,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


@router.get("", response_model=ChannelList)
async def list_channels(
    _: RequireRead,
    session: DbSession,
    request: Request,
) -> ChannelList:
    """List channels, filtered by user role visibility.

    When no OIDC roles are present (OIDC disabled or not logged in),
    returns only public channels.
    """
    role = resolve_user_role(request)

    query = select(Channel).order_by(Channel.name)
    channels = session.execute(query).scalars().all()

    max_level = get_max_visibility_level(role)
    filtered = []
    for ch in channels:
        level = VISIBILITY_LEVELS.get(ch.visibility, 0)
        if level <= max_level:
            filtered.append(_channel_to_read(ch, include_key=True))

    return ChannelList(items=filtered, total=len(filtered))


@router.post("", response_model=ChannelRead, status_code=201)
async def create_channel(
    __: RequireAdmin,
    session: DbSession,
    body: ChannelCreate,
) -> ChannelRead:
    """Create a new channel (admin only)."""
    existing = session.execute(
        select(Channel).where(Channel.name == body.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Channel '{body.name}' already exists"
        )

    existing_key = session.execute(
        select(Channel).where(Channel.key_hex == body.key_hex)
    ).scalar_one_or_none()
    if existing_key:
        raise HTTPException(
            status_code=409, detail="Key already in use by another channel"
        )

    channel_hash = Channel.compute_channel_hash(body.key_hex)

    channel = Channel(
        name=body.name,
        key_hex=body.key_hex,
        channel_hash=channel_hash,
        visibility=body.visibility,
        enabled=body.enabled,
    )
    session.add(channel)
    session.commit()
    session.refresh(channel)

    return _channel_to_read(channel, include_key=True)


@router.put("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    __: RequireAdmin,
    session: DbSession,
    channel_id: str,
    body: ChannelUpdate,
) -> ChannelRead:
    """Update a channel (admin only, name is immutable)."""
    channel = session.execute(
        select(Channel).where(Channel.id == channel_id)
    ).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if body.key_hex is not None:
        existing_key = session.execute(
            select(Channel).where(
                Channel.key_hex == body.key_hex, Channel.id != channel_id
            )
        ).scalar_one_or_none()
        if existing_key:
            raise HTTPException(
                status_code=409, detail="Key already in use by another channel"
            )
        channel.key_hex = body.key_hex
        channel.channel_hash = Channel.compute_channel_hash(body.key_hex)

    if body.visibility is not None:
        channel.visibility = body.visibility

    if body.enabled is not None:
        channel.enabled = body.enabled

    session.commit()
    session.refresh(channel)

    return _channel_to_read(channel, include_key=True)


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    __: RequireAdmin,
    session: DbSession,
    channel_id: str,
) -> None:
    """Delete a channel (admin only)."""
    channel = session.execute(
        select(Channel).where(Channel.id == channel_id)
    ).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    session.delete(channel)
    session.commit()
