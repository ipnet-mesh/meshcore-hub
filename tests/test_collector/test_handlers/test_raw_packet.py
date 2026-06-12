"""Tests for the raw packet capture handler."""

from sqlalchemy import select

from meshcore_hub.collector.handlers.raw_packet import store_raw_packet
from meshcore_hub.common.models import Node, RawPacket


def _channel_decoded() -> dict:
    """Decoder output resembling a channel-message packet on channel 0x2A."""
    return {
        "payloadType": 4,
        "routeType": 1,
        "pathLength": 2,
        "payload": {
            "decoded": {
                "channelHash": "2A",
                "sourceHash": "01AB2186C4D5EE",
            }
        },
    }


class TestStoreRawPacket:
    """Tests for store_raw_packet."""

    def test_captures_one_row(self, db_manager, db_session):
        """A single packet writes exactly one raw_packets row."""
        payload = {"raw": "0011223344", "hash": "deadbeef", "SNR": 9.5, "path": "0102"}

        store_raw_packet(
            "a" * 64, payload, _channel_decoded(), "channel_msg_recv", db_manager
        )

        rows = db_session.execute(select(RawPacket)).scalars().all()
        assert len(rows) == 1
        rp = rows[0]
        assert rp.raw_hex == "0011223344"
        assert rp.packet_hash == "deadbeef"
        assert rp.event_type == "channel_msg_recv"
        assert rp.snr == 9.5

    def test_derives_channel_idx_and_source_prefix(self, db_manager, db_session):
        """channel_idx from channelHash; source prefix from sourceHash."""
        payload = {"raw": "00", "hash": "h1"}

        store_raw_packet(
            "a" * 64, payload, _channel_decoded(), "channel_msg_recv", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.channel_idx == 0x2A  # 42
        assert rp.source_pubkey_prefix == "01AB2186C4D5"
        assert rp.route_type == "flood"
        assert rp.path_len == 2
        assert rp.payload_type == 4

    def test_no_dedup_one_row_per_observer(self, db_manager, db_session):
        """The same packet hash from two observers stores two rows."""
        payload = {"raw": "00", "hash": "shared"}

        store_raw_packet(
            "a" * 64, payload, _channel_decoded(), "channel_msg_recv", db_manager
        )
        store_raw_packet(
            "b" * 64, payload, _channel_decoded(), "channel_msg_recv", db_manager
        )

        rows = db_session.execute(select(RawPacket)).scalars().all()
        assert len(rows) == 2
        assert {r.packet_hash for r in rows} == {"shared"}

    def test_marks_observer_node(self, db_manager, db_session):
        """The observing node is created and flagged is_observer."""
        payload = {"raw": "00", "hash": "h1"}

        store_raw_packet(
            "c" * 64, payload, _channel_decoded(), "channel_msg_recv", db_manager
        )

        node = db_session.execute(
            select(Node).where(Node.public_key == "c" * 64)
        ).scalar_one()
        assert node.is_observer is True

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.observer_node_id == node.id

    def test_non_channel_packet_has_null_channel_idx(self, db_manager, db_session):
        """A packet with no channelHash stores channel_idx = None."""
        payload = {"raw": "00", "hash": "h1"}
        decoded = {"payloadType": 1, "payload": {"decoded": {"sourceHash": "AABBCCDD"}}}

        store_raw_packet("a" * 64, payload, decoded, "letsmesh_packet", db_manager)

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.channel_idx is None
        assert rp.source_pubkey_prefix == "AABBCCDD"[:12]


class TestStoreRawPacketEdges:
    """Cover the observer-update and sender-prefix fallback branches."""

    def test_existing_observer_node_updated(self, db_manager, db_session):
        """A pre-existing observer node is reused and marked is_observer."""
        existing = Node(public_key="d" * 64, is_observer=False, last_seen=None)
        db_session.add(existing)
        db_session.commit()

        store_raw_packet(
            "d" * 64,
            {"raw": "00", "hash": "h1"},
            _channel_decoded(),
            "channel_msg_recv",
            db_manager,
        )

        nodes = db_session.execute(select(Node)).scalars().all()
        assert len(nodes) == 1
        db_session.refresh(nodes[0])
        # The existing observer was reused, flag flipped, last_seen stamped.
        assert nodes[0].is_observer is True
        assert nodes[0].last_seen is not None

    def test_source_prefix_from_sender_public_key(self, db_manager, db_session):
        """source_pubkey_prefix falls back to senderPublicKey when no sourceHash."""
        decoded = {
            "payloadType": 1,
            "payload": {"decoded": {"senderPublicKey": "C1C2C3C4C5C6C7"}},
        }
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "req", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.source_pubkey_prefix == "C1C2C3C4C5C6"

    def test_no_source_prefix_when_absent(self, db_manager, db_session):
        """No sourceHash/senderPublicKey leaves source_pubkey_prefix NULL."""
        decoded = {"payloadType": 3, "payload": {"decoded": {}}}
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "ack", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.source_pubkey_prefix is None
