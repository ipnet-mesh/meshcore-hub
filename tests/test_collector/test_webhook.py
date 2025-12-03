"""Tests for the webhook dispatcher module."""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from meshcore_hub.collector.webhook import (
    WebhookConfig,
    WebhookDispatcher,
    create_webhook_dispatcher_from_config,
    dispatch_event,
    get_queued_events,
    set_dispatch_callback,
)


class TestWebhookConfig:
    """Tests for WebhookConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = WebhookConfig(url="https://example.com/webhook")
        assert config.url == "https://example.com/webhook"
        assert config.name == "webhook"
        assert config.event_types == []
        assert config.filter_expression is None
        assert config.headers == {}
        assert config.timeout == 10.0
        assert config.max_retries == 3
        assert config.retry_backoff == 2.0
        assert config.enabled is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            name="my-webhook",
            event_types=["advertisement"],
            filter_expression="$.snr > -10",
            headers={"X-API-Key": "secret"},
            timeout=5.0,
            max_retries=5,
            retry_backoff=1.0,
            enabled=False,
        )
        assert config.name == "my-webhook"
        assert config.event_types == ["advertisement"]
        assert config.filter_expression == "$.snr > -10"
        assert config.headers == {"X-API-Key": "secret"}
        assert config.timeout == 5.0
        assert config.max_retries == 5
        assert config.retry_backoff == 1.0
        assert config.enabled is False

    def test_matches_event_no_filters(self):
        """Test event matching with no filters."""
        config = WebhookConfig(url="https://example.com/webhook")
        assert config.matches_event("advertisement", {"name": "Node1"}) is True
        assert config.matches_event("contact_msg_recv", {"text": "Hello"}) is True

    def test_matches_event_type_filter(self):
        """Test event matching with event type filter."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            event_types=["advertisement", "contact_msg_recv"],
        )
        assert config.matches_event("advertisement", {}) is True
        assert config.matches_event("contact_msg_recv", {}) is True
        assert config.matches_event("channel_msg_recv", {}) is False

    def test_matches_event_filter_equals(self):
        """Test event matching with equals filter."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression='$.name == "Node1"',
        )
        assert config.matches_event("advertisement", {"name": "Node1"}) is True
        assert config.matches_event("advertisement", {"name": "Node2"}) is False

    def test_matches_event_filter_not_equals(self):
        """Test event matching with not equals filter."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression='$.name != "Node1"',
        )
        assert config.matches_event("advertisement", {"name": "Node1"}) is False
        assert config.matches_event("advertisement", {"name": "Node2"}) is True

    def test_matches_event_filter_numeric_comparison(self):
        """Test event matching with numeric comparisons."""
        config_gt = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.snr > -10",
        )
        assert config_gt.matches_event("msg", {"snr": -5}) is True
        assert config_gt.matches_event("msg", {"snr": -10}) is False
        assert config_gt.matches_event("msg", {"snr": -15}) is False

        config_gte = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.snr >= -10",
        )
        assert config_gte.matches_event("msg", {"snr": -10}) is True

        config_lt = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.hops < 5",
        )
        assert config_lt.matches_event("msg", {"hops": 3}) is True
        assert config_lt.matches_event("msg", {"hops": 5}) is False

        config_lte = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.hops <= 5",
        )
        assert config_lte.matches_event("msg", {"hops": 5}) is True

    def test_matches_event_filter_exists(self):
        """Test event matching with exists filter."""
        config_exists = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.name exists",
        )
        assert config_exists.matches_event("adv", {"name": "Node1"}) is True
        assert config_exists.matches_event("adv", {"other": "value"}) is False

        config_not_exists = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.name not exists",
        )
        assert config_not_exists.matches_event("adv", {"name": "Node1"}) is False
        assert config_not_exists.matches_event("adv", {"other": "value"}) is True

    def test_matches_event_filter_nested_path(self):
        """Test event matching with nested path."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression='$.data.type == "sensor"',
        )
        assert config.matches_event("event", {"data": {"type": "sensor"}}) is True
        assert config.matches_event("event", {"data": {"type": "other"}}) is False
        assert config.matches_event("event", {"data": {}}) is False
        assert config.matches_event("event", {}) is False

    def test_matches_event_filter_boolean(self):
        """Test event matching with boolean values."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.active == true",
        )
        assert config.matches_event("event", {"active": True}) is True
        assert config.matches_event("event", {"active": False}) is False

    def test_matches_event_filter_null(self):
        """Test event matching with null value."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="$.value != null",
        )
        assert config.matches_event("event", {"value": "something"}) is True
        assert config.matches_event("event", {"value": None}) is False

    def test_matches_event_invalid_filter(self):
        """Test event matching with invalid filter expression."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            filter_expression="invalid expression",
        )
        # Invalid expressions should pass through
        assert config.matches_event("event", {"any": "data"}) is True


