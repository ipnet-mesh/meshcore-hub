"""Tests for the raw packet capture handler."""

from sqlalchemy import select

from meshcore_hub.collector.handlers.raw_packet import (
    store_raw_packet,
    update_raw_packet_event_hash,
)
from meshcore_hub.common.models import Node, PacketPathHop, RawPacket


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

        rp_id = store_raw_packet(
            "a" * 64, payload, _channel_decoded(), "channel_msg_recv", db_manager
        )

        rows = db_session.execute(select(RawPacket)).scalars().all()
        assert len(rows) == 1
        rp = rows[0]
        assert rp.raw_hex == "0011223344"
        assert rp.packet_hash == "deadbeef"
        assert rp.event_type == "channel_msg_recv"
        assert rp.snr == 9.5
        assert rp_id == rp.id

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


class TestStoreRawPacketPathHashBytes:
    """Tests for path_hash_bytes computation at ingest."""

    def test_top_level_path_max_byte_width(self, db_manager, db_session):
        """Mixed-width hashes in decoded.path persist the widest byte width."""
        decoded = {
            "payloadType": 1,
            "path": ["aa", "aabbcc"],
            "pathLength": 2,
            "payload": {"decoded": {"sourceHash": "AABBCCDD"}},
        }
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "flood", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.path_hash_bytes == 3

    def test_trace_fallback_path_hashes(self, db_manager, db_session):
        """Trace-style pathHashes in payload.decoded are used as fallback."""
        decoded = {
            "payloadType": 1,
            "payload": {"decoded": {"pathHashes": ["aabb", "ccdd"]}},
        }
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "trace", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.path_hash_bytes == 2

    def test_one_byte_path(self, db_manager, db_session):
        """Single-byte hashes persist width 1."""
        decoded = {
            "payloadType": 1,
            "path": ["aa", "bb"],
            "payload": {"decoded": {}},
        }
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "flood", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.path_hash_bytes == 1

    def test_no_path_returns_none(self, db_manager, db_session):
        """No path hashes at all persist path_hash_bytes = None."""
        decoded = {"payloadType": 3, "payload": {"decoded": {}}}
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "ack", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.path_hash_bytes is None

    def test_null_decoded_returns_none(self, db_manager, db_session):
        """A None decoded_packet leaves path_hash_bytes as None."""
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, None, "unknown", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.path_hash_bytes is None

    def test_path_len_still_persisted(self, db_manager, db_session):
        """path_len is still persisted alongside path_hash_bytes."""
        decoded = {
            "payloadType": 1,
            "path": ["aa", "bb", "cc"],
            "pathLength": 3,
            "payload": {"decoded": {"sourceHash": "AABBCCDD"}},
        }
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "flood", db_manager
        )

        rp = db_session.execute(select(RawPacket)).scalar_one()
        assert rp.path_len == 3
        assert rp.path_hash_bytes == 1


