"""Tests for MQTT topic parsing utilities."""

import logging
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from meshcore_hub.common.mqtt import MQTTClient, MQTTConfig, TopicBuilder


class TestTopicBuilder:
    """Tests for MQTT topic builder parsing helpers."""

    def test_parse_event_topic_with_single_segment_prefix(self) -> None:
        """Event topics are parsed correctly with a simple prefix."""
        builder = TopicBuilder(prefix="meshcore")

        parsed = builder.parse_event_topic(
            "meshcore/ABCDEF1234567890/event/advertisement"
        )

        assert parsed == ("abcdef1234567890", "advertisement")

    def test_parse_event_topic_with_multi_segment_prefix(self) -> None:
        """Event topics are parsed correctly with a slash-delimited prefix."""
        builder = TopicBuilder(prefix="meshcore/BOS")

        parsed = builder.parse_event_topic(
            "meshcore/BOS/ABCDEF1234567890/event/channel_msg_recv"
        )

        assert parsed == ("abcdef1234567890", "channel_msg_recv")

    def test_parse_command_topic_with_multi_segment_prefix(self) -> None:
        """Command topics are parsed correctly with a slash-delimited prefix."""
        builder = TopicBuilder(prefix="meshcore/BOS")

        parsed = builder.parse_command_topic(
            "meshcore/BOS/ABCDEF123456/command/send_msg"
        )

        assert parsed == ("abcdef123456", "send_msg")

    def test_parse_letsmesh_upload_topic(self) -> None:
        """LetsMesh upload topics map to public key and feed type."""
        builder = TopicBuilder(prefix="meshcore")

        parsed = builder.parse_letsmesh_upload_topic(
            "meshcore/STN/ABCDEF1234567890/status"
        )

        assert parsed == ("abcdef1234567890", "status")

    def test_parse_letsmesh_upload_topic_rejects_unknown_feed(self) -> None:
        """Unknown LetsMesh feed topics are rejected."""
        builder = TopicBuilder(prefix="meshcore")

        parsed = builder.parse_letsmesh_upload_topic(
            "meshcore/STN/ABCDEF1234567890/something_else"
        )

        assert parsed is None


