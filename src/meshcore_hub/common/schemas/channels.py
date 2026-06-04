"""Pydantic schemas for channel API endpoints."""

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ChannelCreate(BaseModel):
    """Schema for creating a channel."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Channel display name",
    )
    key_hex: str = Field(
        ...,
        min_length=32,
        max_length=64,
        description="Channel secret key as uppercase hex (32 or 64 chars)",
    )
    visibility: Literal["community", "member", "operator", "admin"] = Field(
        default="community",
        description="Channel visibility/permission level",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the channel is active",
    )

    @field_validator("key_hex")
    @classmethod
    def validate_key_hex(cls, v: str) -> str:
        """Validate key is uppercase hex and correct length."""
        v = v.strip().upper()
        if not re.fullmatch(r"[0-9A-F]+", v):
            raise ValueError("key_hex must contain only hexadecimal characters")
        if len(v) not in (32, 64):
            raise ValueError("key_hex must be 32 or 64 hex characters")
        return v


class ChannelUpdate(BaseModel):
    """Schema for updating a channel."""

    key_hex: Optional[str] = Field(
        default=None,
        min_length=32,
        max_length=64,
        description="Channel secret key as uppercase hex",
    )
    visibility: Optional[Literal["community", "member", "operator", "admin"]] = Field(
        default=None,
        description="Channel visibility/permission level",
    )
    enabled: Optional[bool] = Field(
        default=None,
        description="Whether the channel is active",
    )

    @field_validator("key_hex")
    @classmethod
    def validate_key_hex(cls, v: str | None) -> str | None:
        """Validate key is uppercase hex and correct length."""
        if v is None:
            return v
        v = v.strip().upper()
        if not re.fullmatch(r"[0-9A-F]+", v):
            raise ValueError("key_hex must contain only hexadecimal characters")
        if len(v) not in (32, 64):
            raise ValueError("key_hex must be 32 or 64 hex characters")
        return v


class ChannelRead(BaseModel):
    """Schema for reading a channel."""

    id: str = Field(..., description="Channel UUID")
    name: str = Field(..., description="Channel display name")
    channel_hash: str = Field(..., description="Channel hash (2-char hex)")
    visibility: str = Field(..., description="Visibility level")
    enabled: bool = Field(..., description="Whether the channel is active")
    masked_key: str = Field(..., description="Masked key (first/last 4 chars)")
    key_hex: Optional[str] = Field(
        default=None,
        description="Full key hex (visible to users with channel access)",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True}


class ChannelList(BaseModel):
    """Schema for paginated channel list response."""

    items: list[ChannelRead] = Field(..., description="List of channels")
    total: int = Field(..., description="Total number of channels")
