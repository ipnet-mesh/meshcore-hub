"""Pydantic schemas for user profile API endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserProfileRead(BaseModel):
    """Schema for reading a user profile."""

    id: str = Field(..., description="Profile UUID")
    user_id: str = Field(..., description="OIDC subject identifier")
    name: Optional[str] = Field(default=None, description="User's display name")
    callsign: Optional[str] = Field(default=None, description="Amateur radio callsign")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """Schema for updating a user profile."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="User's display name",
    )
    callsign: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Amateur radio callsign",
    )


class AdoptedNodeRead(BaseModel):
    """Schema for reading an adopted node in the context of a user profile."""

    public_key: str = Field(..., description="Node's 64-character hex public key")
    name: Optional[str] = Field(default=None, description="Node display name")
    adv_type: Optional[str] = Field(default=None, description="Advertisement type")
    adopted_at: datetime = Field(..., description="When the node was adopted")

    class Config:
        from_attributes = True


class UserProfileWithNodes(UserProfileRead):
    """Schema for reading a user profile with adopted nodes."""

    nodes: list[AdoptedNodeRead] = Field(
        default_factory=list,
        description="Nodes adopted by this user",
    )


class NodeAdoptRequest(BaseModel):
    """Schema for adopting a node."""

    public_key: str = Field(
        ...,
        max_length=64,
        description="Public key of the node to adopt",
    )
