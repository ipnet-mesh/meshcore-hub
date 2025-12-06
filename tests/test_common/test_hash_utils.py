"""Tests for hash utilities for event deduplication."""

from datetime import datetime, timezone

from meshcore_hub.common.hash_utils import (
    compute_advertisement_hash,
    compute_message_hash,
    compute_telemetry_hash,
    compute_trace_hash,
)


class TestComputeMessageHash:
    """Tests for compute_message_hash function."""

    def test_same_content_produces_same_hash(self) -> None:
        """Identical messages should produce the same hash."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        hash1 = compute_message_hash(
            text="Hello World",
            pubkey_prefix="01ab2186c4d5",
            channel_idx=4,
            sender_timestamp=timestamp,
            txt_type=1,
        )
        hash2 = compute_message_hash(
            text="Hello World",
            pubkey_prefix="01ab2186c4d5",
            channel_idx=4,
            sender_timestamp=timestamp,
            txt_type=1,
        )

        assert hash1 == hash2

    def test_different_text_produces_different_hash(self) -> None:
        """Messages with different text should have different hashes."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        hash1 = compute_message_hash(
            text="Hello World",
            pubkey_prefix="01ab2186c4d5",
            sender_timestamp=timestamp,
        )
        hash2 = compute_message_hash(
            text="Goodbye World",
            pubkey_prefix="01ab2186c4d5",
            sender_timestamp=timestamp,
        )

        assert hash1 != hash2

    def test_different_sender_produces_different_hash(self) -> None:
        """Messages from different senders should have different hashes."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        hash1 = compute_message_hash(
            text="Hello",
            pubkey_prefix="01ab2186c4d5",
            sender_timestamp=timestamp,
        )
        hash2 = compute_message_hash(
            text="Hello",
            pubkey_prefix="99ff8877aabb",
            sender_timestamp=timestamp,
        )

        assert hash1 != hash2

    def test_different_channel_produces_different_hash(self) -> None:
        """Messages on different channels should have different hashes."""
        hash1 = compute_message_hash(text="Hello", channel_idx=1)
        hash2 = compute_message_hash(text="Hello", channel_idx=2)

        assert hash1 != hash2

    def test_handles_none_values(self) -> None:
        """Hash function should handle None values gracefully."""
        hash1 = compute_message_hash(
            text="Test",
            pubkey_prefix=None,
            channel_idx=None,
            sender_timestamp=None,
            txt_type=None,
        )

        assert hash1 is not None
        assert len(hash1) == 32  # MD5 hex digest length


class TestComputeAdvertisementHash:
    """Tests for compute_advertisement_hash function."""

    def test_same_content_same_bucket_produces_same_hash(self) -> None:
        """Advertisements within the same time bucket should match."""
        # Two times within the same 5-minute (300 second) bucket
        time1 = datetime(2024, 1, 15, 10, 31, 0, tzinfo=timezone.utc)
        time2 = datetime(2024, 1, 15, 10, 33, 0, tzinfo=timezone.utc)

        hash1 = compute_advertisement_hash(
            public_key="a" * 64,
            name="Node1",
            adv_type="chat",
            flags=128,
            received_at=time1,
            bucket_seconds=300,  # 5 minutes
        )
        hash2 = compute_advertisement_hash(
            public_key="a" * 64,
            name="Node1",
            adv_type="chat",
            flags=128,
            received_at=time2,
            bucket_seconds=300,  # 5 minutes
        )

        assert hash1 == hash2

    def test_different_bucket_produces_different_hash(self) -> None:
        """Advertisements in different time buckets should not match."""
        # Two times in different 5-minute (300 second) buckets
        time1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        time2 = datetime(2024, 1, 15, 10, 36, 0, tzinfo=timezone.utc)

        hash1 = compute_advertisement_hash(
            public_key="a" * 64,
            name="Node1",
            received_at=time1,
            bucket_seconds=300,  # 5 minutes
        )
        hash2 = compute_advertisement_hash(
            public_key="a" * 64,
            name="Node1",
            received_at=time2,
            bucket_seconds=300,  # 5 minutes
        )

        assert hash1 != hash2

    def test_different_public_key_produces_different_hash(self) -> None:
        """Advertisements from different nodes should have different hashes."""
        time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        hash1 = compute_advertisement_hash(
            public_key="a" * 64,
            received_at=time,
        )
        hash2 = compute_advertisement_hash(
            public_key="b" * 64,
            received_at=time,
        )

        assert hash1 != hash2

    def test_configurable_bucket_size(self) -> None:
        """Bucket size should be configurable."""
        time1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        time2 = datetime(2024, 1, 15, 10, 35, 0, tzinfo=timezone.utc)

        # With 5-minute (300s) bucket, these should be in different buckets
        hash1_5min = compute_advertisement_hash(
            public_key="a" * 64,
            received_at=time1,
            bucket_seconds=300,  # 5 minutes
        )
        hash2_5min = compute_advertisement_hash(
            public_key="a" * 64,
            received_at=time2,
            bucket_seconds=300,  # 5 minutes
        )
        assert hash1_5min != hash2_5min

        # With 10-minute (600s) bucket, these should be in the same bucket
        hash1_10min = compute_advertisement_hash(
            public_key="a" * 64,
            received_at=time1,
            bucket_seconds=600,  # 10 minutes
        )
        hash2_10min = compute_advertisement_hash(
            public_key="a" * 64,
            received_at=time2,
            bucket_seconds=600,  # 10 minutes
        )
        assert hash1_10min == hash2_10min


class TestComputeTraceHash:
    """Tests for compute_trace_hash function."""

    def test_same_tag_produces_same_hash(self) -> None:
        """Same initiator_tag should produce same hash."""
        hash1 = compute_trace_hash(initiator_tag=123456789)
        hash2 = compute_trace_hash(initiator_tag=123456789)

        assert hash1 == hash2

    def test_different_tag_produces_different_hash(self) -> None:
        """Different initiator_tag should produce different hash."""
        hash1 = compute_trace_hash(initiator_tag=123456789)
        hash2 = compute_trace_hash(initiator_tag=987654321)

        assert hash1 != hash2


class TestComputeTelemetryHash:
    """Tests for compute_telemetry_hash function."""

    def test_same_content_same_bucket_produces_same_hash(self) -> None:
        """Telemetry within the same time bucket should match."""
        time1 = datetime(2024, 1, 15, 10, 31, 0, tzinfo=timezone.utc)
        time2 = datetime(2024, 1, 15, 10, 33, 0, tzinfo=timezone.utc)
        data = {"temperature": 22.5, "humidity": 65}

        hash1 = compute_telemetry_hash(
            node_public_key="a" * 64,
            parsed_data=data,
            received_at=time1,
            bucket_seconds=300,  # 5 minutes
        )
        hash2 = compute_telemetry_hash(
            node_public_key="a" * 64,
            parsed_data=data,
            received_at=time2,
            bucket_seconds=300,  # 5 minutes
        )

        assert hash1 == hash2

    def test_different_data_produces_different_hash(self) -> None:
        """Different sensor readings should produce different hashes."""
        time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        hash1 = compute_telemetry_hash(
            node_public_key="a" * 64,
            parsed_data={"temperature": 22.5},
            received_at=time,
        )
        hash2 = compute_telemetry_hash(
            node_public_key="a" * 64,
            parsed_data={"temperature": 25.0},
            received_at=time,
        )

        assert hash1 != hash2

    def test_deterministic_dict_serialization(self) -> None:
        """Dict serialization should be deterministic regardless of key order."""
        time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Same data, different key order in source dicts
        data1 = {"a": 1, "b": 2, "c": 3}
        data2 = {"c": 3, "a": 1, "b": 2}

        hash1 = compute_telemetry_hash(
            node_public_key="a" * 64,
            parsed_data=data1,
            received_at=time,
        )
        hash2 = compute_telemetry_hash(
            node_public_key="a" * 64,
            parsed_data=data2,
            received_at=time,
        )

        assert hash1 == hash2
