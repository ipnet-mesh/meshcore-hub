"""Tests for the collector subscriber."""

import pytest
from unittest.mock import MagicMock, call, patch

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
        assert payload["SNR"] == 12.5
        assert payload["path_len"] == 3

    def test_letsmesh_packet_without_decrypted_text_is_not_shown_as_message(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Undecodable LetsMesh packets are kept as informational events, not messages."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        letsmesh_packet_handler = MagicMock()
        channel_handler = MagicMock()
        subscriber.register_handler("letsmesh_packet", letsmesh_packet_handler)
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

        letsmesh_packet_handler.assert_called_once()
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
        assert payload["channel_name"] == "#test"
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
        assert payload["public_key"] == "B" * 64
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
        assert payload["public_key"] == "C" * 64
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
        assert payload["node_public_key"] == "D" * 64

    def test_letsmesh_packet_fallback_logs_decoded_payload(
        self, mock_mqtt_client, db_manager
    ) -> None:
        """Unmapped packets include decoder output in letsmesh_packet payload."""
        mock_mqtt_client.topic_builder.parse_letsmesh_upload_topic.return_value = (
            "a" * 64,
            "packets",
        )
        subscriber = Subscriber(
            mock_mqtt_client,
            db_manager,
        )
        packet_handler = MagicMock()
        subscriber.register_handler("letsmesh_packet", packet_handler)
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
        assert event_type == "letsmesh_packet"
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
