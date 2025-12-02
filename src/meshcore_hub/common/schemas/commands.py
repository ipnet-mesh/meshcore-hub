"""Pydantic schemas for command API endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class SendMessageCommand(BaseModel):
    """Schema for sending a direct message."""

    destination: str = Field(
        ...,
        min_length=12,
        max_length=64,
        description="Destination public key or prefix",
    )
    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Message content",
    )
    timestamp: Optional[int] = Field(
        default=None,
        description="Unix timestamp (optional, defaults to current time)",
    )


class SendChannelMessageCommand(BaseModel):
    """Schema for sending a channel message."""

    channel_idx: int = Field(
        ...,
        ge=0,
        le=255,
        description="Channel index (0-255)",
    )
    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Message content",
    )
    timestamp: Optional[int] = Field(
        default=None,
        description="Unix timestamp (optional, defaults to current time)",
    )


class SendAdvertCommand(BaseModel):
    """Schema for sending an advertisement."""

    flood: bool = Field(
        default=True,
        description="Whether to flood the advertisement",
    )


class RequestStatusCommand(BaseModel):
    """Schema for requesting node status."""

    target_public_key: Optional[str] = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="Target node public key (optional)",
    )


class RequestTelemetryCommand(BaseModel):
    """Schema for requesting telemetry data."""

    target_public_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Target node public key",
    )


class CommandResponse(BaseModel):
    """Schema for command response."""

    success: bool = Field(..., description="Whether command was accepted")
    message: str = Field(..., description="Response message")
    command_id: Optional[str] = Field(
        default=None,
        description="Command tracking ID (if applicable)",
    )
