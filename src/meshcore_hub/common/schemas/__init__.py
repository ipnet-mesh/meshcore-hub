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
    ReceiverInfo,
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
from meshcore_hub.common.schemas.network import (
    RadioConfig,
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
    # Messages & Events
    "ReceiverInfo",
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
    # Network
    "RadioConfig",
]
