"""Pydantic schemas for MeshCore events."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AdvertisementEvent(BaseModel):
    """Schema for ADVERTISEMENT / NEW_ADVERT events."""

    public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Node's 64-character hex public key",
    )
    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Node name/alias",
    )
    adv_type: Optional[str] = Field(
        default=None,
        description="Node type: chat, repeater, room, none",
    )
    flags: Optional[int] = Field(
        default=None,
        description="Capability/status flags bitmask",
    )


class ContactMessageEvent(BaseModel):
    """Schema for CONTACT_MSG_RECV events."""

    pubkey_prefix: str = Field(
        ...,
        min_length=12,
        max_length=12,
        description="First 12 characters of sender's public key",
    )
    text: str = Field(..., description="Message content")
    path_len: Optional[int] = Field(
        default=None,
        description="Number of hops message traveled",
    )
    txt_type: Optional[int] = Field(
        default=None,
        description="Message type indicator (0=plain, 2=signed, etc.)",
    )
    signature: Optional[str] = Field(
        default=None,
        max_length=8,
        description="Message signature (8 hex chars)",
    )
    SNR: Optional[float] = Field(
        default=None,
        alias="snr",
        description="Signal-to-Noise Ratio in dB",
    )
    sender_timestamp: Optional[int] = Field(
        default=None,
        description="Unix timestamp when message was sent",
    )

    class Config:
        populate_by_name = True


class ChannelMessageEvent(BaseModel):
    """Schema for CHANNEL_MSG_RECV events."""

    channel_idx: int = Field(
        ...,
        ge=0,
        le=255,
        description="Channel number (0-255)",
    )
    text: str = Field(..., description="Message content")
    path_len: Optional[int] = Field(
        default=None,
        description="Number of hops message traveled",
    )
    txt_type: Optional[int] = Field(
        default=None,
        description="Message type indicator",
    )
    signature: Optional[str] = Field(
        default=None,
        max_length=8,
        description="Message signature (8 hex chars)",
    )
    SNR: Optional[float] = Field(
        default=None,
        alias="snr",
        description="Signal-to-Noise Ratio in dB",
    )
    sender_timestamp: Optional[int] = Field(
        default=None,
        description="Unix timestamp when message was sent",
    )

    class Config:
        populate_by_name = True


class TraceDataEvent(BaseModel):
    """Schema for TRACE_DATA events."""

    initiator_tag: int = Field(
        ...,
        description="Unique trace identifier",
    )
    path_len: Optional[int] = Field(
        default=None,
        description="Length of the path",
    )
    flags: Optional[int] = Field(
        default=None,
        description="Trace flags/options",
    )
    auth: Optional[int] = Field(
        default=None,
        description="Authentication/validation data",
    )
    path_hashes: Optional[list[str]] = Field(
        default=None,
        description="Array of 2-character node hash identifiers",
    )
    snr_values: Optional[list[float]] = Field(
        default=None,
        description="Array of SNR values per hop",
    )
    hop_count: Optional[int] = Field(
        default=None,
        description="Total number of hops",
    )


class TelemetryResponseEvent(BaseModel):
    """Schema for TELEMETRY_RESPONSE events."""

    node_public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Full public key of reporting node",
    )
    lpp_data: Optional[bytes] = Field(
        default=None,
        description="Raw LPP-encoded sensor data",
    )
    parsed_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Decoded sensor readings",
    )


class ContactInfo(BaseModel):
    """Schema for a single contact in CONTACTS event."""

    public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Node's full public key",
    )
    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Node name/alias",
    )
    node_type: Optional[str] = Field(
        default=None,
        description="Node type: chat, repeater, room, none",
    )


class ContactsEvent(BaseModel):
    """Schema for CONTACTS sync events."""

    contacts: list[ContactInfo] = Field(
        ...,
        description="Array of contact objects",
    )


class SendConfirmedEvent(BaseModel):
    """Schema for SEND_CONFIRMED events."""

    destination_public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Recipient's full public key",
    )
    round_trip_ms: int = Field(
        ...,
        description="Round-trip time in milliseconds",
    )


class StatusResponseEvent(BaseModel):
    """Schema for STATUS_RESPONSE events."""

    node_public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Node's full public key",
    )
    status: Optional[str] = Field(
        default=None,
        description="Status description",
    )
    uptime: Optional[int] = Field(
        default=None,
        description="Uptime in seconds",
    )
    message_count: Optional[int] = Field(
        default=None,
        description="Total messages processed",
    )


class BatteryEvent(BaseModel):
    """Schema for BATTERY events."""

    battery_voltage: float = Field(
        ...,
        description="Battery voltage (e.g., 3.7V)",
    )
    battery_percentage: int = Field(
        ...,
        ge=0,
        le=100,
        description="Battery level 0-100%",
    )


class PathUpdatedEvent(BaseModel):
    """Schema for PATH_UPDATED events."""

    node_public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Target node's full public key",
    )
    hop_count: int = Field(
        ...,
        description="Number of hops in new path",
    )


class WebhookPayload(BaseModel):
    """Schema for webhook payload envelope."""

    event_type: str = Field(..., description="Event type name")
    timestamp: datetime = Field(..., description="Event timestamp (ISO 8601)")
    data: dict[str, Any] = Field(..., description="Event-specific payload")
