"""Tests for raw packet API routes."""

from datetime import datetime, timezone

import pytest

from meshcore_hub.common.models import Channel, Node, NodeTag, RawPacket


class TestListRawPackets:
    """Tests for GET /packets endpoint."""

    def test_list_empty(self, client_no_auth):
        response = client_no_auth.get("/api/v1/packets")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_with_data(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(
                raw_hex="0011",
                packet_hash="h1",
                event_type="letsmesh_packet",
                received_at=datetime.now(timezone.utc),
            )
        )
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/packets")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["raw_hex"] == "0011"
        assert item["redacted"] is False

    def test_filter_event_type(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(raw_hex="00", event_type="advertisement", received_at=now),
                RawPacket(raw_hex="11", event_type="channel_msg_recv", received_at=now),
            ]
        )
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/packets?event_type=advertisement")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == "advertisement"

    def test_filter_source_prefix_and_snr(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="00",
                    source_pubkey_prefix="AABBCCDDEEFF",
                    snr=10.0,
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="11",
                    source_pubkey_prefix="112233445566",
                    snr=2.0,
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/packets?pubkey_prefix=AABBCCDDEEFF&min_snr=5"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["source_pubkey_prefix"] == "AABBCCDDEEFF"

    def test_pagination_params_echoed(self, client_no_auth):
        response = client_no_auth.get("/api/v1/packets?limit=25&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 25
        assert data["offset"] == 5

    def test_filter_by_exact_packet_hash(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(raw_hex="00", packet_hash="HASH_AAA", received_at=now),
                RawPacket(raw_hex="11", packet_hash="HASH_AAA", received_at=now),
                RawPacket(raw_hex="22", packet_hash="HASH_BBB", received_at=now),
            ]
        )
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/packets?packet_hash=HASH_AAA")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert {i["packet_hash"] for i in data["items"]} == {"HASH_AAA"}


class TestRawPacketRedaction:
    """Tests for channel-visibility redaction of raw packets."""

    @pytest.fixture
    def packets_with_visibility(self, api_db_session):
        """Community-channel, admin-channel, and non-channel raw packets."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        pub_idx = int(Channel.compute_channel_hash(pub_key), 16)
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)

        api_db_session.add_all(
            [
                Channel(
                    name="CommunityCh",
                    key_hex=pub_key,
                    channel_hash=Channel.compute_channel_hash(pub_key),
                    visibility="community",
                    enabled=True,
                ),
                Channel(
                    name="AdminCh",
                    key_hex=adm_key,
                    channel_hash=Channel.compute_channel_hash(adm_key),
                    visibility="admin",
                    enabled=True,
                ),
            ]
        )
        now = datetime.now(timezone.utc)
        pub_pkt = RawPacket(
            raw_hex="C0FFEE",
            event_type="channel_msg_recv",
            channel_idx=pub_idx,
            decoded={"payload": {"decoded": {"channelHash": "x"}}},
            received_at=now,
        )
        adm_pkt = RawPacket(
            raw_hex="ADADAD",
            event_type="channel_msg_recv",
            channel_idx=adm_idx,
            decoded={"payload": {"decoded": {"channelHash": "y"}}},
            received_at=now,
        )
        plain_pkt = RawPacket(
            raw_hex="DEADBE",
            event_type="advertisement",
            channel_idx=None,
            received_at=now,
        )
        api_db_session.add_all([pub_pkt, adm_pkt, plain_pkt])
        api_db_session.commit()
        return pub_pkt, adm_pkt, plain_pkt

    def test_anonymous_redacts_admin_channel(
        self, client_no_auth, packets_with_visibility
    ):
        """Anonymous sees the admin-channel packet metadata-only (redacted)."""
        response = client_no_auth.get("/api/v1/packets")
        assert response.status_code == 200
        data = response.json()
        # All three rows are returned (count stable), but the admin one is redacted.
        assert data["total"] == 3
        adm = next(i for i in data["items"] if i["raw_hex"] is None)
        assert adm["redacted"] is True
        assert adm["decoded"] is None
        # Non-channel and community packets are not redacted.
        assert any(
            i["raw_hex"] == "DEADBE" and not i["redacted"] for i in data["items"]
        )
        assert any(
            i["raw_hex"] == "C0FFEE" and not i["redacted"] for i in data["items"]
        )

    def test_admin_sees_full(self, client_no_auth, packets_with_visibility):
        """Admin role sees the admin-channel packet in full."""
        response = client_no_auth.get(
            "/api/v1/packets", headers={"X-User-Roles": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert all(not i["redacted"] for i in data["items"])
        assert any(i["raw_hex"] == "ADADAD" for i in data["items"])

    def test_redacted_filter(self, client_no_auth, packets_with_visibility):
        """The redacted filter narrows to (only|excluding) redacted rows."""
        only = client_no_auth.get("/api/v1/packets?redacted=true").json()
        assert only["total"] == 1
        assert only["items"][0]["redacted"] is True

        without = client_no_auth.get("/api/v1/packets?redacted=false").json()
        assert without["total"] == 2
        assert all(not i["redacted"] for i in without["items"])

    def test_count_stable_across_roles(self, client_no_auth, packets_with_visibility):
        """Pagination count is the same regardless of role (rows redacted not hidden)."""
        anon = client_no_auth.get("/api/v1/packets").json()
        admin = client_no_auth.get(
            "/api/v1/packets", headers={"X-User-Roles": "admin"}
        ).json()
        assert anon["total"] == admin["total"] == 3

    def test_get_single_redacted(self, client_no_auth, packets_with_visibility):
        """GET /packets/{id} redacts an above-role channel packet (not 404)."""
        _, adm_pkt, _ = packets_with_visibility
        response = client_no_auth.get(f"/api/v1/packets/{adm_pkt.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["redacted"] is True
        assert data["raw_hex"] is None

    def test_get_single_visible_to_admin(self, client_no_auth, packets_with_visibility):
        _, adm_pkt, _ = packets_with_visibility
        response = client_no_auth.get(
            f"/api/v1/packets/{adm_pkt.id}", headers={"X-User-Roles": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["redacted"] is False
        assert data["raw_hex"] == "ADADAD"


class TestRawPacketFiltersAndHydration:
    """Cover the remaining filters, observer hydration, detail, and key builder."""

    def test_search_packet_type_channel_route(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA",
                    packet_hash="findme",
                    packet_type=5,
                    channel_idx=7,
                    route_type="flood",
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="BB",
                    packet_type=2,
                    channel_idx=9,
                    route_type="direct",
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        assert client_no_auth.get("/api/v1/packets?search=findme").json()["total"] == 1
        assert client_no_auth.get("/api/v1/packets?packet_type=5").json()["total"] == 1
        assert client_no_auth.get("/api/v1/packets?channel_idx=7").json()["total"] == 1
        assert (
            client_no_auth.get("/api/v1/packets?route_type=flood").json()["total"] == 1
        )
        assert client_no_auth.get("/api/v1/packets?route_type=all").json()["total"] == 2

    def test_snr_and_path_len_ranges(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", snr=1.0, path_len=1, received_at=now),
                RawPacket(raw_hex="BB", snr=9.0, path_len=5, received_at=now),
            ]
        )
        api_db_session.commit()

        assert client_no_auth.get("/api/v1/packets?max_snr=3").json()["total"] == 1
        assert client_no_auth.get("/api/v1/packets?min_path_len=3").json()["total"] == 1
        assert client_no_auth.get("/api/v1/packets?max_path_len=3").json()["total"] == 1

    def test_since_until_window(self, client_no_auth, api_db_session):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", received_at=old),
                RawPacket(raw_hex="BB", received_at=recent),
            ]
        )
        api_db_session.commit()

        ts = "2021-01-01T00:00:00+00:00"
        assert (
            client_no_auth.get("/api/v1/packets", params={"since": ts}).json()["total"]
            == 1
        )
        assert (
            client_no_auth.get("/api/v1/packets", params={"until": ts}).json()["total"]
            == 1
        )

    def test_decryptable_filter(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA",
                    decoded={"payload": {"decoded": {"decrypted": {"message": "hi"}}}},
                    received_at=now,
                ),
                RawPacket(raw_hex="BB", decoded={"payload": {}}, received_at=now),
            ]
        )
        api_db_session.commit()

        yes = client_no_auth.get("/api/v1/packets?decryptable=true").json()
        assert yes["total"] == 1
        assert yes["items"][0]["raw_hex"] == "AA"
        no = client_no_auth.get("/api/v1/packets?decryptable=false").json()
        assert no["total"] == 1
        assert no["items"][0]["raw_hex"] == "BB"

    def test_observer_hydration_and_filter(self, client_no_auth, api_db_session):
        obs_key = "ab" * 32  # Node lowercases its public key
        node = Node(public_key=obs_key, name="ObsNode")
        api_db_session.add(node)
        api_db_session.flush()
        api_db_session.add(NodeTag(node_id=node.id, key="name", value="TaggedObs"))
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                observer_node_id=node.id,
                received_at=datetime.now(timezone.utc),
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packets").json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["observed_by"] == obs_key
        assert item["observer_name"] == "ObsNode"
        assert item["observer_tag_name"] == "TaggedObs"

        # observed_by filter
        filtered = client_no_auth.get(
            "/api/v1/packets", params={"observed_by": obs_key}
        ).json()
        assert filtered["total"] == 1

    def test_sort_by_snr_ascending(self, client_no_auth, api_db_session):
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                RawPacket(raw_hex="LO", snr=1.0, received_at=now),
                RawPacket(raw_hex="HI", snr=9.0, received_at=now),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packets?sort=snr&order=asc").json()
        assert [i["raw_hex"] for i in data["items"]] == ["LO", "HI"]

    def test_get_detail_with_observer(self, client_no_auth, api_db_session):
        node = Node(public_key="M" * 64, name="DetailObs")
        api_db_session.add(node)
        api_db_session.flush()
        api_db_session.add(NodeTag(node_id=node.id, key="name", value="DetailTag"))
        pkt = RawPacket(
            raw_hex="AA",
            observer_node_id=node.id,
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add(pkt)
        api_db_session.commit()

        data = client_no_auth.get(f"/api/v1/packets/{pkt.id}").json()
        assert data["observer_tag_name"] == "DetailTag"

    def test_get_detail_404(self, client_no_auth):
        response = client_no_auth.get("/api/v1/packets/does-not-exist")
        assert response.status_code == 404

    def test_packets_key_builder_anonymous(self):
        from starlette.requests import Request

        from meshcore_hub.api.routes.raw_packets import _packets_key_builder

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "headers": [],
                "query_string": b"limit=50&sort=time",
            }
        )
        key = _packets_key_builder(request)
        assert key.startswith("packets:role=anonymous:")
        assert "limit=50" in key