class TestStoreRawPacketPathHops:
    """Tests for packet_path_hops insertion at ingest."""

    def test_hops_inserted_with_positions(self, db_manager, db_session):
        """Each path hash becomes a hop with the correct position and hash."""
        decoded = {
            "payloadType": 1,
            "path": ["aa", "bbcc", "dd"],
            "payload": {"decoded": {}},
        }
        store_raw_packet(
            "a" * 64,
            {"raw": "00", "hash": "pkt1"},
            decoded,
            "flood",
            db_manager,
        )

        hops = (
            db_session.execute(select(PacketPathHop).order_by(PacketPathHop.position))
            .scalars()
            .all()
        )
        assert len(hops) == 3
        assert [h.position for h in hops] == [0, 1, 2]
        assert [h.node_hash for h in hops] == ["AA", "BBCC", "DD"]
        assert all(h.packet_hash == "pkt1" for h in hops)

    def test_hops_skipped_when_path_absent(self, db_manager, db_session):
        """No path hashes means zero hop rows."""
        decoded = {"payloadType": 3, "payload": {"decoded": {}}}
        store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "h1"}, decoded, "ack", db_manager
        )

        hops = db_session.execute(select(PacketPathHop)).scalars().all()
        assert len(hops) == 0

    def test_observer_node_id_denormalized(self, db_manager, db_session):
        """The observer node ID is denormalized onto each hop row."""
        decoded = {
            "payloadType": 1,
            "path": ["aa", "bb"],
            "payload": {"decoded": {}},
        }
        store_raw_packet(
            "c" * 64,
            {"raw": "00", "hash": "pkt2"},
            decoded,
            "flood",
            db_manager,
        )

        node = db_session.execute(
            select(Node).where(Node.public_key == "c" * 64)
        ).scalar_one()

        hops = db_session.execute(select(PacketPathHop)).scalars().all()
        assert len(hops) == 2
        assert all(h.observer_node_id == node.id for h in hops)

    def test_hops_trace_fallback(self, db_manager, db_session):
        """Trace-style pathHashes in payload.decoded produce hops too."""
        decoded = {
            "payloadType": 1,
            "payload": {"decoded": {"pathHashes": ["aabb", "ccdd"]}},
        }
        store_raw_packet(
            "a" * 64,
            {"raw": "00", "hash": "pkt3"},
            decoded,
            "trace",
            db_manager,
        )

        hops = (
            db_session.execute(select(PacketPathHop).order_by(PacketPathHop.position))
            .scalars()
            .all()
        )
        assert len(hops) == 2
        assert [h.node_hash for h in hops] == ["AABB", "CCDD"]


class TestUpdateRawPacketEventHash:
    """Tests for the post-dispatch event_hash backfill."""

    def test_backfills_raw_packet_and_hops(self, db_manager, db_session):
        """update_raw_packet_event_hash writes event_hash onto both rows."""
        decoded = {
            "payloadType": 1,
            "path": ["aa", "bb"],
            "payload": {"decoded": {}},
        }
        rp_id = store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "wire1"}, decoded, "flood", db_manager
        )
        assert rp_id is not None

        update_raw_packet_event_hash(rp_id, "evt-aaa", db_manager)

        rp = db_session.execute(select(RawPacket)).scalar_one()
        db_session.refresh(rp)
        assert rp.event_hash == "evt-aaa"

        hops = db_session.execute(select(PacketPathHop)).scalars().all()
        assert len(hops) == 2
        for hop in hops:
            db_session.refresh(hop)
            assert hop.event_hash == "evt-aaa"

    def test_backfill_idempotent_on_replay(self, db_manager, db_session):
        """Calling backfill twice with the same hash is a no-op."""
        decoded = {"payloadType": 1, "path": ["aa"], "payload": {"decoded": {}}}
        rp_id = store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "wire1"}, decoded, "flood", db_manager
        )
        assert rp_id is not None

        update_raw_packet_event_hash(rp_id, "evt-aaa", db_manager)
        update_raw_packet_event_hash(rp_id, "evt-aaa", db_manager)

        rp = db_session.execute(select(RawPacket)).scalar_one()
        db_session.refresh(rp)
        assert rp.event_hash == "evt-aaa"

    def test_backfill_overwrites_prior_value(self, db_manager, db_session):
        """A second backfill with a different hash replaces the prior one."""
        decoded = {"payloadType": 1, "path": ["aa"], "payload": {"decoded": {}}}
        rp_id = store_raw_packet(
            "a" * 64, {"raw": "00", "hash": "wire1"}, decoded, "flood", db_manager
        )
        assert rp_id is not None

        update_raw_packet_event_hash(rp_id, "evt-first", db_manager)
        update_raw_packet_event_hash(rp_id, "evt-second", db_manager)

        rp = db_session.execute(select(RawPacket)).scalar_one()
        db_session.refresh(rp)
        assert rp.event_hash == "evt-second"

    def test_backfill_no_op_when_row_missing(self, db_manager, db_session):
        """Backfilling a non-existent id silently does nothing (retention
        cleanup may have removed the row between capture and dispatch)."""
        # No row created; just verify it doesn't raise.
        update_raw_packet_event_hash("nonexistent-id", "evt-aaa", db_manager)

        assert db_session.execute(select(RawPacket)).scalars().all() == []
