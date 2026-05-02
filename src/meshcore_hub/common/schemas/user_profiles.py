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
    roles: list[str] = Field(default_factory=list, description="User roles")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> "UserProfileRead":
        if hasattr(obj, "role_list") and not isinstance(obj, dict):
            d = {
                "id": str(obj.id),  # type: ignore[attr-defined]
                "user_id": obj.user_id,  # type: ignore[attr-defined]
                "name": obj.name,  # type: ignore[attr-defined]
                "callsign": obj.callsign,  # type: ignore[attr-defined]
                "roles": obj.role_list,
                "created_at": obj.created_at,  # type: ignore[attr-defined]
                "updated_at": obj.updated_at,  # type: ignore[attr-defined]
            }
            return super().model_validate(d)
        return super().model_validate(obj)


class UserProfilePublic(BaseModel):
    """Public-facing schema — omits user_id for privacy."""

    id: str = Field(..., description="Profile UUID")
    name: Optional[str] = Field(default=None, description="User's display name")
    callsign: Optional[str] = Field(default=None, description="Amateur radio callsign")
    roles: list[str] = Field(default_factory=list, description="User roles")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class AdoptedNodeRead(BaseModel):
    """Schema for reading an adopted node in the context of a user profile."""

    public_key: str = Field(..., description="Node's 64-character hex public key")
    name: Optional[str] = Field(default=None, description="Node display name")
    adv_type: Optional[str] = Field(default=None, description="Advertisement type")
    adopted_at: datetime = Field(..., description="When the node was adopted")

    class Config:
        from_attributes = True


class UserProfileListItem(BaseModel):
    """Schema for a single profile in list responses."""

    id: str = Field(..., description="Profile UUID")
    name: Optional[str] = Field(default=None, description="User's display name")
    callsign: Optional[str] = Field(default=None, description="Amateur radio callsign")
    roles: list[str] = Field(default_factory=list, description="User roles")
    node_count: int = Field(default=0, description="Number of adopted nodes")
    adopted_nodes: list[AdoptedNodeRead] = Field(
        default_factory=list,
        description="Nodes adopted by this user",
    )


class UserProfileList(BaseModel):
    """Schema for paginated profile list response."""

    items: list[UserProfileListItem] = Field(..., description="List of profiles")
    total: int = Field(..., description="Total number of profiles")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Page offset")


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


class UserProfileWithNodes(UserProfileRead):
    """Schema for reading a user profile with adopted nodes (owner view)."""

    nodes: list[AdoptedNodeRead] = Field(
        default_factory=list,
        description="Nodes adopted by this user",
    )


class UserProfilePublicWithNodes(UserProfilePublic):
    """Public profile view with adopted nodes."""

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
