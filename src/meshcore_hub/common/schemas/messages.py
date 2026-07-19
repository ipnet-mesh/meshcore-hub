"""Pydantic schemas for message API endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ObserverInfo(BaseModel):
    """Information about an observer that captured an event."""

    node_id: str = Field(..., description="Observer node UUID")
    public_key: str = Field(..., description="Observer node public key")
    name: Optional[str] = Field(default=None, description="Observer node name")
    tag_name: Optional[str] = Field(default=None, description="Observer name from tags")
    snr: Optional[float] = Field(
        default=None, description="Signal-to-noise ratio at this observer"
    )
    path_len: Optional[int] = Field(
        default=None, description="Hop count at this observer"
    )
    observed_at: datetime = Field(
        ..., description="When this observer captured the event"
    )

    class Config:
        from_attributes = True


class MessageRead(BaseModel):
    """Schema for reading a message."""

    observed_by: Optional[str] = Field(
        default=None, description="Observing interface node public key"
    )
    observer_name: Optional[str] = Field(default=None, description="Observer node name")
    observer_tag_name: Optional[str] = Field(
        default=None, description="Observer name from tags"
    )
    message_type: str = Field(..., description="Message type (contact, channel)")
    pubkey_prefix: Optional[str] = Field(
        default=None, description="Sender's public key prefix (12 chars)"
    )
    sender_name: Optional[str] = Field(
        default=None, description="Sender's advertised node name"
    )
    sender_tag_name: Optional[str] = Field(
        default=None, description="Sender's name from node tags"
    )
    channel_idx: Optional[int] = Field(default=None, description="Channel index")
    text: str = Field(..., description="Message content")
    path_len: Optional[int] = Field(default=None, description="Number of hops")
    txt_type: Optional[int] = Field(default=None, description="Message type indicator")
    signature: Optional[str] = Field(default=None, description="Message signature")
    snr: Optional[float] = Field(default=None, description="Signal-to-noise ratio")
    sender_timestamp: Optional[datetime] = Field(
        default=None, description="Sender's timestamp"
    )
    received_at: datetime = Field(..., description="When received by interface")
    created_at: datetime = Field(..., description="Record creation timestamp")
    packet_hash: Optional[str] = Field(
        default=None, description="LetsMesh wire packet hash, links to raw packets"
    )
    spam_score: Optional[float] = Field(
        default=None,
        description="Likely-spam score 0.0-1.0 (null when scoring disabled)",
    )
    observers: list[ObserverInfo] = Field(
        default_factory=list, description="All observers that captured this message"
    )

    class Config:
        from_attributes = True


class MessageList(BaseModel):
    """Schema for paginated message list response."""

    items: list[MessageRead] = Field(..., description="List of messages")
    total: int = Field(..., description="Total number of messages")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")


class MessageFilters(BaseModel):
    """Schema for message query filters."""

    type: Optional[Literal["contact", "channel"]] = Field(
        default=None,
        description="Filter by message type",
    )
    pubkey_prefix: Optional[str] = Field(
        default=None,
        description="Filter by sender public key prefix",
    )
    channel_idx: Optional[int] = Field(
        default=None,
        description="Filter by channel index",
    )
    since: Optional[datetime] = Field(
        default=None,
        description="Start timestamp filter",
    )
    until: Optional[datetime] = Field(
        default=None,
        description="End timestamp filter",
    )
    search: Optional[str] = Field(
        default=None,
        description="Search in message text",
    )
    limit: int = Field(default=50, ge=1, le=100, description="Page size limit")
    offset: int = Field(default=0, ge=0, description="Page offset")


class AdvertisementRead(BaseModel):
    """Schema for reading an advertisement."""

    observed_by: Optional[str] = Field(
        default=None, description="Receiving interface node public key"
    )
    observer_name: Optional[str] = Field(default=None, description="Observer node name")
    observer_tag_name: Optional[str] = Field(
        default=None, description="Observer name from tags"
    )
    public_key: str = Field(..., description="Advertised public key")
    name: Optional[str] = Field(default=None, description="Advertised name")
    node_name: Optional[str] = Field(
        default=None, description="Node name from nodes table"
    )
    node_tag_name: Optional[str] = Field(
        default=None, description="Node name from tags"
    )
    node_tag_description: Optional[str] = Field(
        default=None, description="Node description from tags"
    )
    adv_type: Optional[str] = Field(default=None, description="Node type")
    flags: Optional[int] = Field(default=None, description="Capability flags")
    route_type: Optional[str] = Field(
        default=None,
        description="Route type: flood, transport_flood, direct, transport_direct",
    )
    advert_timestamp: Optional[datetime] = Field(
        default=None, description="Node's own timestamp from advert payload"
    )
    received_at: datetime = Field(..., description="When received")
    created_at: datetime = Field(..., description="Record creation timestamp")
    packet_hash: Optional[str] = Field(
        default=None, description="LetsMesh wire packet hash, links to raw packets"
    )
    observers: list[ObserverInfo] = Field(
        default_factory=list,
        description="All observers that captured this advertisement",
    )

    class Config:
        from_attributes = True


class AdvertisementList(BaseModel):
    """Schema for paginated advertisement list response."""

    items: list[AdvertisementRead] = Field(..., description="List of advertisements")
    total: int = Field(..., description="Total number of advertisements")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")


class TracePathRead(BaseModel):
    """Schema for reading a trace path."""

    observed_by: Optional[str] = Field(
        default=None, description="Receiving interface node public key"
    )
    initiator_tag: int = Field(..., description="Trace identifier")
    path_len: Optional[int] = Field(default=None, description="Path length")
    flags: Optional[int] = Field(default=None, description="Trace flags")
    auth: Optional[int] = Field(default=None, description="Auth data")
    path_hashes: Optional[list[str]] = Field(
        default=None,
        description="Hex-encoded node hash identifiers (variable length, e.g. '4a' for single-byte or 'b3fa' for multibyte)",
    )
    snr_values: Optional[list[float]] = Field(
        default=None, description="SNR values per hop"
    )
    hop_count: Optional[int] = Field(default=None, description="Total hops")
    received_at: datetime = Field(..., description="When received")
    created_at: datetime = Field(..., description="Record creation timestamp")
    observers: list[ObserverInfo] = Field(
        default_factory=list,
        description="All observers that captured this trace",
    )

    class Config:
        from_attributes = True


class TracePathList(BaseModel):
    """Schema for paginated trace path list response."""

    items: list[TracePathRead] = Field(..., description="List of trace paths")
    total: int = Field(..., description="Total number of trace paths")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")


class TelemetryRead(BaseModel):
    """Schema for reading a telemetry record."""

    observed_by: Optional[str] = Field(
        default=None, description="Receiving interface node public key"
    )
    node_public_key: str = Field(..., description="Reporting node public key")
    parsed_data: Optional[dict] = Field(
        default=None, description="Decoded sensor readings"
    )
    received_at: datetime = Field(..., description="When received")
    created_at: datetime = Field(..., description="Record creation timestamp")
    observers: list[ObserverInfo] = Field(
        default_factory=list,
        description="All observers that captured this telemetry",
    )

    class Config:
        from_attributes = True


class TelemetryList(BaseModel):
    """Schema for paginated telemetry list response."""

    items: list[TelemetryRead] = Field(..., description="List of telemetry records")
    total: int = Field(..., description="Total number of records")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")


class RecentAdvertisement(BaseModel):
    """Schema for a recent advertisement summary."""

    public_key: str = Field(..., description="Node public key")
    name: Optional[str] = Field(default=None, description="Node name")
    tag_name: Optional[str] = Field(default=None, description="Name tag")
    adv_type: Optional[str] = Field(default=None, description="Node type")
    received_at: datetime = Field(..., description="When received")
    route_type: Optional[str] = Field(default=None, description="Route type")
    observers: list[ObserverInfo] = Field(
        default_factory=list,
        description="All observers that captured this advertisement",
    )
    observed_by: Optional[str] = Field(
        default=None, description="Observing interface node public key"
    )


class ChannelMessage(BaseModel):
    """Schema for a channel message summary."""

    text: str = Field(..., description="Message text")
    sender_name: Optional[str] = Field(default=None, description="Sender name")
    sender_tag_name: Optional[str] = Field(
        default=None, description="Sender name from tags"
    )
    pubkey_prefix: Optional[str] = Field(
        default=None, description="Sender public key prefix"
    )
    received_at: datetime = Field(..., description="When received")


class DashboardStats(BaseModel):
    """Schema for dashboard aggregate statistics (counts only).

    The Recent Adverts / Recent Channel Messages lists used to live here
    but were split into ``GET /dashboard/recent-activity`` so they can
    carry a shorter cache TTL than the expensive aggregate counts.
    """

    total_nodes: int = Field(..., description="Total number of nodes")
    active_nodes: int = Field(..., description="Nodes active in last 24h")
    total_messages: int = Field(..., description="Total number of messages")
    messages_today: int = Field(..., description="Messages received today")
    messages_7d: int = Field(default=0, description="Messages received in last 7 days")
    total_advertisements: int = Field(..., description="Total advertisements")
    advertisements_24h: int = Field(
        default=0, description="Advertisements received in last 24h"
    )
    advertisements_7d: int = Field(
        default=0, description="Advertisements received in last 7 days"
    )
    channel_message_counts: dict[int, int] = Field(
        default_factory=dict,
        description="Message count per channel",
    )
    total_operators: int = Field(default=0, description="Number of operator-role users")
    total_members: int = Field(
        default=0, description="Number of member-role users (excluding operators)"
    )
    total_packets: int = Field(default=0, description="Total raw packets captured")
    packets_7d: int = Field(default=0, description="Packets captured in last 7 days")


class RecentActivity(BaseModel):
    """Schema for ``GET /dashboard/recent-activity``.

    Hosts the recent-adverts / recent-channel-messages lists that used to
    be embedded in ``DashboardStats``. Cached at the default ``redis_cache_ttl``
    (30 s) so the dashboard's Recent panels stay fresh even while the
    aggregate counts are cached at the longer ``redis_cache_ttl_dashboard``.
    Channel visibility is role-scoped via the cache key builder.
    """

    recent_advertisements: list[RecentAdvertisement] = Field(
        default_factory=list, description="Last 10 advertisements"
    )
    channel_messages: dict[int, list[ChannelMessage]] = Field(
        default_factory=dict,
        description="Recent messages per channel (up to 5 each, role-visible only)",
    )


class DailyActivityPoint(BaseModel):
    """Schema for a single day's activity count."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    count: int = Field(..., description="Count for this day")


