"""Tests for the collector subscriber."""

import pytest
from unittest.mock import MagicMock, patch

from meshcore_hub.collector.subscriber import Subscriber, create_subscriber


class TestSubscriber:
    """Tests for Subscriber class."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.topic_builder = MagicMock()
        client.topic_builder.all_events_topic.return_value = "meshcore/+/event/#"
        client.topic_builder.parse_event_topic.return_value = ("a" * 64, "advertisement")
        return client

    @pytest.fixture
    def subscriber(self, mock_mqtt_client, db_manager):
        """Create a subscriber instance."""
        return Subscriber(mock_mqtt_client, db_manager)

    def test_register_handler(self, subscriber):
        """Test handler registration."""
        handler = MagicMock()

        subscriber.register_handler("advertisement", handler)

        assert "advertisement" in subscriber._handlers

    def test_start_connects_mqtt(self, subscriber, mock_mqtt_client):
        """Test that start connects to MQTT."""
        subscriber.start()

        mock_mqtt_client.connect.assert_called_once()
        mock_mqtt_client.start_background.assert_called_once()
        mock_mqtt_client.subscribe.assert_called_once()

    def test_stop_disconnects_mqtt(self, subscriber, mock_mqtt_client):
        """Test that stop disconnects MQTT."""
        subscriber.start()
        subscriber.stop()

        mock_mqtt_client.stop.assert_called_once()
        mock_mqtt_client.disconnect.assert_called_once()

    def test_handle_mqtt_message_calls_handler(self, subscriber, mock_mqtt_client, db_manager):
        """Test that MQTT messages are routed to handlers."""
        handler = MagicMock()
        subscriber.register_handler("advertisement", handler)
        subscriber.start()

        subscriber._handle_mqtt_message(
            topic="meshcore/abc/event/advertisement",
            pattern="meshcore/+/event/#",
            payload={"public_key": "b" * 64, "name": "Test"},
        )

        handler.assert_called_once()


class TestCreateSubscriber:
    """Tests for create_subscriber factory function."""

    def test_creates_subscriber(self):
        """Test creating a subscriber."""
        with patch("meshcore_hub.collector.subscriber.MQTTClient") as MockMQTT:
            subscriber = create_subscriber(
                mqtt_host="localhost",
                mqtt_port=1883,
                database_url="sqlite:///:memory:",
            )

            assert subscriber is not None
            MockMQTT.assert_called_once()
