"""Webhook Dispatcher for sending events to external services.

The webhook dispatcher:
1. Receives events from the collector
2. Filters events based on JSONPath expressions
3. Sends HTTP POST requests to configured endpoints
4. Implements retry logic with exponential backoff
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    """Configuration for a single webhook endpoint."""

    url: str
    name: str = "webhook"
    event_types: list[str] = field(default_factory=list)
    filter_expression: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 10.0
    max_retries: int = 3
    retry_backoff: float = 2.0
    enabled: bool = True

    def matches_event(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Check if this webhook should receive the event.

        Args:
            event_type: Event type name
            payload: Event payload

        Returns:
            True if the event matches this webhook's filters
        """
        # Check event type filter
        if self.event_types and event_type not in self.event_types:
            return False

        # Check JSONPath filter expression
        if self.filter_expression:
            if not self._evaluate_filter(payload):
                return False

        return True

    def _evaluate_filter(self, payload: dict[str, Any]) -> bool:
        """Evaluate a simple JSONPath-like filter expression.

        Supports expressions like:
        - $.field == "value"
        - $.nested.field != null
        - $.field exists
        - $.field > 10

        Args:
            payload: Event payload

        Returns:
            True if the filter matches
        """
        if not self.filter_expression:
            return True

        expr = self.filter_expression.strip()

        # Parse expression: $.path operator value
        # Supports: ==, !=, >, <, >=, <=, exists, not exists
        # Note: >= and <= must come before > and < in the alternation
        pattern = r"^\$\.([a-zA-Z0-9_.]+)\s+(==|!=|>=|<=|>|<|exists|not exists)\s*(.*)$"
        match = re.match(pattern, expr)

        if not match:
            logger.warning(f"Invalid filter expression: {expr}")
            return True  # Pass through if expression is invalid

        path = match.group(1)
        operator = match.group(2)
        value_str = match.group(3).strip() if match.group(3) else None

        # Navigate the path
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                current = None
                break

        # Evaluate operator
        if operator == "exists":
            return current is not None
        elif operator == "not exists":
            return current is None
        elif current is None:
            return False

        # Parse value for comparison
        if value_str is None:
            return False

        # Handle quoted strings
        compare_value: Any
        if value_str.startswith('"') and value_str.endswith('"'):
            compare_value = value_str[1:-1]
        elif value_str.startswith("'") and value_str.endswith("'"):
            compare_value = value_str[1:-1]
        elif value_str == "null":
            compare_value = None
        elif value_str == "true":
            compare_value = True
        elif value_str == "false":
            compare_value = False
        else:
            try:
                compare_value = int(value_str)
            except ValueError:
                try:
                    compare_value = float(value_str)
                except ValueError:
                    compare_value = value_str

        # Perform comparison
        try:
            if operator == "==":
                return bool(current == compare_value)
            elif operator == "!=":
                return bool(current != compare_value)
            elif operator == ">":
                return bool(current > compare_value)
            elif operator == "<":
                return bool(current < compare_value)
            elif operator == ">=":
                return bool(current >= compare_value)
            elif operator == "<=":
                return bool(current <= compare_value)
        except TypeError:
            return False

        return False