class DailyActivity(BaseModel):
    """Schema for daily advertisement activity over a period."""

    days: int = Field(..., description="Number of days in the period")
    data: list[DailyActivityPoint] = Field(
        ..., description="Daily advertisement counts"
    )


class MessageActivity(BaseModel):
    """Schema for daily message activity over a period."""

    days: int = Field(..., description="Number of days in the period")
    data: list[DailyActivityPoint] = Field(..., description="Daily message counts")


class BreakdownBucket(BaseModel):
    """Schema for a single labeled count bucket in a breakdown."""

    label: str = Field(..., description="Bucket label")
    count: int = Field(..., description="Count for this bucket")


class PacketBreakdown(BaseModel):
    """Schema for raw-packet composition over a period."""

    days: int = Field(..., description="Number of days in the period")
    by_event_type: list[BreakdownBucket] = Field(
        default_factory=list,
        description="Top event types by count (top 6 + 'other')",
    )
    by_path_width: list[BreakdownBucket] = Field(
        default_factory=list,
        description="Path-hash byte widths (1b/2b/3b), NULL excluded",
    )


class NodeCountHistory(BaseModel):
    """Schema for node count over time."""

    days: int = Field(..., description="Number of days in the period")
    data: list[DailyActivityPoint] = Field(
        ..., description="Cumulative node count per day"
    )