class TestMQTTClient:
    """Tests for the MQTTClient wrapper (keepalive, SUBACK, resubscribe)."""

    @pytest.fixture
    def wired(self) -> tuple[MQTTClient, MagicMock]:
        """Create an MQTTClient whose paho client is a MagicMock."""
        instance = MQTTClient(MQTTConfig())
        paho_mock = MagicMock()
        instance._client = paho_mock
        return instance, paho_mock

    def test_apply_socket_keepalive_sets_sockopts(
        self, wired: tuple[MQTTClient, MagicMock]
    ) -> None:
        """TCP keepalive options are applied to the active socket."""
        client, paho_mock = wired
        sock = MagicMock()
        paho_mock.socket.return_value = sock

        client._apply_socket_keepalive()

        assert sock.setsockopt.call_args_list == [
            call(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            call(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60),
            call(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30),
            call(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3),
        ]

    def test_apply_socket_keepalive_without_socket(
        self, wired: tuple[MQTTClient, MagicMock]
    ) -> None:
        """Missing socket (not yet connected) is tolerated silently."""
        client, paho_mock = wired
        paho_mock.socket.return_value = None

        client._apply_socket_keepalive()  # must not raise

        paho_mock.socket.assert_called_once()

    def test_apply_socket_keepalive_swallows_oserror(
        self, wired: tuple[MQTTClient, MagicMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        """OSError from setsockopt is swallowed (best-effort)."""
        client, paho_mock = wired
        sock = MagicMock()
        sock.setsockopt.side_effect = OSError("unsupported")
        paho_mock.socket.return_value = sock

        with caplog.at_level(logging.DEBUG, logger="meshcore_hub.common.mqtt"):
            client._apply_socket_keepalive()  # must not raise

        assert any("TCP keepalive" in r.message for r in caplog.records)

    def test_on_connect_applies_keepalive_and_resubscribes_with_qos(
        self, wired: tuple[MQTTClient, MagicMock]
    ) -> None:
        """Successful CONNACK enables keepalive and resubscribes at stored QoS."""
        client, paho_mock = wired
        client.subscribe("meshcore/+/+/packets", handler=lambda *a: None, qos=1)
        client.subscribe("meshcore/+/+/status", handler=lambda *a: None, qos=1)
        paho_mock.subscribe.reset_mock()
        paho_mock.socket.return_value = MagicMock()

        client._on_connect(paho_mock, None, None, 0)

        assert client.is_connected is True
        assert paho_mock.socket.return_value.setsockopt.call_count >= 1
        assert paho_mock.subscribe.call_args_list == [
            call("meshcore/+/+/packets", 1),
            call("meshcore/+/+/status", 1),
        ]

    def test_on_connect_failure_stays_disconnected(
        self, wired: tuple[MQTTClient, MagicMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Refused CONNACK keeps the client disconnected and logs an error."""
        client, paho_mock = wired

        client._on_connect(paho_mock, None, None, SimpleNamespace(value=135))

        assert client.is_connected is False
        paho_mock.subscribe.assert_not_called()
        assert any("Failed to connect" in r.message for r in caplog.records)

    def test_apply_socket_keepalive_unwraps_websocket_wrapper(
        self, wired: tuple[MQTTClient, MagicMock]
    ) -> None:
        """Keepalive is applied to the raw socket inside paho's websocket wrapper."""
        client, paho_mock = wired
        raw_sock = MagicMock()
        wrapper = MagicMock(spec=["recv", "send", "close", "_socket"])
        wrapper._socket = raw_sock
        paho_mock.socket.return_value = wrapper

        client._apply_socket_keepalive()

        assert raw_sock.setsockopt.call_args_list == [
            call(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            call(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60),
            call(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30),
            call(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3),
        ]

    def test_apply_socket_keepalive_wrapper_without_raw_socket(
        self, wired: tuple[MQTTClient, MagicMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        """A wrapper exposing no raw socket is skipped without raising."""
        client, paho_mock = wired
        wrapper = MagicMock(spec=["recv", "send", "close"])
        paho_mock.socket.return_value = wrapper

        with caplog.at_level(logging.DEBUG, logger="meshcore_hub.common.mqtt"):
            client._apply_socket_keepalive()  # must not raise

        assert any("setsockopt" in r.message for r in caplog.records)

    def test_on_subscribe_granted_is_debug_only(
        self, wired: tuple[MQTTClient, MagicMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Granted SUBACKs are logged at DEBUG, not ERROR."""
        client, paho_mock = wired
        with caplog.at_level(logging.DEBUG, logger="meshcore_hub.common.mqtt"):
            client._on_subscribe(
                paho_mock, None, mid=7, reason_code_list=[SimpleNamespace(value=0)]
            )

        assert not any(r.levelno == logging.ERROR for r in caplog.records)
        assert any("acknowledged" in r.message for r in caplog.records)

    def test_on_subscribe_refusal_logs_error(
        self, wired: tuple[MQTTClient, MagicMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        """A 0x80 SUBACK refusal is surfaced as an ERROR log."""
        client, paho_mock = wired
        client._on_subscribe(
            paho_mock, None, mid=7, reason_code_list=[SimpleNamespace(value=0x80)]
        )

        assert any(
            r.levelno == logging.ERROR and "refused" in r.message
            for r in caplog.records
        )

    def test_on_subscribe_accepts_plain_int_reason_code(
        self, wired: tuple[MQTTClient, MagicMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        """A bare int reason code (defensive path) is handled."""
        client, paho_mock = wired
        client._on_subscribe(paho_mock, None, mid=1, reason_code_list=0x80)

        assert any(
            r.levelno == logging.ERROR and "refused" in r.message
            for r in caplog.records
        )

    def test_subscribe_records_qos_for_resubscribe(
        self, wired: tuple[MQTTClient, MagicMock]
    ) -> None:
        """Registered QoS is stored and removed with the subscription."""
        client, _ = wired
        client.subscribe("meshcore/+/+/packets", handler=lambda *a: None, qos=1)

        assert client._topic_qos == {"meshcore/+/+/packets": 1}

        client.unsubscribe("meshcore/+/+/packets")

        assert client._topic_qos == {}