class TestWebhookDispatcher:
    """Tests for WebhookDispatcher."""

    @pytest.fixture
    def dispatcher(self):
        """Create a webhook dispatcher for testing."""
        return WebhookDispatcher()

    @pytest.mark.asyncio
    async def test_start_stop(self, dispatcher):
        """Test starting and stopping the dispatcher."""
        assert dispatcher.is_running is False

        await dispatcher.start()
        assert dispatcher.is_running is True
        assert dispatcher._client is not None

        await dispatcher.stop()
        assert dispatcher.is_running is False
        assert dispatcher._client is None

    def test_add_webhook(self, dispatcher):
        """Test adding a webhook."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="test-webhook",
        )
        dispatcher.add_webhook(webhook)
        assert len(dispatcher.webhooks) == 1
        assert dispatcher.webhooks[0].name == "test-webhook"

    def test_remove_webhook(self, dispatcher):
        """Test removing a webhook."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="test-webhook",
        )
        dispatcher.add_webhook(webhook)
        assert len(dispatcher.webhooks) == 1

        result = dispatcher.remove_webhook("test-webhook")
        assert result is True
        assert len(dispatcher.webhooks) == 0

        result = dispatcher.remove_webhook("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_not_running(self, dispatcher):
        """Test dispatch when dispatcher is not running."""
        result = await dispatcher.dispatch("event", {"data": "test"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_dispatch_no_webhooks(self, dispatcher):
        """Test dispatch with no webhooks configured."""
        await dispatcher.start()
        result = await dispatcher.dispatch("event", {"data": "test"})
        assert result == {}
        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_success(self, dispatcher):
        """Test successful webhook dispatch."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="test-webhook",
        )
        dispatcher.add_webhook(webhook)
        await dispatcher.start()

        # Mock the HTTP client
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch.object(
            dispatcher._client, "post", return_value=mock_response
        ) as mock_post:
            result = await dispatcher.dispatch(
                "advertisement",
                {"name": "Node1"},
                public_key="abc123",
            )

            assert result == {"test-webhook": True}
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["event_type"] == "advertisement"
            assert call_kwargs["json"]["payload"]["name"] == "Node1"
            assert call_kwargs["json"]["public_key"] == "abc123"

        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_disabled_webhook(self, dispatcher):
        """Test dispatch skips disabled webhooks."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="disabled-webhook",
            enabled=False,
        )
        dispatcher.add_webhook(webhook)
        await dispatcher.start()

        result = await dispatcher.dispatch("event", {"data": "test"})
        assert result == {}

        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_filtered_webhook(self, dispatcher):
        """Test dispatch respects event type filter."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="filtered-webhook",
            event_types=["advertisement"],
        )
        dispatcher.add_webhook(webhook)
        await dispatcher.start()

        # This event should not match the filter
        result = await dispatcher.dispatch("contact_msg_recv", {"text": "Hello"})
        assert result == {}

        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_http_error(self, dispatcher):
        """Test dispatch handles HTTP errors."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="error-webhook",
            max_retries=0,  # No retries for faster test
        )
        dispatcher.add_webhook(webhook)
        await dispatcher.start()

        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch.object(dispatcher._client, "post", return_value=mock_response):
            result = await dispatcher.dispatch("event", {"data": "test"})
            assert result == {"error-webhook": False}

        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_timeout(self, dispatcher):
        """Test dispatch handles timeouts."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="timeout-webhook",
            max_retries=0,
        )
        dispatcher.add_webhook(webhook)
        await dispatcher.start()

        with patch.object(
            dispatcher._client,
            "post",
            side_effect=httpx.TimeoutException("Timeout"),
        ):
            result = await dispatcher.dispatch("event", {"data": "test"})
            assert result == {"timeout-webhook": False}

        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_retry_success(self, dispatcher):
        """Test dispatch retries and eventually succeeds."""
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            name="retry-webhook",
            max_retries=2,
            retry_backoff=0.01,  # Fast backoff for tests
        )
        dispatcher.add_webhook(webhook)
        await dispatcher.start()

        mock_response_success = AsyncMock()
        mock_response_success.status_code = 200

        # First call fails, second succeeds
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Timeout")
            return mock_response_success

        with patch.object(dispatcher._client, "post", side_effect=mock_post):
            result = await dispatcher.dispatch("event", {"data": "test"})
            assert result == {"retry-webhook": True}
            assert call_count == 2

        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_dispatch_multiple_webhooks(self, dispatcher):
        """Test dispatch to multiple webhooks concurrently."""
        webhook1 = WebhookConfig(
            url="https://example.com/webhook1",
            name="webhook-1",
        )
        webhook2 = WebhookConfig(
            url="https://example.com/webhook2",
            name="webhook-2",
        )
        dispatcher.add_webhook(webhook1)
        dispatcher.add_webhook(webhook2)
        await dispatcher.start()

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch.object(dispatcher._client, "post", return_value=mock_response):
            result = await dispatcher.dispatch("event", {"data": "test"})
            assert result == {"webhook-1": True, "webhook-2": True}

        await dispatcher.stop()


class TestWebhookDispatcherFactory:
    """Tests for create_webhook_dispatcher_from_config."""

    def test_create_from_config(self):
        """Test creating dispatcher from configuration."""
        config: list[dict[str, Any]] = [
            {
                "name": "webhook-1",
                "url": "https://example.com/webhook1",
                "event_types": ["advertisement"],
            },
            {
                "name": "webhook-2",
                "url": "https://example.com/webhook2",
                "filter_expression": "$.snr > -10",
                "headers": {"X-API-Key": "secret"},
                "timeout": 5.0,
            },
        ]

        dispatcher = create_webhook_dispatcher_from_config(config)
        assert len(dispatcher.webhooks) == 2
        assert dispatcher.webhooks[0].name == "webhook-1"
        assert dispatcher.webhooks[0].event_types == ["advertisement"]
        assert dispatcher.webhooks[1].name == "webhook-2"
        assert dispatcher.webhooks[1].filter_expression == "$.snr > -10"
        assert dispatcher.webhooks[1].headers == {"X-API-Key": "secret"}
        assert dispatcher.webhooks[1].timeout == 5.0

    def test_create_from_config_missing_url(self):
        """Test creating dispatcher with missing URL in config."""
        config = [
            {
                "name": "invalid-webhook",
                # Missing 'url'
            },
        ]

        dispatcher = create_webhook_dispatcher_from_config(config)
        assert len(dispatcher.webhooks) == 0

    def test_create_from_empty_config(self):
        """Test creating dispatcher from empty config."""
        dispatcher = create_webhook_dispatcher_from_config([])
        assert len(dispatcher.webhooks) == 0


class TestSyncDispatchHelpers:
    """Tests for synchronous dispatch helper functions."""

    def test_queue_events(self):
        """Test queuing events for dispatch."""
        # Clear any existing state
        get_queued_events()
        set_dispatch_callback(None)

        dispatch_event("event1", {"data": 1}, "key1")
        dispatch_event("event2", {"data": 2}, "key2")

        events = get_queued_events()
        assert len(events) == 2
        assert events[0] == ("event1", {"data": 1}, "key1")
        assert events[1] == ("event2", {"data": 2}, "key2")

        # Queue should be cleared
        events = get_queued_events()
        assert len(events) == 0

    def test_dispatch_callback(self):
        """Test dispatch callback."""
        received_events = []

        def callback(event_type, payload, public_key):
            received_events.append((event_type, payload, public_key))

        set_dispatch_callback(callback)

        dispatch_event("test_event", {"value": "test"}, "pub_key_123")

        assert len(received_events) == 1
        assert received_events[0] == ("test_event", {"value": "test"}, "pub_key_123")

        # Queue should be empty when using callback
        events = get_queued_events()
        assert len(events) == 0

        # Clean up
        set_dispatch_callback(None)
