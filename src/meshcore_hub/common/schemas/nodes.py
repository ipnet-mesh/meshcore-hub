"""Pydantic schemas for node API endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class NodeTagCreate(BaseModel):
    """Schema for creating a node tag."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Tag name/key",
    )
    value: Optional[str] = Field(
        default=None,
        description="Tag value",
    )
    value_type: Literal["string", "number", "boolean"] = Field(
        default="string",
        description="Value type hint",
    )


class NodeTagUpdate(BaseModel):
    """Schema for updating a node tag."""

    value: Optional[str] = Field(
        default=None,
        description="Tag value",
    )
    value_type: Optional[Literal["string", "number", "boolean"]] = Field(
        default=None,
        description="Value type hint",
    )


class NodeTagMove(BaseModel):
    """Schema for moving a node tag to a different node."""

    new_public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Public key of the destination node",
    )


class NodeTagRead(BaseModel):
    """Schema for reading a node tag."""

    key: str = Field(..., description="Tag name/key")
    value: Optional[str] = Field(default=None, description="Tag value")
    value_type: str = Field(..., description="Value type hint")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class NodeRead(BaseModel):
    """Schema for reading a node."""

    public_key: str = Field(..., description="Node's 64-character hex public key")
    name: Optional[str] = Field(default=None, description="Node display name")
    adv_type: Optional[str] = Field(default=None, description="Advertisement type")
    flags: Optional[int] = Field(default=None, description="Capability flags")
    first_seen: datetime = Field(..., description="First advertisement timestamp")
    last_seen: Optional[datetime] = Field(
        default=None, description="Last activity timestamp"
    )
    lat: Optional[float] = Field(default=None, description="GPS latitude coordinate")
    lon: Optional[float] = Field(default=None, description="GPS longitude coordinate")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record update timestamp")
    tags: list[NodeTagRead] = Field(default_factory=list, description="Node tags")

    class Config:
        from_attributes = True


class NodeList(BaseModel):
    """Schema for paginated node list response."""

    items: list[NodeRead] = Field(..., description="List of nodes")
    total: int = Field(..., description="Total number of nodes")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")


class NodeFilters(BaseModel):
    """Schema for node query filters."""

    search: Optional[str] = Field(
        default=None,
        description="Search in name tag, node name, or public key",
    )
    adv_type: Optional[str] = Field(
        default=None,
        description="Filter by advertisement type",
    )
    has_tag: Optional[str] = Field(
        default=None,
        description="Filter by tag key",
    )
    limit: int = Field(default=50, ge=1, le=100, description="Page size limit")
    offset: int = Field(default=0, ge=0, description="Page offset")
