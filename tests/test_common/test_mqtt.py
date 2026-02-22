"""Tests for MQTT topic parsing utilities."""

from meshcore_hub.common.mqtt import TopicBuilder


class TestTopicBuilder:
    """Tests for MQTT topic builder parsing helpers."""

    def test_parse_event_topic_with_single_segment_prefix(self) -> None:
        """Event topics are parsed correctly with a simple prefix."""
        builder = TopicBuilder(prefix="meshcore")

        parsed = builder.parse_event_topic(
            "meshcore/ABCDEF1234567890/event/advertisement"
        )

        assert parsed == ("ABCDEF1234567890", "advertisement")

    def test_parse_event_topic_with_multi_segment_prefix(self) -> None:
        """Event topics are parsed correctly with a slash-delimited prefix."""
        builder = TopicBuilder(prefix="meshcore/BOS")

        parsed = builder.parse_event_topic(
            "meshcore/BOS/ABCDEF1234567890/event/channel_msg_recv"
        )

        assert parsed == ("ABCDEF1234567890", "channel_msg_recv")

    def test_parse_command_topic_with_multi_segment_prefix(self) -> None:
        """Command topics are parsed correctly with a slash-delimited prefix."""
        builder = TopicBuilder(prefix="meshcore/BOS")

        parsed = builder.parse_command_topic(
            "meshcore/BOS/ABCDEF123456/command/send_msg"
        )

        assert parsed == ("ABCDEF123456", "send_msg")

    def test_parse_letsmesh_upload_topic(self) -> None:
        """LetsMesh upload topics map to public key and feed type."""
        builder = TopicBuilder(prefix="meshcore/BOS")

        parsed = builder.parse_letsmesh_upload_topic(
            "meshcore/BOS/ABCDEF1234567890/status"
        )

        assert parsed == ("ABCDEF1234567890", "status")

    def test_parse_letsmesh_upload_topic_rejects_unknown_feed(self) -> None:
        """Unknown LetsMesh feed topics are rejected."""
        builder = TopicBuilder(prefix="meshcore/BOS")

        parsed = builder.parse_letsmesh_upload_topic(
            "meshcore/BOS/ABCDEF1234567890/something_else"
        )

        assert parsed is None
