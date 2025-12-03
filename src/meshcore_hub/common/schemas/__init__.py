"""Pydantic schemas for API request/response validation."""

from meshcore_hub.common.schemas.events import (
    AdvertisementEvent,
    ContactMessageEvent,
    ChannelMessageEvent,
    TraceDataEvent,
    TelemetryResponseEvent,
    ContactsEvent,
    SendConfirmedEvent,
    StatusResponseEvent,
    BatteryEvent,
    PathUpdatedEvent,
)
from meshcore_hub.common.schemas.nodes import (
    NodeRead,
    NodeList,
    NodeTagCreate,
    NodeTagUpdate,
    NodeTagRead,
)
from meshcore_hub.common.schemas.messages import (
    MessageRead,
    MessageList,
    MessageFilters,
)
from meshcore_hub.common.schemas.commands import (
    SendMessageCommand,
    SendChannelMessageCommand,
    SendAdvertCommand,
)
from meshcore_hub.common.schemas.members import (
    MemberCreate,
    MemberUpdate,
    MemberRead,
    MemberList,
)

__all__ = [
    # Events
    "AdvertisementEvent",
    "ContactMessageEvent",
    "ChannelMessageEvent",
    "TraceDataEvent",
    "TelemetryResponseEvent",
    "ContactsEvent",
    "SendConfirmedEvent",
    "StatusResponseEvent",
    "BatteryEvent",
    "PathUpdatedEvent",
    # Nodes
    "NodeRead",
    "NodeList",
    "NodeTagCreate",
    "NodeTagUpdate",
    "NodeTagRead",
    # Messages
    "MessageRead",
    "MessageList",
    "MessageFilters",
    # Commands
    "SendMessageCommand",
    "SendChannelMessageCommand",
    "SendAdvertCommand",
    # Members
    "MemberCreate",
    "MemberUpdate",
    "MemberRead",
    "MemberList",
]
