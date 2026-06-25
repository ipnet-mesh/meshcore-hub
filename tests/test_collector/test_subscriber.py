"""Tests for the collector subscriber."""

import pytest
from unittest.mock import MagicMock, call, patch

from meshcore_hub.collector.observer_filter import ObserverFilter
from meshcore_hub.collector.subscriber import Subscriber, create_subscriber


class TestSubscriber:
    """Tests for Subscriber class."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.topic_builder = MagicMock()
        client.topic_builder.prefix = "meshcore"
        client.topic_builder.all_events_topic.return_value = "meshcore/+/event/#"
        client.topic_builder.parse_event_topic.return_value = (
            "a" * 64,
            "advertisement",
        )
        client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "status",
        )
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
        assert mock_mqtt_client.subscribe.call_count == 3

    def test_stop_disconnects_mqtt(self, subscriber, mock_mqtt_client):
        """Test that stop disconnects MQTT."""
        with patch("meshcore_hub.collector.subscriber.time.sleep"):
            subscriber.start()
            subscriber.stop()

        mock_mqtt_client.stop.assert_called_once()
        mock_mqtt_client.disconnect.assert_called_once()

    def test_handle_mqtt_message_calls_handler(
        self, subscriber, mock_mqtt_client, db_manager
    ):
        """Test that MQTT messages are routed to handlers."""
        handler = MagicMock()
        subscriber.register_handler("advertisement", handler)
        subscriber.start()

        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "status",
        )
        subscriber._normalize_letsmesh_event = MagicMock(
            return_value=(
                "a" * 64,
                "advertisement",
                {"public_key": "b" * 64, "name": "Test"},
            )
        )

        subscriber._handle_mqtt_message(
            topic="meshcore/STN/abc/status",
            pattern="meshcore/+/+/status",
            payload={"public_key": "b" * 64, "name": "Test"},
        )

        handler.assert_called_once()

    def test_raw_capture_disabled_writes_no_rows(self, mock_mqtt_client, db_manager):
        """With capture disabled, no raw_packets rows are written but the
        structured handler still runs."""
        from sqlalchemy import select

        from meshcore_hub.common.models import RawPacket

        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client, db_manager, raw_packet_capture_enabled=False
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("a" * 64, "channel_msg_recv", {"text": "hi"})
        )

        subscriber._handle_mqtt_message(
            topic="meshcore/STN/abc/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "00", "hash": "h1"},
        )

        handler.assert_called_once()
        session = db_manager.get_session()
        try:
            rows = session.execute(select(RawPacket)).scalars().all()
            assert len(rows) == 0
        finally:
            session.close()

    def test_raw_capture_enabled_writes_row(self, mock_mqtt_client, db_manager):
        """With capture enabled, a packets-feed message writes one raw row."""
        from sqlalchemy import select

        from meshcore_hub.common.models import RawPacket

        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client, db_manager, raw_packet_capture_enabled=True
        )
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("a" * 64, "channel_msg_recv", {"text": "hi"})
        )
        subscriber._letsmesh_decoder.decode_payload = MagicMock(  # type: ignore[method-assign]
            return_value={"payloadType": 4, "payload": {"decoded": {}}}
        )

        subscriber._handle_mqtt_message(
            topic="meshcore/STN/abc/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "0011", "hash": "h1"},
        )

        session = db_manager.get_session()
        try:
            rows = session.execute(select(RawPacket)).scalars().all()
            assert len(rows) == 1
            assert rows[0].raw_hex == "0011"
            assert rows[0].event_type == "channel_msg_recv"
        finally:
            session.close()

    def test_raw_capture_skips_status_feed(self, mock_mqtt_client, db_manager):
        """Capture is packets-feed only; status feed writes no raw rows."""
        from sqlalchemy import select

        from meshcore_hub.common.models import RawPacket

        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "status",
        )
        subscriber = Subscriber(
            mock_mqtt_client, db_manager, raw_packet_capture_enabled=True
        )
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("a" * 64, "letsmesh_status", {})
        )

        subscriber._handle_mqtt_message(
            topic="meshcore/STN/abc/status",
            pattern="meshcore/+/+/status",
            payload={"some": "status"},
        )

        session = db_manager.get_session()
        try:
            rows = session.execute(select(RawPacket)).scalars().all()
            assert len(rows) == 0
        finally:
            session.close()

    def test_start_subscribes_to_letsmesh_topics(self, mock_mqtt_client, db_manager):
        """LetsMesh ingest mode subscribes to packets/status/internal feeds."""
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )

        subscriber.start()

        expected_calls = [
            call("meshcore/+/+/packets", subscriber._handle_mqtt_message),
            call("meshcore/+/+/status", subscriber._handle_mqtt_message),
            call("meshcore/+/+/internal", subscriber._handle_mqtt_message),
        ]
        mock_mqtt_client.subscribe.assert_has_calls(expected_calls, any_order=False)
        assert mock_mqtt_client.subscribe.call_count == 3

    def test_blocked_observer_is_dropped_no_dispatch(
        self, mock_mqtt_client, db_manager
    ):
        """An observer on the denylist has its event dropped before dispatch."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "b" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
            observer_filter=ObserverFilter.from_lists(denylist=["b" * 64]),
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        # Spy on normalize: it must never be called for a blocked observer.
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("b" * 64, "channel_msg_recv", {"text": "hi"})
        )

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'b' * 64}/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "00", "hash": "h1"},
        )

        handler.assert_not_called()
        subscriber._normalize_letsmesh_event.assert_not_called()

    def test_blocked_observer_writes_no_raw_packet(self, mock_mqtt_client, db_manager):
        """A blocked observer's packet is dropped before raw-packet capture."""
        from sqlalchemy import select

        from meshcore_hub.common.models import RawPacket

        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "b" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
            raw_packet_capture_enabled=True,
            observer_filter=ObserverFilter.from_lists(denylist=["b" * 64]),
        )
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("b" * 64, "channel_msg_recv", {"text": "hi"})
        )

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'b' * 64}/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "0011", "hash": "h1"},
        )

        session = db_manager.get_session()
        try:
            rows = session.execute(select(RawPacket)).scalars().all()
            assert len(rows) == 0
        finally:
            session.close()

    def test_allowed_observer_dispatches_normally(self, mock_mqtt_client, db_manager):
        """An observer on the allowlist is dispatched as usual."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
            observer_filter=ObserverFilter.from_lists(allowlist=["a" * 64]),
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("a" * 64, "channel_msg_recv", {"text": "hi"})
        )

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'a' * 64}/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "00", "hash": "h1"},
        )

        handler.assert_called_once()

    def test_observer_not_on_allowlist_is_dropped(self, mock_mqtt_client, db_manager):
        """With an allowlist active, an unlisted observer is dropped."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "b" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
            observer_filter=ObserverFilter.from_lists(allowlist=["a" * 64]),
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("b" * 64, "channel_msg_recv", {"text": "hi"})
        )

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'b' * 64}/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "00", "hash": "h1"},
        )

        handler.assert_not_called()

    def test_inactive_filter_does_not_parse_topic(self, mock_mqtt_client, db_manager):
        """The default (inactive) filter adds no work: the topic is not parsed
        for filtering, and dispatch proceeds normally."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.reset_mock()
        subscriber = Subscriber(mock_mqtt_client, db_manager)
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber._normalize_letsmesh_event = MagicMock(  # type: ignore[method-assign]
            return_value=("a" * 64, "channel_msg_recv", {"text": "hi"})
        )

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'a' * 64}/packets",
            pattern="meshcore/+/+/packets",
            payload={"raw": "00", "hash": "h1"},
        )

        handler.assert_called_once()
        # Inactive filter short-circuits before touching the topic builder.
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.assert_not_called()

    def test_letsmesh_status_maps_to_letsmesh_status(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """LetsMesh status payloads are stored as informational status events."""
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        advert_handler = MagicMock()
        status_handler = MagicMock()
        subscriber.register_handler("advertisement", advert_handler)
        subscriber.register_handler("letsmesh_status", status_handler)
        subscriber.start()

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'a' * 64}/status",
            pattern="meshcore/+/+/status",
            payload={
                "origin": "Observer Node",
                "origin_id": "b" * 64,
                "model": "Heltec V3",
                "mode": "repeater",
                "flags": 7,
            },
        )

        advert_handler.assert_not_called()
        status_handler.assert_called_once()
        public_key, event_type, payload, _db = status_handler.call_args.args
        assert public_key == "a" * 64
        assert event_type == "letsmesh_status"
        assert payload["origin_id"] == "b" * 64
        assert payload["origin"] == "Observer Node"
        assert payload["mode"] == "repeater"

    def test_letsmesh_status_with_debug_flags_does_not_emit_advertisement(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Status debug metadata should remain informational only."""
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        advert_handler = MagicMock()
        status_handler = MagicMock()
        subscriber.register_handler("advertisement", advert_handler)
        subscriber.register_handler("letsmesh_status", status_handler)
        subscriber.start()

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'a' * 64}/status",
            pattern="meshcore/+/+/status",
            payload={
                "origin": "Observer Node",
                "origin_id": "b" * 64,
                "mode": "repeater",
                "stats": {"debug_flags": 7},
            },
        )

        advert_handler.assert_not_called()
        status_handler.assert_called_once()
        _public_key, _event_type, payload, _db = status_handler.call_args.args
        assert payload["stats"]["debug_flags"] == 7

    def test_letsmesh_status_without_identity_maps_to_letsmesh_status(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Status heartbeat payloads without identity metadata stay informational."""
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        advert_handler = MagicMock()
        status_handler = MagicMock()
        subscriber.register_handler("advertisement", advert_handler)
        subscriber.register_handler("letsmesh_status", status_handler)
        subscriber.start()

        subscriber._handle_mqtt_message(
            topic=f"meshcore/STN/{'a' * 64}/status",
            pattern="meshcore/+/+/status",
            payload={
                "origin_id": "b" * 64,
                "stats": {"cpu": 27, "mem": 91, "debug_flags": 7},
            },
        )

        advert_handler.assert_not_called()
        status_handler.assert_called_once()

    def test_letsmesh_packet_maps_to_channel_message(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """LetsMesh packets are mapped to channel messages when text is available."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 5,
                "payload": {
                    "decoded": {
                        "decrypted": {
                            "message": "hello channel",
                        }
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "5",
                    "hash": "ABCDEF1234",
                    "timestamp": "2026-02-21T17:42:39.897932",
                    "SNR": "12.5",
                    "path": "91CBC3",
                },
            )

        handler.assert_called_once()
        public_key, event_type, payload, _db = handler.call_args.args
        assert public_key == "a" * 64
        assert event_type == "channel_msg_recv"
        assert payload["text"] == "hello channel"
        assert payload["txt_type"] == 5
        assert "sender_timestamp" not in payload
        assert payload["snr"] == 12.5
        assert payload["path_len"] == 3

    def test_letsmesh_packet_without_decrypted_text_is_not_shown_as_message(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Undecodable channel packets are kept as informational events, not messages."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        # A GRP_TXT (type 5) that does not decrypt is classified as
        # encrypted_channel, not routed to the channel message handler.
        encrypted_handler = MagicMock()
        channel_handler = MagicMock()
        subscriber.register_handler("encrypted_channel", encrypted_handler)
        subscriber.register_handler("channel_msg_recv", channel_handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value=None,
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "5",
                    "hash": "ABCDEF1234",
                    "raw": "15040791959fd9",
                },
            )

        encrypted_handler.assert_called_once()
        channel_handler.assert_not_called()

    def test_letsmesh_packet_uses_decoder_text_when_available(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """LetsMesh packet decoder output is used for message text and timestamp."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber.start()

        with (
            patch.object(
                subscriber._letsmesh_decoder,
                "decode_payload",
                return_value={
                    "payloadType": 5,
                    "pathLength": 4,
                    "payload": {
                        "decoded": {
                            "channelHash": "AA",
                            "decrypted": {
                                "sender": "ABCD1234",
                                "timestamp": 1771695860,
                                "message": "decoded hello",
                            },
                        }
                    },
                },
            ),
            patch.object(
                subscriber._letsmesh_decoder,
                "channel_name_from_decoded",
                return_value="test",
            ),
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "5",
                    "hash": "ABCDEF1234",
                    "raw": "15040791959fd9",
                    "SNR": "9.0",
                },
            )

        handler.assert_called_once()
        public_key, event_type, payload, _db = handler.call_args.args
        assert public_key == "a" * 64
        assert event_type == "channel_msg_recv"
        assert payload["text"] == "decoded hello"
        assert payload["channel_name"] == "test"
        assert payload["sender_timestamp"] == 1771695860
        assert payload["txt_type"] == 5
        assert payload["path_len"] == 4
        assert payload["channel_idx"] == 170
        assert payload["pubkey_prefix"] == "ABCD1234"

    def test_letsmesh_packet_type_1_maps_to_contact_message(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """LetsMesh packet type 1 is treated as direct/contact message traffic."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        handler = MagicMock()
        subscriber.register_handler("contact_msg_recv", handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 1,
                "payload": {
                    "decoded": {
                        "sourceHash": "7CAF1337A58D",
                        "decrypted": {
                            "message": "hello dm",
                        },
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "1",
                    "hash": "ABABAB1234",
                    "raw": "010203",
                },
            )

        handler.assert_called_once()
        public_key, event_type, payload, _db = handler.call_args.args
        assert public_key == "a" * 64
        assert event_type == "contact_msg_recv"
        assert payload["text"] == "hello dm"
        assert payload["pubkey_prefix"] == "7CAF1337A58D"

    def test_letsmesh_decoder_sender_name_prefixes_message_text(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Non-hex decoder sender names are rendered as `Name: Message`."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        subscriber._include_test_channel = True
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 5,
                "payload": {
                    "decoded": {
                        "channelHash": "D9",
                        "decrypted": {
                            "sender": "Stephenbarz",
                            "message": "hello mesh",
                        },
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "5",
                    "hash": "FEEDC0DE",
                    "raw": "AABBCC",
                },
            )

        handler.assert_called_once()
        _public_key, event_type, payload, _db = handler.call_args.args
        assert event_type == "channel_msg_recv"
        assert payload["text"] == "Stephenbarz: hello mesh"
        assert payload["channel_idx"] == 217
        assert "pubkey_prefix" not in payload

    def test_letsmesh_packet_type_4_maps_to_advertisement_with_location(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Decoder packet type 4 is mapped to advertisement with GPS coordinates."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        handler = MagicMock()
        subscriber.register_handler("advertisement", handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 4,
                "payload": {
                    "decoded": {
                        "type": 4,
                        "publicKey": "B" * 64,
                        "appData": {
                            "flags": 146,
                            "deviceRole": 2,
                            "location": {
                                "latitude": 42.470001,
                                "longitude": -71.330001,
                            },
                            "name": "Concord Attic G2",
                        },
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "4",
                    "hash": "A1B2C3D4",
                    "raw": "010203",
                },
            )

        handler.assert_called_once()
        public_key, event_type, payload, _db = handler.call_args.args
        assert public_key == "a" * 64
        assert event_type == "advertisement"
        assert payload["public_key"] == "b" * 64
        assert payload["name"] == "Concord Attic G2"
        assert payload["adv_type"] == "repeater"
        assert payload["flags"] == 146
        assert payload["lat"] == 42.470001
        assert payload["lon"] == -71.330001

    def test_letsmesh_packet_type_11_maps_to_contact(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Decoder packet type 11 is mapped to native contact events."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        contact_handler = MagicMock()
        advert_handler = MagicMock()
        subscriber.register_handler("contact", contact_handler)
        subscriber.register_handler("advertisement", advert_handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 11,
                "payload": {
                    "decoded": {
                        "type": 11,
                        "publicKey": "C" * 64,
                        "nodeType": 2,
                        "nodeTypeName": "Repeater",
                        "rawFlags": 146,
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "11",
                    "hash": "E5F6A7B8",
                    "raw": "040506",
                },
            )

        advert_handler.assert_not_called()
        contact_handler.assert_called_once()
        _public_key, event_type, payload, _db = contact_handler.call_args.args
        assert event_type == "contact"
        assert payload["public_key"] == "c" * 64
        assert payload["type"] == 2
        assert payload["flags"] == 146

    def test_letsmesh_packet_type_9_maps_to_trace_data(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Decoder packet type 9 is mapped to native trace_data events."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        trace_handler = MagicMock()
        subscriber.register_handler("trace_data", trace_handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 9,
                "pathLength": 4,
                "payload": {
                    "decoded": {
                        "type": 9,
                        "traceTag": "DF9D7A20",
                        "authCode": 0,
                        "flags": 0,
                        "pathHashes": ["71", "0B", "24", "0B"],
                        "snrValues": [12.5, 11.5, 10, 6.25],
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "9",
                    "hash": "99887766",
                    "raw": "ABCDEF",
                },
            )

        trace_handler.assert_called_once()
        _public_key, event_type, payload, _db = trace_handler.call_args.args
        assert event_type == "trace_data"
        assert payload["initiator_tag"] == int("DF9D7A20", 16)
        assert payload["path_hashes"] == ["71", "0B", "24", "0B"]
        assert payload["hop_count"] == 4
        assert payload["snr_values"] == [12.5, 11.5, 10.0, 6.25]

    def test_letsmesh_trace_data_with_multibyte_path_hashes(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Multibyte path hashes flow through the collector pipeline correctly."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        trace_handler = MagicMock()
        subscriber.register_handler("trace_data", trace_handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 9,
                "pathLength": 3,
                "payload": {
                    "decoded": {
                        "type": 9,
                        "traceTag": "DF9D7A20",
                        "authCode": 0,
                        "flags": 0,
                        "pathHashes": ["71a2", "0Bcd", "24ef"],
                        "snrValues": [12.5, 11.5, 10.0],
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "9",
                    "hash": "99887766",
                    "raw": "ABCDEF",
                },
            )

        trace_handler.assert_called_once()
        _public_key, event_type, payload, _db = trace_handler.call_args.args
        assert event_type == "trace_data"
        assert payload["path_hashes"] == ["71A2", "0BCD", "24EF"]
        assert payload["hop_count"] == 3

    def test_letsmesh_path_updated_with_multibyte_path_hashes(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Multibyte path hashes in path_updated events are normalized correctly."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        path_handler = MagicMock()
        subscriber.register_handler("path_updated", path_handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 8,
                "payload": {
                    "decoded": {
                        "type": 8,
                        "isValid": True,
                        "pathLength": 2,
                        "pathHashes": ["AA11", "BB22"],
                        "extraType": 244,
                        "extraData": "D" * 64,
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "8",
                    "hash": "99887766",
                    "raw": "ABCDEF",
                },
            )

        path_handler.assert_called_once()
        _public_key, event_type, payload, _db = path_handler.call_args.args
        assert event_type == "path_updated"
        assert payload["path_hashes"] == ["AA11", "BB22"]
        assert payload["hop_count"] == 2

    def test_letsmesh_packet_type_8_maps_to_path_updated(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Decoder packet type 8 is mapped to native path_updated events."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        path_handler = MagicMock()
        packet_handler = MagicMock()
        subscriber.register_handler("path_updated", path_handler)
        subscriber.register_handler("letsmesh_packet", packet_handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 8,
                "payload": {
                    "decoded": {
                        "type": 8,
                        "isValid": True,
                        "pathLength": 2,
                        "pathHashes": ["AA", "BB"],
                        "extraType": 244,
                        "extraData": "D" * 64,
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "8",
                    "hash": "99887766",
                    "raw": "ABCDEF",
                },
            )

        packet_handler.assert_not_called()
        path_handler.assert_called_once()
        _public_key, event_type, payload, _db = path_handler.call_args.args
        assert event_type == "path_updated"
        assert payload["hop_count"] == 2
        assert payload["path_hashes"] == ["AA", "BB"]
        assert payload["extra_type"] == 244
        assert payload["node_public_key"] == "d" * 64

    def test_letsmesh_packet_fallback_logs_decoded_payload(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Unmapped packets are classified by payload type and keep decoder output."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        # MULTIPART (type 10) has no structured handler -> classified as multipart.
        packet_handler = MagicMock()
        subscriber.register_handler("multipart", packet_handler)
        subscriber.start()

        decoded_packet = {
            "payloadType": 10,
            "payload": {
                "decoded": {
                    "type": 10,
                    "isValid": True,
                }
            },
        }
        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value=decoded_packet,
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "10",
                    "hash": "99887766",
                    "raw": "ABCDEF",
                },
            )

        packet_handler.assert_called_once()
        _public_key, event_type, payload, _db = packet_handler.call_args.args
        assert event_type == "multipart"
        assert payload["decoded_payload_type"] == 10
        assert payload["decoded_packet"] == decoded_packet

    def test_letsmesh_packet_sender_fallback_from_payload_fields(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Sender prefix falls back to payload sourceHash when decoder has no sender."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        handler = MagicMock()
        subscriber.register_handler("channel_msg_recv", handler)
        subscriber.start()

        with patch.object(
            subscriber._letsmesh_decoder,
            "decode_payload",
            return_value={
                "payloadType": 5,
                "payload": {
                    "decoded": {
                        "decrypted": {
                            "message": "hello from payload sender",
                        },
                    }
                },
            },
        ):
            subscriber._handle_mqtt_message(
                topic=f"meshcore/STN/{'a' * 64}/packets",
                pattern="meshcore/+/+/packets",
                payload={
                    "packet_type": "5",
                    "hash": "ABABAB1234",
                    "sourceHash": "1A2B3C4D5E6F",
                    "raw": "010203",
                },
            )

        handler.assert_called_once()
        _public_key, _event_type, payload, _db = handler.call_args.args
        assert payload["text"] == "hello from payload sender"
        assert payload["pubkey_prefix"] == "1A2B3C4D5E6F"


class TestSubscriberDispatch:
    """Tests for _dispatch_event and lifecycle methods."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.topic_builder = MagicMock()
        client.topic_builder.prefix = "meshcore"
        client.topic_builder.all_events_topic.return_value = "meshcore/+/event/#"
        client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "status",
        )
        return client

    @pytest.fixture
    def subscriber(self, mock_mqtt_client, db_manager):
        """Create a subscriber instance."""
        return Subscriber(mock_mqtt_client, db_manager)

    def test_dispatch_event_with_no_handler_falls_back_to_event_log(self, subscriber):
        """Unregistered event types fall back to event_log handler."""
        with patch(
            "meshcore_hub.collector.handlers.event_log.handle_event_log"
        ) as mock_log:
            subscriber._dispatch_event("a" * 64, "unknown_type", {"data": 1})
            mock_log.assert_called_once()

    def test_dispatch_event_handler_exception_logged(self, subscriber):
        """Handler exceptions are caught and logged, not re-raised."""
        handler = MagicMock(side_effect=RuntimeError("boom"))
        subscriber.register_handler("test_event", handler)

        subscriber._dispatch_event("a" * 64, "test_event", {"data": 1})

        handler.assert_called_once()

    def test_dispatch_event_event_log_exception_logged(self, subscriber):
        """Event log handler exceptions are caught and logged."""
        with patch(
            "meshcore_hub.collector.handlers.event_log.handle_event_log",
            side_effect=RuntimeError("log boom"),
        ):
            subscriber._dispatch_event("a" * 64, "unknown_type", {"data": 1})

    def test_dispatch_event_queues_webhook(self, subscriber):
        """Events are queued for webhook when dispatcher is configured."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.webhooks = [MagicMock()]
        subscriber._webhook_dispatcher = mock_dispatcher

        handler = MagicMock()
        subscriber.register_handler("test_event", handler)

        subscriber._dispatch_event("a" * 64, "test_event", {"data": 1})

        assert len(subscriber._webhook_queue) == 1
        assert subscriber._webhook_queue[0][0] == "test_event"

    def test_dispatch_event_no_webhook_without_dispatcher(self, subscriber):
        """No webhook queued when dispatcher is not configured."""
        handler = MagicMock()
        subscriber.register_handler("test_event", handler)

        subscriber._dispatch_event("a" * 64, "test_event", {"data": 1})

        assert len(subscriber._webhook_queue) == 0

    def test_start_with_mqtt_retry(self, mock_mqtt_client, db_manager):
        """MQTT connection is retried on failure."""
        mock_mqtt_client.connect.side_effect = [
            ConnectionError("fail"),
            None,
        ]

        subscriber = Subscriber(mock_mqtt_client, db_manager)
        with patch("meshcore_hub.collector.subscriber.time.sleep"):
            subscriber.start()

        assert mock_mqtt_client.connect.call_count == 2
        assert subscriber._mqtt_connected is True
        subscriber.stop()

    def test_start_mqtt_all_retries_exhausted(self, mock_mqtt_client, db_manager):
        """Subscriber raises when all MQTT retries fail."""
        mock_mqtt_client.connect.side_effect = ConnectionError("fail")

        subscriber = Subscriber(mock_mqtt_client, db_manager)
        with (
            patch("meshcore_hub.collector.subscriber.time.sleep"),
            pytest.raises(ConnectionError),
        ):
            subscriber.start()

    def test_run_calls_start_when_not_running(self, mock_mqtt_client, db_manager):
        """run() calls start() if subscriber is not running."""
        subscriber = Subscriber(mock_mqtt_client, db_manager)

        with patch.object(subscriber, "start") as mock_start:
            mock_start.side_effect = lambda: setattr(subscriber, "_running", True)
            subscriber._shutdown_event.set()
            subscriber.run()

        mock_start.assert_called_once()

    def test_stop_when_not_running(self, subscriber):
        """stop() is a no-op when not running."""
        subscriber._running = False
        subscriber.stop()

    def test_health_status(self, subscriber):
        """Health status reports correct state."""
        status = subscriber.get_health_status()
        assert status["running"] is False
        assert status["mqtt_connected"] is False
        assert status["database_connected"] is False
        assert status["healthy"] is False


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


class TestChannelKeyRefresh:
    """Tests for channel key loading and refresh from database."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.topic_builder = MagicMock()
        client.topic_builder.prefix = "meshcore"
        client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "status",
        )
        return client

    def test_load_channel_keys_from_db(self, mock_mqtt_client, db_manager):
        """Test loading channel keys from database."""
        from meshcore_hub.common.models.channel import Channel

        with db_manager.session_scope() as session:
            ch = Channel(
                name="TestCh",
                key_hex="AABBCCDDEEFF00112233445566778899",
                channel_hash=Channel.compute_channel_hash(
                    "AABBCCDDEEFF00112233445566778899"
                ),
                visibility="community",
                enabled=True,
            )
            session.add(ch)

        subscriber = Subscriber(mock_mqtt_client, db_manager)

        assert len(subscriber._db_channel_keys) == 1
        assert "TestCh=AABBCCDDEEFF00112233445566778899" in subscriber._db_channel_keys

    def test_load_channel_keys_detects_test_channel(self, mock_mqtt_client, db_manager):
        """Test that test channel is detected by name."""
        from meshcore_hub.common.models.channel import Channel

        with db_manager.session_scope() as session:
            ch = Channel(
                name="Test",
                key_hex="AABBCCDDEEFF00112233445566778899",
                channel_hash=Channel.compute_channel_hash(
                    "AABBCCDDEEFF00112233445566778899"
                ),
                visibility="community",
                enabled=True,
            )
            session.add(ch)

        subscriber = Subscriber(mock_mqtt_client, db_manager)

        assert subscriber._include_test_channel is True

    def test_load_channel_keys_only_enabled(self, mock_mqtt_client, db_manager):
        """Test that only enabled channels are loaded."""
        from meshcore_hub.common.models.channel import Channel

        with db_manager.session_scope() as session:
            ch1 = Channel(
                name="Enabled",
                key_hex="AABBCCDDEEFF00112233445566778899",
                channel_hash=Channel.compute_channel_hash(
                    "AABBCCDDEEFF00112233445566778899"
                ),
                enabled=True,
            )
            ch2 = Channel(
                name="Disabled",
                key_hex="11223344556677889900AABBCCDDEEFF",
                channel_hash=Channel.compute_channel_hash(
                    "11223344556677889900AABBCCDDEEFF"
                ),
                enabled=False,
            )
            session.add_all([ch1, ch2])

        subscriber = Subscriber(mock_mqtt_client, db_manager)

        assert len(subscriber._db_channel_keys) == 1
        assert "Enabled=" in subscriber._db_channel_keys[0]

    def test_load_channel_keys_handles_db_error(self, mock_mqtt_client, db_manager):
        """Test graceful handling of database errors during key loading."""
        broken_db = MagicMock()
        broken_db.session_scope.side_effect = Exception("DB connection failed")

        subscriber = Subscriber(mock_mqtt_client, broken_db)

        assert subscriber._db_channel_keys == []
        assert subscriber._include_test_channel is False

    def test_refresh_channel_keys_from_db(self, mock_mqtt_client, db_manager):
        """Test refreshing channel keys reloads the decoder."""
        from meshcore_hub.common.models.channel import Channel

        subscriber = Subscriber(mock_mqtt_client, db_manager)
        assert len(subscriber._db_channel_keys) == 0

        with db_manager.session_scope() as session:
            ch = Channel(
                name="NewCh",
                key_hex="CCDDEEFF00112233445566778899AABB",
                channel_hash=Channel.compute_channel_hash(
                    "CCDDEEFF00112233445566778899AABB"
                ),
                visibility="community",
                enabled=True,
            )
            session.add(ch)

        with patch.object(subscriber._letsmesh_decoder, "reload_keys") as mock_reload:
            subscriber._refresh_channel_keys_from_db()

        assert len(subscriber._db_channel_keys) == 1
        mock_reload.assert_called_once_with(subscriber._db_channel_keys)

    def test_refresh_handles_db_error(self, mock_mqtt_client, db_manager):
        """Test refresh handles database errors gracefully."""
        broken_db = MagicMock()

        def broken_scope():
            raise Exception("DB error")

        broken_db.session_scope.side_effect = broken_scope

        subscriber = Subscriber(broken_db, broken_db)

        with patch.object(subscriber._letsmesh_decoder, "reload_keys"):
            subscriber._refresh_channel_keys_from_db()

        assert subscriber._db_channel_keys == []

    def test_channel_refresh_scheduler_starts(self, mock_mqtt_client, db_manager):
        """Test channel refresh scheduler starts a daemon thread."""
        subscriber = Subscriber(
            mock_mqtt_client, db_manager, channel_refresh_interval_seconds=300
        )
        subscriber._running = True
        with patch("meshcore_hub.collector.subscriber.time.sleep"):
            subscriber._start_channel_refresh_scheduler()

            assert subscriber._channel_refresh_thread is not None
            assert subscriber._channel_refresh_thread.daemon is True

            subscriber._running = False
            subscriber._channel_refresh_thread.join(timeout=2.0)

    def test_channel_refresh_scheduler_disabled(self, mock_mqtt_client, db_manager):
        """Test channel refresh scheduler is disabled when interval is 0."""
        subscriber = Subscriber(
            mock_mqtt_client, db_manager, channel_refresh_interval_seconds=0
        )
        subscriber._running = True
        subscriber._start_channel_refresh_scheduler()

        assert subscriber._channel_refresh_thread is None

        subscriber._running = False

    def test_channel_refresh_scheduler_stop(self, mock_mqtt_client, db_manager):
        """Test stopping the channel refresh scheduler."""
        subscriber = Subscriber(
            mock_mqtt_client, db_manager, channel_refresh_interval_seconds=300
        )
        subscriber._running = True
        with patch("meshcore_hub.collector.subscriber.time.sleep"):
            subscriber._start_channel_refresh_scheduler()
            subscriber._running = False

            subscriber._stop_channel_refresh_scheduler()
        assert subscriber._channel_refresh_thread is not None
        assert not subscriber._channel_refresh_thread.is_alive()

    def test_load_channel_keys_empty_db(self, mock_mqtt_client, db_manager):
        """Test loading channel keys from empty database."""
        subscriber = Subscriber(mock_mqtt_client, db_manager)

        assert subscriber._db_channel_keys == []
        assert subscriber._include_test_channel is False

    def test_decoder_initialized_with_db_keys(self, mock_mqtt_client, db_manager):
        """Test decoder is initialized with database channel keys."""
        from meshcore_hub.common.models.channel import Channel

        key_hex = "DDEEFF00112233445566778899AABBCC"
        with db_manager.session_scope() as session:
            ch = Channel(
                name="DecCh",
                key_hex=key_hex,
                channel_hash=Channel.compute_channel_hash(key_hex),
                visibility="community",
                enabled=True,
            )
            session.add(ch)

        subscriber = Subscriber(mock_mqtt_client, db_manager)

        assert key_hex in subscriber._letsmesh_decoder._channel_keys


class TestSpamRescoreScheduler:
    """Tests for the background spam re-scoring sweep scheduler."""

    @pytest.fixture
    def mock_mqtt_client(self):
        client = MagicMock()
        client.topic_builder = MagicMock()
        client.topic_builder.prefix = "meshcore"
        return client

    def test_disabled_does_not_start_thread(self, mock_mqtt_client, db_manager):
        """With spam detection off (default), no sweep thread is created."""
        sub = Subscriber(mock_mqtt_client, db_manager)
        sub._start_spam_rescore_scheduler()
        assert sub._spam_rescore_thread is None
        # Stopping when never started is a no-op.
        sub._stop_spam_rescore_scheduler()

    def test_enabled_runs_sweep_and_stops(
        self, mock_mqtt_client, db_manager, monkeypatch
    ):
        """Enabled scheduler spawns a thread, runs a sweep, and joins on stop."""
        import threading

        import meshcore_hub.collector.spam as spam_mod
        from meshcore_hub.collector.spam import SpamConfig

        cfg = SpamConfig(enabled=True, rescore_interval_seconds=1)
        monkeypatch.setattr(spam_mod, "get_spam_config", lambda: cfg)
        # Avoid the real 1s-per-tick sleep in the inner loop.
        monkeypatch.setattr(
            "meshcore_hub.collector.subscriber.time.sleep", lambda *_: None
        )

        sub = Subscriber(mock_mqtt_client, db_manager)
        called = threading.Event()

        def fake_rescore(session, sweep_cfg):
            called.set()
            sub._running = False  # break the loop after one sweep
            return 1  # truthy -> exercises the "updated" log line

        monkeypatch.setattr(spam_mod, "rescore_recent", fake_rescore)

        sub._running = True
        sub._start_spam_rescore_scheduler()
        assert called.wait(timeout=5.0)
        sub._stop_spam_rescore_scheduler()

        assert sub._spam_rescore_thread is not None
        assert not sub._spam_rescore_thread.is_alive()

    def test_sweep_error_is_logged(self, mock_mqtt_client, db_manager, monkeypatch):
        """An exception in the sweep is caught and logged, not propagated."""
        import threading

        import meshcore_hub.collector.spam as spam_mod
        from meshcore_hub.collector.spam import SpamConfig

        cfg = SpamConfig(enabled=True, rescore_interval_seconds=1)
        monkeypatch.setattr(spam_mod, "get_spam_config", lambda: cfg)
        monkeypatch.setattr(
            "meshcore_hub.collector.subscriber.time.sleep", lambda *_: None
        )

        sub = Subscriber(mock_mqtt_client, db_manager)
        called = threading.Event()

        def boom(session, sweep_cfg):
            sub._running = False  # break the loop before raising
            called.set()
            raise RuntimeError("sweep failed")

        monkeypatch.setattr(spam_mod, "rescore_recent", boom)

        sub._running = True
        sub._start_spam_rescore_scheduler()
        assert called.wait(timeout=5.0)
        sub._stop_spam_rescore_scheduler()
        assert sub._spam_rescore_thread is not None
        assert not sub._spam_rescore_thread.is_alive()
