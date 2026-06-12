"""Pydantic schemas for raw packet API endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RawPacketRead(BaseModel):
    """Schema for reading a raw packet.

    When ``redacted`` is true the packet was observed on a channel above the
    requesting role's visibility level: ``raw_hex`` and ``decoded`` are nulled
    out and only non-sensitive metadata is retained.
    """

    id: str = Field(..., description="Raw packet UUID")
    observed_by: Optional[str] = Field(
        default=None, description="Observing interface node public key"
    )
    observer_name: Optional[str] = Field(default=None, description="Observer node name")
    observer_tag_name: Optional[str] = Field(
        default=None, description="Observer name from tags"
    )
    packet_hash: Optional[str] = Field(
        default=None, description="LetsMesh packet hash (links to structured records)"
    )
    raw_hex: Optional[str] = Field(
        default=None, description="On-air packet bytes as hex (null when redacted)"
    )
    packet_type: Optional[int] = Field(default=None, description="Wire packet type")
    payload_type: Optional[int] = Field(
        default=None, description="Decoder payload type"
    )
    event_type: Optional[str] = Field(
        default=None, description="How the collector classified the packet"
    )
    channel_idx: Optional[int] = Field(
        default=None, description="Channel index for channel-message packets"
    )
    source_pubkey_prefix: Optional[str] = Field(
        default=None, description="Sender public key prefix"
    )
    route_type: Optional[str] = Field(default=None, description="Route type")
    path_len: Optional[int] = Field(default=None, description="Hop count")
    snr: Optional[float] = Field(default=None, description="Signal-to-noise ratio")
    decoded: Optional[dict[str, Any]] = Field(
        default=None, description="Decoder summary (null when redacted)"
    )
    redacted: bool = Field(
        default=False,
        description="True when the payload was redacted for channel visibility",
    )
    received_at: datetime = Field(..., description="When received")
    created_at: datetime = Field(..., description="Record creation timestamp")

    class Config:
        from_attributes = True


class RawPacketList(BaseModel):
    """Schema for paginated raw packet list response."""

    items: list[RawPacketRead] = Field(..., description="List of raw packets")
    total: int = Field(..., description="Total number of raw packets")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")
