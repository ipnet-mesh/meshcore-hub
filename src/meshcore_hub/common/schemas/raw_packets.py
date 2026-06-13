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


class PacketReceptionInfo(BaseModel):
    """One raw_packet row — a single (observer, path) reception."""

    packet_id: str = Field(..., description="Raw packet UUID")
    observed_by: Optional[str] = Field(default=None, description="Observer public key")
    observer_name: Optional[str] = Field(default=None, description="Observer node name")
    observer_tag_name: Optional[str] = Field(
        default=None, description="Observer name from tags"
    )
    snr: Optional[float] = Field(default=None, description="SNR at this observer")
    path_len: Optional[int] = Field(default=None, description="Hop count")
    path_hashes: Optional[list[str]] = Field(
        default=None,
        description="Hop node hash sequence from decoded.payload.decoded.pathHashes",
    )
    received_at: datetime = Field(..., description="When received")
    redacted: bool = Field(default=False)


class GroupedPacketRead(BaseModel):
    """One packet hash with aggregated reception info."""

    packet_hash: Optional[str] = Field(default=None)
    event_type: Optional[str] = Field(default=None)
    channel_idx: Optional[int] = Field(default=None)
    packet_type: Optional[int] = Field(default=None)
    payload_type: Optional[int] = Field(default=None)
    route_type: Optional[str] = Field(default=None)
    source_pubkey_prefix: Optional[str] = Field(default=None)
    reception_count: int = Field(..., description="Total rows (paths × observers)")
    observer_count: int = Field(..., description="Distinct observer nodes")
    path_hash_bytes: Optional[int] = Field(
        default=None,
        description=(
            "Widest path-hash prefix width in bytes (1/2/3) for the "
            "representative reception"
        ),
    )
    receptions: list[PacketReceptionInfo] = Field(
        default_factory=list,
        description="Individual receptions (populated for detail, empty for list)",
    )
    first_seen: datetime = Field(
        ..., description="Earliest received_at across all receptions"
    )
    redacted: bool = Field(
        default=False, description="True when all receptions are redacted"
    )
    raw_hex: Optional[str] = Field(
        default=None, description="Representative raw hex (null for list view)"
    )
    decoded: Optional[dict[str, Any]] = Field(
        default=None, description="Representative decoded JSON (null for list view)"
    )


class GroupedPacketList(BaseModel):
    """Paginated list of grouped packets."""

    items: list[GroupedPacketRead] = Field(..., description="List of packet groups")
    total: int = Field(..., description="Total distinct packet hashes matching filters")
    limit: int
    offset: int
