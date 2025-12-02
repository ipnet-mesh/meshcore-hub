"""Event handlers for processing MQTT messages."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshcore_hub.collector.subscriber import Subscriber


def register_all_handlers(subscriber: "Subscriber") -> None:
    """Register all event handlers with the subscriber.

    Args:
        subscriber: Subscriber instance
    """
    from meshcore_hub.collector.handlers.advertisement import handle_advertisement
    from meshcore_hub.collector.handlers.message import (
        handle_contact_message,
        handle_channel_message,
    )
    from meshcore_hub.collector.handlers.trace import handle_trace_data
    from meshcore_hub.collector.handlers.telemetry import handle_telemetry
    from meshcore_hub.collector.handlers.contacts import handle_contacts
    from meshcore_hub.collector.handlers.event_log import handle_event_log

    # Persisted events with specific handlers
    subscriber.register_handler("advertisement", handle_advertisement)
    subscriber.register_handler("contact_msg_recv", handle_contact_message)
    subscriber.register_handler("channel_msg_recv", handle_channel_message)
    subscriber.register_handler("trace_data", handle_trace_data)
    subscriber.register_handler("telemetry_response", handle_telemetry)
    subscriber.register_handler("contacts", handle_contacts)

    # Informational events (logged only)
    subscriber.register_handler("send_confirmed", handle_event_log)
    subscriber.register_handler("status_response", handle_event_log)
    subscriber.register_handler("battery", handle_event_log)
    subscriber.register_handler("path_updated", handle_event_log)
