"""Pydantic schemas for route API endpoints."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RouteNodeRead(BaseModel):
    """A path-node entry in a route."""

    node_id: str
    position: int
    expected_hash: Optional[str] = None
    name: Optional[str] = None
    public_key: Optional[str] = None

    model_config = {"from_attributes": True}


class RouteObserverRead(BaseModel):
    """An observer entry in a route."""

    node_id: str
    name: Optional[str] = None
    public_key: Optional[str] = None

    model_config = {"from_attributes": True}


class RouteResultSummary(BaseModel):
    """Lightweight evaluation result embedded in list responses."""

    state: Optional[str] = None
    quality: Optional[str] = None
    matched_count: Optional[int] = None
    threshold: Optional[int] = None
    effective_degraded: Optional[int] = None
    evaluated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RouteCreate(BaseModel):
    """Schema for creating a route."""

    from_label: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Label for the route's start endpoint",
    )
    to_label: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Label for the route's end endpoint",
    )
    description: Optional[str] = Field(default=None, description="Route description")
    visibility: Literal["community", "member", "operator", "admin"] = Field(
        default="community", description="Visibility level"
    )
    match_width: int = Field(
        default=1, ge=1, le=3, description="Hash prefix width (1-3 bytes)"
    )
    window_hours: int = Field(
        default=24, ge=1, le=720, description="Evaluation window in hours"
    )
    packet_count_threshold: int = Field(
        default=3, ge=1, le=10000, description="Minimum distinct packets for healthy"
    )
    degraded_threshold: Optional[int] = Field(
        default=None, description="Comfort bar (null = 2x threshold)"
    )
    max_hop_span: Optional[int] = Field(
        default=None, description="Max hop distance between first and last node"
    )
    enabled: bool = Field(default=True, description="Whether this route is evaluated")
    reversible: bool = Field(
        default=True, description="Whether to match the path in both directions"
    )
    node_public_keys: list[str] = Field(
        ..., description="Ordered path node public keys (64-char hex, >= 2, distinct)"
    )
    observer_public_keys: Optional[list[str]] = Field(
        default=None,
        description="Observer node public keys (empty/None = all observers)",
    )

    @model_validator(mode="after")
    def validate_route(self) -> "RouteCreate":
        if len(self.node_public_keys) < 2:
            raise ValueError("At least 2 path nodes are required")
        if len({k.lower() for k in self.node_public_keys}) < len(self.node_public_keys):
            raise ValueError("Path nodes must be distinct")
        if (
            self.degraded_threshold is not None
            and self.degraded_threshold <= self.packet_count_threshold
        ):
            raise ValueError("degraded_threshold must be > packet_count_threshold")
        return self


class RouteUpdate(BaseModel):
    """Schema for updating a route."""

    from_label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    to_label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: Optional[Literal["community", "member", "operator", "admin"]] = None
    match_width: Optional[int] = Field(default=None, ge=1, le=3)
    window_hours: Optional[int] = Field(default=None, ge=1, le=720)
    packet_count_threshold: Optional[int] = Field(default=None, ge=1, le=10000)
    degraded_threshold: Optional[int] = None
    max_hop_span: Optional[int] = None
    enabled: Optional[bool] = None
    reversible: Optional[bool] = None
    node_public_keys: Optional[list[str]] = None
    observer_public_keys: Optional[list[str]] = None

    @model_validator(mode="after")
    def validate_route(self) -> "RouteUpdate":
        if self.node_public_keys is not None:
            if len(self.node_public_keys) < 2:
                raise ValueError("At least 2 path nodes are required")
            if len({k.lower() for k in self.node_public_keys}) < len(
                self.node_public_keys
            ):
                raise ValueError("Path nodes must be distinct")
        if (
            self.degraded_threshold is not None
            and self.packet_count_threshold is not None
            and self.degraded_threshold <= self.packet_count_threshold
        ):
            raise ValueError("degraded_threshold must be > packet_count_threshold")
        return self


class RouteRead(BaseModel):
    """Schema for reading a route (list-level with lightweight result)."""

    id: str
    from_label: str
    to_label: str
    description: Optional[str] = None
    visibility: str
    match_width: int
    window_hours: int
    packet_count_threshold: int
    degraded_threshold: Optional[int] = None
    max_hop_span: Optional[int] = None
    enabled: bool
    reversible: bool
    route_nodes: list[RouteNodeRead] = []
    route_observers: list[RouteObserverRead] = []
    route_result: Optional[RouteResultSummary] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RouteList(BaseModel):
    """Paginated route list response."""

    items: list[RouteRead]
    total: int


class RecentMatchPath(BaseModel):
    """A recent matched path for card expand."""

    packet_hash: Optional[str] = None
    hops: list[dict[str, Any]] = []
    received_at: Optional[datetime] = None
    observer_node_id: Optional[str] = None


class ContributingObserver(BaseModel):
    """An observer that contributed matching receptions."""

    node_id: str
    name: Optional[str] = None
    match_count: int = 0


class RouteDetail(BaseModel):
    """Full detail for GET /api/v1/routes/{id}."""

    id: str
    from_label: str
    to_label: str
    description: Optional[str] = None
    visibility: str
    match_width: int
    window_hours: int
    packet_count_threshold: int
    degraded_threshold: Optional[int] = None
    max_hop_span: Optional[int] = None
    enabled: bool
    reversible: bool
    route_nodes: list[RouteNodeRead] = []
    route_observers: list[RouteObserverRead] = []
    route_result: Optional[RouteResultSummary] = None
    contributing_observers: list[ContributingObserver] = []
    recent_matches: list[RecentMatchPath] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoutePreviewRequest(BaseModel):
    """Schema for the preview endpoint."""

    node_public_keys: list[str] = Field(
        ..., description="Ordered path node public keys"
    )
    match_width: int = Field(default=1, ge=1, le=3)
    window_hours: int = Field(default=24, ge=1, le=720)
    packet_count_threshold: int = Field(default=3, ge=1, le=10000)
    degraded_threshold: Optional[int] = None
    max_hop_span: Optional[int] = None
    observer_public_keys: Optional[list[str]] = None
    reversible: bool = Field(default=True)

    @model_validator(mode="after")
    def validate_preview(self) -> "RoutePreviewRequest":
        if len(self.node_public_keys) < 2:
            raise ValueError("At least 2 path nodes are required")
        if len({k.lower() for k in self.node_public_keys}) < len(self.node_public_keys):
            raise ValueError("Path nodes must be distinct")
        return self


class RoutePreviewResponse(BaseModel):
    """Schema for preview results."""

    matched_count: Optional[int] = None
    quality: Optional[str] = None
    state: Optional[str] = None
    contributing_observers: dict[str, int] = {}
    collisions: dict[str, int] = {}
    truncated: bool = False
    candidate_count: Optional[int] = None