class WebhookDispatcher:
    """Dispatches events to webhook endpoints."""

    def __init__(self, webhooks: Optional[list[WebhookConfig]] = None):
        """Initialize the webhook dispatcher.

        Args:
            webhooks: List of webhook configurations
        """
        self.webhooks = webhooks or []
        self._client: Optional[httpx.AsyncClient] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if the dispatcher is running."""
        return self._running

    def add_webhook(self, webhook: WebhookConfig) -> None:
        """Add a webhook configuration.

        Args:
            webhook: Webhook configuration
        """
        self.webhooks.append(webhook)
        logger.info(f"Added webhook: {webhook.name} -> {webhook.url}")

    def remove_webhook(self, name: str) -> bool:
        """Remove a webhook by name.

        Args:
            name: Webhook name

        Returns:
            True if webhook was removed
        """
        for i, webhook in enumerate(self.webhooks):
            if webhook.name == name:
                del self.webhooks[i]
                logger.info(f"Removed webhook: {name}")
                return True
        return False

    async def start(self) -> None:
        """Start the webhook dispatcher."""
        if self._running:
            return

        self._client = httpx.AsyncClient()
        self._running = True
        logger.info(f"Webhook dispatcher started with {len(self.webhooks)} webhooks")

    async def stop(self) -> None:
        """Stop the webhook dispatcher."""
        if not self._running:
            return

        self._running = False
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("Webhook dispatcher stopped")

    async def dispatch(
        self,
        event_type: str,
        payload: dict[str, Any],
        public_key: Optional[str] = None,
    ) -> dict[str, bool]:
        """Dispatch an event to all matching webhooks.

        Args:
            event_type: Event type name
            payload: Event payload
            public_key: Source node public key

        Returns:
            Dictionary mapping webhook names to success status
        """
        if not self._running or not self.webhooks:
            return {}

        # Build full event data
        event_data = {
            "event_type": event_type,
            "public_key": public_key,
            "payload": payload,
        }

        results: dict[str, bool] = {}

        # Dispatch to all matching webhooks concurrently
        tasks = []
        for webhook in self.webhooks:
            if not webhook.enabled:
                continue
            if webhook.matches_event(event_type, payload):
                tasks.append(self._send_webhook(webhook, event_data))

        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            for webhook, result in zip(
                [
                    w
                    for w in self.webhooks
                    if w.enabled and w.matches_event(event_type, payload)
                ],
                task_results,
            ):
                if isinstance(result, Exception):
                    results[webhook.name] = False
                    logger.error(f"Webhook {webhook.name} failed: {result}")
                elif isinstance(result, bool):
                    results[webhook.name] = result
                else:
                    # Should not happen, but handle gracefully
                    results[webhook.name] = False

        return results

    async def _send_webhook(
        self,
        webhook: WebhookConfig,
        event_data: dict[str, Any],
    ) -> bool:
        """Send an event to a webhook endpoint with retry logic.

        Args:
            webhook: Webhook configuration
            event_data: Event data to send

        Returns:
            True if the webhook was sent successfully
        """
        if not self._client:
            return False

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MeshCore-Hub/1.0",
            **webhook.headers,
        }

        last_error: Optional[Exception] = None

        for attempt in range(webhook.max_retries + 1):
            try:
                response = await self._client.post(
                    webhook.url,
                    json=event_data,
                    headers=headers,
                    timeout=webhook.timeout,
                )

                if response.status_code >= 200 and response.status_code < 300:
                    logger.debug(
                        f"Webhook {webhook.name} sent successfully "
                        f"(status={response.status_code})"
                    )
                    return True
                else:
                    logger.warning(
                        f"Webhook {webhook.name} returned status {response.status_code}"
                    )
                    last_error = Exception(f"HTTP {response.status_code}")

            except httpx.TimeoutException as e:
                logger.warning(f"Webhook {webhook.name} timed out: {e}")
                last_error = e
            except httpx.RequestError as e:
                logger.warning(f"Webhook {webhook.name} request error: {e}")
                last_error = e
            except Exception as e:
                logger.error(f"Webhook {webhook.name} unexpected error: {e}")
                last_error = e

            # Retry with backoff (but not after the last attempt)
            if attempt < webhook.max_retries:
                backoff = webhook.retry_backoff * (2**attempt)
                logger.info(
                    f"Retrying webhook {webhook.name} in {backoff}s "
                    f"(attempt {attempt + 2}/{webhook.max_retries + 1})"
                )
                await asyncio.sleep(backoff)

        logger.error(
            f"Webhook {webhook.name} failed after {webhook.max_retries + 1} attempts: "
            f"{last_error}"
        )
        return False


def create_webhook_dispatcher_from_config(
    config: list[dict[str, Any]],
) -> WebhookDispatcher:
    """Create a webhook dispatcher from configuration.

    Args:
        config: List of webhook configurations as dicts

    Returns:
        Configured WebhookDispatcher instance

    Example config:
        [
            {
                "name": "my-webhook",
                "url": "https://example.com/webhook",
                "event_types": ["advertisement", "contact_msg_recv"],
                "filter_expression": "$.snr > -10",
                "headers": {"X-API-Key": "secret"},
                "timeout": 5.0,
                "max_retries": 3,
                "retry_backoff": 2.0,
                "enabled": true
            }
        ]
    """
    webhooks = []

    for item in config:
        try:
            webhook = WebhookConfig(
                url=item["url"],
                name=item.get("name", "webhook"),
                event_types=item.get("event_types", []),
                filter_expression=item.get("filter_expression"),
                headers=item.get("headers", {}),
                timeout=item.get("timeout", 10.0),
                max_retries=item.get("max_retries", 3),
                retry_backoff=item.get("retry_backoff", 2.0),
                enabled=item.get("enabled", True),
            )
            webhooks.append(webhook)
            logger.info(f"Loaded webhook config: {webhook.name}")
        except KeyError as e:
            logger.error(f"Invalid webhook config (missing {e}): {item}")
        except Exception as e:
            logger.error(f"Failed to load webhook config: {e}")

    return WebhookDispatcher(webhooks)


# Synchronous wrapper for use in non-async handlers
_dispatcher: Optional[WebhookDispatcher] = None
_dispatch_queue: list[tuple[str, dict[str, Any], Optional[str]]] = []
_dispatch_callback: Optional[Callable[[str, dict[str, Any], Optional[str]], None]] = (
    None
)


def set_dispatch_callback(
    callback: Optional[Callable[[str, dict[str, Any], Optional[str]], None]]
) -> None:
    """Set a callback for synchronous webhook dispatch.

    This allows the collector to integrate webhook dispatching into its
    event handling loop without requiring async handlers.

    Args:
        callback: Function to call with (event_type, payload, public_key)
    """
    global _dispatch_callback
    _dispatch_callback = callback


def dispatch_event(
    event_type: str,
    payload: dict[str, Any],
    public_key: Optional[str] = None,
) -> None:
    """Queue an event for webhook dispatch.

    This is a synchronous wrapper for use in non-async handlers.
    Events are queued and should be processed by an async loop.

    Args:
        event_type: Event type name
        payload: Event payload
        public_key: Source node public key
    """
    if _dispatch_callback:
        _dispatch_callback(event_type, payload, public_key)
    else:
        _dispatch_queue.append((event_type, payload, public_key))


def get_queued_events() -> list[tuple[str, dict[str, Any], Optional[str]]]:
    """Get and clear queued events.

    Returns:
        List of (event_type, payload, public_key) tuples
    """
    global _dispatch_queue
    events = _dispatch_queue.copy()
    _dispatch_queue = []
    return events
