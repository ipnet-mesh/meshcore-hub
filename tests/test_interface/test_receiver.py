"""Tests for receiver mode implementation."""

import pytest
from unittest.mock import MagicMock, patch

from meshcore_hub.interface.device import EventType
from meshcore_hub.interface.receiver import Receiver, create_receiver


class TestReceiver:
    """Tests for Receiver class."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.topic_builder = MagicMock()
        client.topic_builder.event_topic.return_value = "meshcore/abc/event/test"
        return client

    @pytest.fixture
    def receiver(self, mock_device, mock_mqtt_client):
        """Create a receiver instance."""
        return Receiver(mock_device, mock_mqtt_client)

    def test_start_connects_device_and_mqtt(
        self, receiver, mock_device, mock_mqtt_client
    ):
        """Test that start connects to device and MQTT."""
        receiver.start()

        assert mock_device.is_connected
        mock_mqtt_client.connect.assert_called_once()
        mock_mqtt_client.start_background.assert_called_once()

    def test_stop_disconnects_device_and_mqtt(
        self, receiver, mock_device, mock_mqtt_client
    ):
        """Test that stop disconnects device and MQTT."""
        receiver.start()
        receiver.stop()

        assert not mock_device.is_connected
        mock_mqtt_client.stop.assert_called_once()
        mock_mqtt_client.disconnect.assert_called_once()

    def test_events_published_to_mqtt(self, receiver, mock_device, mock_mqtt_client):
        """Test that device events are published to MQTT."""
        receiver.start()

        # Inject an event
        mock_device.inject_event(
            EventType.ADVERTISEMENT,
            {"public_key": "b" * 64, "name": "TestNode"},
        )

        # Allow time for event processing
        import time

        time.sleep(0.1)

        # Verify MQTT publish was called
        mock_mqtt_client.publish_event.assert_called()

    def test_receiver_syncs_contacts_on_advertisement(
        self, receiver, mock_device, mock_mqtt_client
    ):
        """Test that receiver syncs contacts when advertisement is received."""
        import time
        from unittest.mock import patch

        receiver.start()

        # Patch schedule_get_contacts to track calls
        with patch.object(
            mock_device, "schedule_get_contacts", return_value=True
        ) as mock_get:
            # Inject an advertisement event
            mock_device.inject_event(
                EventType.ADVERTISEMENT,
                {"pubkey_prefix": "b" * 64, "adv_name": "TestNode", "type": 1},
            )

            # Allow time for event processing
            time.sleep(0.1)

            # Verify schedule_get_contacts was called
            mock_get.assert_called()

    def test_receiver_handles_contact_sync_failure(
        self, receiver, mock_device, mock_mqtt_client
    ):
        """Test that receiver handles contact sync failures gracefully."""
        import time
        from unittest.mock import patch

        receiver.start()

        # Patch schedule_get_contacts to return False (failure)
        with patch.object(
            mock_device, "schedule_get_contacts", return_value=False
        ) as mock_get:
            # Should not raise exception even if sync fails
            mock_device.inject_event(
                EventType.ADVERTISEMENT,
                {"pubkey_prefix": "c" * 64, "adv_name": "FailNode", "type": 1},
            )

            # Allow time for event processing
            time.sleep(0.1)

            # Verify it was attempted
            mock_get.assert_called()


class TestCreateReceiver:
    """Tests for create_receiver factory function."""

    def test_creates_receiver_with_mock_device(self):
        """Test creating receiver with mock device."""
        with patch("meshcore_hub.interface.receiver.MQTTClient"):
            receiver = create_receiver(mock=True)

            assert receiver is not None
            assert receiver.device is not None
            assert receiver.device.public_key is not None

    def test_creates_receiver_with_custom_mqtt_config(self):
        """Test creating receiver with custom MQTT configuration."""
        with patch("meshcore_hub.interface.receiver.MQTTClient") as mock_mqtt:
            create_receiver(
                mock=True,
                mqtt_host="mqtt.example.com",
                mqtt_port=8883,
                mqtt_prefix="custom",
            )

            # Verify MQTT client was created with correct config
            mock_mqtt.assert_called_once()
            config = mock_mqtt.call_args[0][0]
            assert config.host == "mqtt.example.com"
            assert config.port == 8883
            assert config.prefix == "custom"
