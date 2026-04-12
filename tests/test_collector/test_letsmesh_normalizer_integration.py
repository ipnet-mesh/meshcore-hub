"""Integration tests for LetsMesh normalizer packet type routing.

Tests the full _normalize_letsmesh_event flow with a mock decoder
returning realistic to_dict() structures for each packet type.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder
from meshcore_hub.collector.letsmesh_normalizer import LetsMeshNormalizer


class _TestNormalizer(LetsMeshNormalizer):
    """Minimal normalizer subclass wired with a mock decoder for testing."""

    def __init__(self, decoder: LetsMeshPacketDecoder) -> None:
        self._letsmesh_decoder = decoder
        self.mqtt = MagicMock()
        self.mqtt.topic_builder.parse_letsmesh_upload_topic = MagicMock(
            return_value=None,
        )


def _make_decoder(
    decoded_packets: dict[str, dict[str, Any] | None],
) -> LetsMeshPacketDecoder:
    """Create a decoder that returns pre-configured results by raw hex."""
    decoder = LetsMeshPacketDecoder()

    original = decoder.decode_payload

    def stub(payload: dict[str, Any]) -> dict[str, Any] | None:
        raw = payload.get("raw", "")
        if raw in decoded_packets:
            return decoded_packets[raw]
        return original(payload)

    decoder.decode_payload = stub  # type: ignore[method-assign]
    return decoder


PUB_KEY = "AA" * 32
OBSERVER_KEY = "BB" * 32


class TestStatusFeed:
    def test_status_feed_passes_through(self) -> None:
        decoder = _make_decoder({})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "status",
        )
        payload = {"uptime": 3600, "nodes_seen": 5}
        result = norm._normalize_letsmesh_event("meshcore/BB.../status", payload)
        assert result is not None
        pk, event_type, pl = result
        assert pk == OBSERVER_KEY
        assert event_type == "letsmesh_status"
        assert pl == payload


class TestInternalFeed:
    def test_internal_feed_passes_through(self) -> None:
        decoder = _make_decoder({})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "internal",
        )
        payload = {"info": "restart"}
        result = norm._normalize_letsmesh_event("meshcore/BB.../internal", payload)
        assert result is not None
        pk, event_type, pl = result
        assert pk == OBSERVER_KEY
        assert event_type == "letsmesh_internal"
        assert pl == payload


class TestAdvertPacket:
    def test_advert_with_name_and_location(self) -> None:
        raw = "advert1"
        decoded = {
            "payloadType": 4,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 4,
                    "publicKey": PUB_KEY,
                    "timestamp": 1700000000,
                    "signature": "CC" * 64,
                    "appData": {
                        "flags": 0x90,
                        "deviceRole": 2,
                        "hasLocation": True,
                        "hasName": True,
                        "location": {"latitude": 47.5, "longitude": -122.1},
                        "name": "TestRepeater",
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        pk, event_type, pl = result
        assert pk == OBSERVER_KEY
        assert event_type == "advertisement"
        assert pl["public_key"] == PUB_KEY
        assert pl["name"] == "TestRepeater"
        assert pl["adv_type"] == "repeater"
        assert pl["lat"] == 47.5
        assert pl["lon"] == -122.1

    def test_advert_without_app_data_falls_back(self) -> None:
        raw = "advert2"
        decoded = {
            "payloadType": 4,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 4,
                    "publicKey": PUB_KEY,
                    "timestamp": 1700000000,
                    "signature": "CC" * 64,
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event(
            "t", {"raw": raw, "origin": "FallbackName"}
        )
        assert result is not None
        _, event_type, pl = result
        assert event_type == "advertisement"
        assert pl["public_key"] == PUB_KEY
        assert pl["name"] == "FallbackName"


class TestGroupTextPacket:
    def test_grouptext_decrypted_routes_to_channel_msg(self) -> None:
        raw = "gt1"
        decoded = {
            "payloadType": 5,
            "pathLength": 1,
            "payload": {
                "decoded": {
                    "type": 5,
                    "channelHash": "11",
                    "sourceHash": "AB",
                    "decrypted": {
                        "message": "Hello world",
                        "sender": "Alice",
                        "timestamp": 1700000000,
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw, "hash": "abc123"})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "channel_msg_recv"
        assert "Alice" in pl["text"]
        assert "Hello world" in pl["text"]
        assert pl.get("channel_name") == "Public"

    def test_grouptext_not_decrypted_falls_through(self) -> None:
        raw = "gt2"
        decoded = {
            "payloadType": 5,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 5,
                    "channelHash": "FF",
                    "ciphertext": "AABBCC",
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "letsmesh_packet"
        assert pl.get("decoded_payload_type") == 5


class TestTextMessagePacket:
    def test_textmessage_decrypted_routes_to_contact_msg(self) -> None:
        raw = "tm1"
        decoded = {
            "payloadType": 2,
            "pathLength": 2,
            "payload": {
                "decoded": {
                    "type": 2,
                    "destinationHash": "CD",
                    "sourceHash": "AB",
                    "decrypted": {
                        "message": "Direct hello",
                        "sender": None,
                        "timestamp": 1700000000,
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "contact_msg_recv"
        assert "Direct hello" in pl["text"]


class TestAnonRequestPacket:
    def test_anonrequest_decrypted_routes_to_contact_msg(self) -> None:
        raw = "ar1"
        decoded = {
            "payloadType": 7,
            "pathLength": 1,
            "payload": {
                "decoded": {
                    "type": 7,
                    "destinationHash": "CD",
                    "senderPublicKey": "DD" * 32,
                    "decrypted": {
                        "message": "anon login message",
                        "timestamp": 1700000000,
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "contact_msg_recv"
        assert "anon login message" in pl["text"]


class TestTracePacket:
    def test_trace_with_snr_routes_to_trace_data(self) -> None:
        raw = "tr1"
        decoded = {
            "payloadType": 9,
            "pathLength": 3,
            "payload": {
                "decoded": {
                    "type": 9,
                    "traceTag": "A1B2C3D4",
                    "authCode": 42,
                    "flags": 0,
                    "pathHashes": ["AA", "BB", "CC"],
                    "snrValues": [5.25, -3.5, 12.0],
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "trace_data"
        assert pl["initiator_tag"] == 0xA1B2C3D4
        assert pl["path_hashes"] == ["AA", "BB", "CC"]
        assert pl["snr_values"] == [5.25, -3.5, 12.0]
        assert pl["hop_count"] == 3

    def test_trace_without_decoded_payload_falls_through(self) -> None:
        raw = "tr2"
        decoded = {
            "payloadType": 9,
            "pathLength": 0,
            "payload": {
                "decoded": None,
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "letsmesh_packet"


class TestControlPacket:
    def test_control_discover_response_routes_to_contact(self) -> None:
        raw = "ctrl1"
        decoded = {
            "payloadType": 11,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 11,
                    "flags": 1,
                    "subType": 144,
                    "dataHex": "",
                    "publicKey": PUB_KEY,
                    "nodeType": 2,
                    "parsed": {
                        "publicKey": PUB_KEY,
                        "nodeType": 2,
                        "snr": 10,
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "contact"
        assert pl["public_key"] == PUB_KEY
        assert pl["type"] == 2

    def test_control_non_discover_routes_to_status_response(self) -> None:
        raw = "ctrl2"
        decoded = {
            "payloadType": 11,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 11,
                    "flags": 0,
                    "subType": 128,
                    "dataHex": "",
                    "parsed": {},
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "status_response"
        assert pl["control_subtype"] == 128


class TestPathPacket:
    def test_path_update_routes_correctly(self) -> None:
        raw = "path1"
        decoded = {
            "payloadType": 8,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 8,
                    "pathLength": 4,
                    "pathHashes": ["AA", "BB", "CC", "DD"],
                    "extraType": 1,
                    "extraData": PUB_KEY,
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "path_updated"
        assert pl["hop_count"] == 4
        assert pl["path_hashes"] == ["AA", "BB", "CC", "DD"]
        assert pl["node_public_key"] == PUB_KEY


class TestResponsePacket:
    def test_response_with_battery_routes_to_battery(self) -> None:
        raw = "resp1"
        decoded = {
            "payloadType": 1,
            "pathLength": 1,
            "payload": {
                "decoded": {
                    "type": 1,
                    "destinationHash": "CD",
                    "sourceHash": "AB",
                    "cipherMac": "0000",
                    "ciphertext": "",
                    "tag": 0,
                    "decrypted": {
                        "content": {
                            "node_public_key": PUB_KEY,
                            "battery_voltage": 3.7,
                            "battery_percentage": 85,
                        }
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "battery"
        assert pl["battery_voltage"] == 3.7
        assert pl["battery_percentage"] == 85

    def test_response_with_telemetry_routes_to_telemetry(self) -> None:
        raw = "resp2"
        decoded = {
            "payloadType": 1,
            "pathLength": 1,
            "payload": {
                "decoded": {
                    "type": 1,
                    "destinationHash": "CD",
                    "sourceHash": "AB",
                    "cipherMac": "0000",
                    "ciphertext": "",
                    "tag": 0,
                    "decrypted": {
                        "content": {
                            "node_public_key": PUB_KEY,
                            "parsed_data": {"temperature": 22.5, "humidity": 60},
                        }
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "telemetry_response"
        assert pl["node_public_key"] == PUB_KEY
        assert pl["parsed_data"]["temperature"] == 22.5

    def test_response_with_status_routes_to_status_response(self) -> None:
        raw = "resp3"
        decoded = {
            "payloadType": 1,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 1,
                    "destinationHash": "CD",
                    "sourceHash": "AB",
                    "cipherMac": "0000",
                    "ciphertext": "",
                    "tag": 0,
                    "decrypted": {
                        "content": {
                            "status": "running",
                            "uptime": 86400,
                            "message_count": 42,
                        }
                    },
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "status_response"
        assert pl["status"] == "running"
        assert pl["uptime"] == 86400
        assert pl["message_count"] == 42


class TestAckPacket:
    def test_ack_falls_through_to_letsmesh_packet(self) -> None:
        raw = "ack1"
        decoded = {
            "payloadType": 3,
            "pathLength": 0,
            "payload": {
                "decoded": {
                    "type": 3,
                    "checksum": "AABBCCDD",
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "letsmesh_packet"
        assert pl["decoded_payload_type"] == 3
        assert pl["decoded_packet"]["payloadType"] == 3


class TestRequestPacket:
    def test_request_without_decrypted_content_falls_through(self) -> None:
        raw = "req1"
        decoded = {
            "payloadType": 0,
            "pathLength": 1,
            "payload": {
                "decoded": {
                    "type": 0,
                    "destinationHash": "CD",
                    "sourceHash": "AB",
                    "cipherMac": "0000",
                    "ciphertext": "AABB",
                    "timestamp": 1700000000,
                    "requestType": 1,
                }
            },
        }
        decoder = _make_decoder({raw: decoded})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "packets",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": raw})
        assert result is not None
        _, event_type, pl = result
        assert event_type == "letsmesh_packet"
        assert pl["decoded_payload_type"] == 0


class TestUnrecognizedFeed:
    def test_unknown_feed_type_returns_none(self) -> None:
        decoder = _make_decoder({})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = (
            OBSERVER_KEY,
            "unknown",
        )

        result = norm._normalize_letsmesh_event("t", {"raw": "FF"})
        assert result is None

    def test_unparseable_topic_returns_none(self) -> None:
        decoder = _make_decoder({})
        norm = _TestNormalizer(decoder)
        norm.mqtt.topic_builder.parse_letsmesh_upload_topic.return_value = None

        result = norm._normalize_letsmesh_event("garbage", {})
        assert result is None
