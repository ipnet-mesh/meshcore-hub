"""Pydantic schemas for member API endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemberNodeCreate(BaseModel):
    """Schema for creating a member node association."""

    public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
        description="Node's public key (64-char hex)",
    )
    node_role: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Role of the node (e.g., 'chat', 'repeater')",
    )


class MemberNodeRead(BaseModel):
    """Schema for reading a member node association."""

    public_key: str = Field(..., description="Node's public key")
    node_role: Optional[str] = Field(default=None, description="Role of the node")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    # Node details (populated from nodes table if available)
    node_name: Optional[str] = Field(default=None, description="Node's name from DB")
    node_adv_type: Optional[str] = Field(
        default=None, description="Node's advertisement type"
    )
    friendly_name: Optional[str] = Field(
        default=None, description="Node's friendly name tag"
    )

    class Config:
        from_attributes = True


class MemberCreate(BaseModel):
    """Schema for creating a member."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Member's display name",
    )
    callsign: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Amateur radio callsign",
    )
    role: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Member's role in the network",
    )
    description: Optional[str] = Field(
        default=None,
        description="Additional description",
    )
    contact: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Contact information",
    )
    nodes: Optional[list[MemberNodeCreate]] = Field(
        default=None,
        description="List of associated nodes",
    )


class MemberUpdate(BaseModel):
    """Schema for updating a member."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Member's display name",
    )
    callsign: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Amateur radio callsign",
    )
    role: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Member's role in the network",
    )
    description: Optional[str] = Field(
        default=None,
        description="Additional description",
    )
    contact: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Contact information",
    )
    nodes: Optional[list[MemberNodeCreate]] = Field(
        default=None,
        description="List of associated nodes (replaces existing nodes)",
    )


class MemberRead(BaseModel):
    """Schema for reading a member."""

    id: str = Field(..., description="Member UUID")
    name: str = Field(..., description="Member's display name")
    callsign: Optional[str] = Field(default=None, description="Amateur radio callsign")
    role: Optional[str] = Field(default=None, description="Member's role")
    description: Optional[str] = Field(default=None, description="Description")
    contact: Optional[str] = Field(default=None, description="Contact information")
    nodes: list[MemberNodeRead] = Field(default=[], description="Associated nodes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class MemberList(BaseModel):
    """Schema for paginated member list response."""

    items: list[MemberRead] = Field(..., description="List of members")
    total: int = Field(..., description="Total number of members")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")
