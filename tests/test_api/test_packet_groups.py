"""Tests for GET /api/v1/packet-groups endpoints."""

from datetime import datetime, timezone

import pytest

from meshcore_hub.common.models import Channel, Node, NodeTag, PacketPathHop, RawPacket


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestListPacketGroups:
    """Tests for GET /packet-groups (grouped list)."""

    def test_empty_db(self, client_no_auth):
        response = client_no_auth.get("/api/v1/packet-groups")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_null_hash_rows_excluded(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(raw_hex="AA", packet_hash=None, received_at=_now())
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        assert data["total"] == 0

    def test_single_group(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA",
                    packet_hash="H1",
                    event_type="advertisement",
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="BB",
                    packet_hash="H1",
                    event_type="advertisement",
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["packet_hash"] == "H1"
        assert item["reception_count"] == 2
        assert item["event_type"] == "advertisement"

    def test_multiple_groups(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", packet_hash="H1", received_at=now),
                RawPacket(raw_hex="BB", packet_hash="H1", received_at=now),
                RawPacket(raw_hex="CC", packet_hash="H2", received_at=now),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        assert data["total"] == 2
        hashes = {i["packet_hash"] for i in data["items"]}
        assert hashes == {"H1", "H2"}

    def test_observer_count(self, client_no_auth, api_db_session):
        now = _now()
        obs1 = Node(public_key="a" * 64)
        obs2 = Node(public_key="b" * 64)
        api_db_session.add_all([obs1, obs2])
        api_db_session.flush()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA",
                    packet_hash="H1",
                    observer_node_id=obs1.id,
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="BB",
                    packet_hash="H1",
                    observer_node_id=obs2.id,
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="CC",
                    packet_hash="H1",
                    observer_node_id=obs1.id,
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        item = data["items"][0]
        assert item["reception_count"] == 3
        assert item["observer_count"] == 2

    def test_filter_event_type(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA", packet_hash="H1", event_type="advert", received_at=now
                ),
                RawPacket(
                    raw_hex="BB", packet_hash="H2", event_type="path", received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?event_type=advert").json()
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == "advert"

    def test_filter_channel_idx(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA", packet_hash="H1", channel_idx=7, received_at=now
                ),
                RawPacket(
                    raw_hex="BB", packet_hash="H2", channel_idx=9, received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?channel_idx=7").json()
        assert data["total"] == 1
        assert data["items"][0]["channel_idx"] == 7

    def test_filter_search_by_hash(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", packet_hash="FINDME", received_at=now),
                RawPacket(raw_hex="BB", packet_hash="OTHER", received_at=now),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?search=FINDME").json()
        assert data["total"] == 1
        assert data["items"][0]["packet_hash"] == "FINDME"

    def test_since_filter(self, client_no_auth, api_db_session):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent = _now()
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", packet_hash="OLD", received_at=old),
                RawPacket(raw_hex="BB", packet_hash="NEW", received_at=recent),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get(
            "/api/v1/packet-groups", params={"since": "2021-01-01T00:00:00+00:00"}
        ).json()
        assert data["total"] == 1
        assert data["items"][0]["packet_hash"] == "NEW"

    def test_until_filter(self, client_no_auth, api_db_session):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent = _now()
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", packet_hash="OLD", received_at=old),
                RawPacket(raw_hex="BB", packet_hash="NEW", received_at=recent),
            ]
        )
        api_db_session.commit()

        # Pass explicit since to bypass the 7-day default window
        data = client_no_auth.get(
            "/api/v1/packet-groups",
            params={
                "since": "2019-01-01T00:00:00+00:00",
                "until": "2021-01-01T00:00:00+00:00",
            },
        ).json()
        assert data["total"] == 1
        assert data["items"][0]["packet_hash"] == "OLD"

    def test_sort_by_reception_count(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(raw_hex="A1", packet_hash="FEW", received_at=now),
                RawPacket(raw_hex="B1", packet_hash="MANY", received_at=now),
                RawPacket(raw_hex="B2", packet_hash="MANY", received_at=now),
                RawPacket(raw_hex="B3", packet_hash="MANY", received_at=now),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get(
            "/api/v1/packet-groups?sort=reception_count&order=desc"
        ).json()
        assert data["items"][0]["packet_hash"] == "MANY"
        assert data["items"][1]["packet_hash"] == "FEW"

    def test_sort_by_event_type(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA",
                    packet_hash="Z_HASH",
                    event_type="zzz",
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="BB",
                    packet_hash="A_HASH",
                    event_type="aaa",
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get(
            "/api/v1/packet-groups?sort=event_type&order=asc"
        ).json()
        assert data["items"][0]["event_type"] == "aaa"

    def test_pagination_params_echoed(self, client_no_auth):
        data = client_no_auth.get("/api/v1/packet-groups?limit=10&offset=5").json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_receptions_not_populated_in_list(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(raw_hex="AA", packet_hash="H1", received_at=_now())
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        assert data["items"][0]["receptions"] == []

    def test_raw_hex_and_decoded_not_in_list(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(
                raw_hex="DEADBEEF",
                packet_hash="H1",
                decoded={"foo": "bar"},
                received_at=_now(),
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        item = data["items"][0]
        assert item["raw_hex"] is None
        assert item["decoded"] is None

    def test_invalid_sort_defaults_to_time(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(raw_hex="AA", packet_hash="H1", received_at=_now())
        )
        api_db_session.commit()

        data = client_no_auth.get(
            "/api/v1/packet-groups?sort=bogus&order=invalid"
        ).json()
        assert data["total"] == 1

    def test_key_builder_role_aware(self):
        from starlette.requests import Request

        from meshcore_hub.api.routes.packet_groups import _group_key_builder

        req = Request(
            {
                "type": "http",
                "method": "GET",
                "headers": [],
                "query_string": b"limit=10",
            }
        )
        key = _group_key_builder(req)
        assert key.startswith("packet_groups:role=anonymous:")
        assert "limit=10" in key


class TestPathHashBytes:
    """Tests for the persisted path_hash_bytes field on the list endpoint."""

    def test_one_byte_path(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                packet_hash="H1",
                path_hash_bytes=1,
                received_at=_now(),
            )
        )
        api_db_session.commit()
        item = client_no_auth.get("/api/v1/packet-groups").json()["items"][0]
        assert item["path_hash_bytes"] == 1

    def test_two_byte_path(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                packet_hash="H1",
                path_hash_bytes=2,
                received_at=_now(),
            )
        )
        api_db_session.commit()
        item = client_no_auth.get("/api/v1/packet-groups").json()["items"][0]
        assert item["path_hash_bytes"] == 2

    def test_three_byte_path(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                packet_hash="H1",
                path_hash_bytes=3,
                received_at=_now(),
            )
        )
        api_db_session.commit()
        item = client_no_auth.get("/api/v1/packet-groups").json()["items"][0]
        assert item["path_hash_bytes"] == 3

    def test_width_aggregates_across_receptions(self, client_no_auth, api_db_session):
        """Width is observer-relative; take the widest across all receptions.

        The oldest reception (representative) carries no path, while a newer
        reception of the same packet saw a 2-byte path. The badge must reflect
        the widest path seen, not just the representative row.
        """
        base = _now()
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                packet_hash="H1",
                path_hash_bytes=None,
                received_at=base,
            )
        )
        api_db_session.add(
            RawPacket(
                raw_hex="BB",
                packet_hash="H1",
                path_hash_bytes=2,
                received_at=base.replace(microsecond=base.microsecond + 1),
            )
        )
        api_db_session.commit()
        item = client_no_auth.get("/api/v1/packet-groups").json()["items"][0]
        assert item["path_hash_bytes"] == 2

    def test_no_path_returns_none(self, client_no_auth, api_db_session):
        api_db_session.add(
            RawPacket(raw_hex="AA", packet_hash="H1", received_at=_now())
        )
        api_db_session.commit()
        item = client_no_auth.get("/api/v1/packet-groups").json()["items"][0]
        assert item["path_hash_bytes"] is None

    def test_redacted_path_width_hidden(self, client_no_auth, api_db_session):
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)
        api_db_session.add(
            Channel(
                name="Adm",
                key_hex=adm_key,
                channel_hash=Channel.compute_channel_hash(adm_key),
                visibility="admin",
                enabled=True,
            )
        )
        api_db_session.add(
            RawPacket(
                raw_hex="SECRET",
                packet_hash="ADM_HASH",
                channel_idx=adm_idx,
                path_hash_bytes=2,
                received_at=_now(),
            )
        )
        api_db_session.commit()
        item = client_no_auth.get("/api/v1/packet-groups").json()["items"][0]
        assert item["redacted"] is True
        assert item["path_hash_bytes"] is None


class TestPathHashBytesFilter:
    """Tests for the ?path_hash_bytes= query filter."""

    def test_filter_returns_only_matching_width(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="A", packet_hash="H1", path_hash_bytes=1, received_at=now
                ),
                RawPacket(
                    raw_hex="B", packet_hash="H2", path_hash_bytes=2, received_at=now
                ),
                RawPacket(
                    raw_hex="C", packet_hash="H3", path_hash_bytes=3, received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?path_hash_bytes=2").json()
        assert data["total"] == 1
        assert data["items"][0]["packet_hash"] == "H2"

    def test_filter_width_1(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="A", packet_hash="H1", path_hash_bytes=1, received_at=now
                ),
                RawPacket(
                    raw_hex="B", packet_hash="H2", path_hash_bytes=3, received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?path_hash_bytes=1").json()
        assert data["total"] == 1
        assert data["items"][0]["packet_hash"] == "H1"

    def test_filter_width_3(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="A", packet_hash="H1", path_hash_bytes=1, received_at=now
                ),
                RawPacket(
                    raw_hex="B", packet_hash="H2", path_hash_bytes=3, received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?path_hash_bytes=3").json()
        assert data["total"] == 1
        assert data["items"][0]["packet_hash"] == "H2"

    def test_no_filter_returns_all_including_null(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="A", packet_hash="H1", path_hash_bytes=1, received_at=now
                ),
                RawPacket(
                    raw_hex="B", packet_hash="H2", path_hash_bytes=None, received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups").json()
        assert data["total"] == 2
        widths = {i["path_hash_bytes"] for i in data["items"]}
        assert widths == {1, None}

    def test_filter_excludes_null_width(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="A", packet_hash="H1", path_hash_bytes=None, received_at=now
                ),
                RawPacket(
                    raw_hex="B", packet_hash="H2", path_hash_bytes=2, received_at=now
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?path_hash_bytes=2").json()
        assert data["total"] == 1
        assert data["items"][0]["path_hash_bytes"] == 2

    def test_filter_redacted_group_still_null(self, client_no_auth, api_db_session):
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)
        now = _now()
        api_db_session.add(
            Channel(
                name="Adm",
                key_hex=adm_key,
                channel_hash=Channel.compute_channel_hash(adm_key),
                visibility="admin",
                enabled=True,
            )
        )
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="SECRET",
                    packet_hash="ADM",
                    channel_idx=adm_idx,
                    path_hash_bytes=2,
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="OK",
                    packet_hash="PUB",
                    path_hash_bytes=2,
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups?path_hash_bytes=2").json()
        assert data["total"] == 2
        adm = next(i for i in data["items"] if i["packet_hash"] == "ADM")
        assert adm["redacted"] is True
        assert adm["path_hash_bytes"] is None


class TestGetPacketGroup:
    """Tests for GET /packet-groups/{hash} (detail)."""

    def test_404_for_unknown_hash(self, client_no_auth):
        response = client_no_auth.get("/api/v1/packet-groups/NOSUCHPACKET")
        assert response.status_code == 404

    def test_returns_all_receptions(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(raw_hex="AA", packet_hash="H1", received_at=now),
                RawPacket(raw_hex="BB", packet_hash="H1", received_at=now),
                RawPacket(raw_hex="CC", packet_hash="H1", received_at=now),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups/H1").json()
        assert data["packet_hash"] == "H1"
        assert data["reception_count"] == 3
        assert len(data["receptions"]) == 3

    def test_observer_hydration(self, client_no_auth, api_db_session):
        obs = Node(public_key="o" * 64, name="ObsName")
        api_db_session.add(obs)
        api_db_session.flush()
        api_db_session.add(NodeTag(node_id=obs.id, key="name", value="TaggedObs"))
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                packet_hash="H1",
                observer_node_id=obs.id,
                received_at=_now(),
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups/H1").json()
        r = data["receptions"][0]
        assert r["observed_by"] == "o" * 64
        assert r["observer_name"] == "ObsName"
        assert r["observer_tag_name"] == "TaggedObs"

    def test_path_hashes_from_hop_table(self, client_no_auth, api_db_session):
        """Path hashes are read from packet_path_hops, not decoded JSON."""
        rp = RawPacket(
            raw_hex="AA",
            packet_hash="H1",
            decoded={"payload": {"decoded": {"pathHashes": ["AA", "BB", "CC"]}}},
            path_len=3,
            received_at=_now(),
        )
        api_db_session.add(rp)
        api_db_session.flush()
        for pos, nh in enumerate(["AA", "BB", "CC"]):
            api_db_session.add(
                PacketPathHop(
                    raw_packet_id=rp.id,
                    position=pos,
                    node_hash=nh,
                    packet_hash="H1",
                    received_at=_now(),
                )
            )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups/H1").json()
        r = data["receptions"][0]
        assert r["path_hashes"] == ["AA", "BB", "CC"]
        assert r["path_len"] == 3

    def test_path_hashes_missing_returns_none(self, client_no_auth, api_db_session):
        """A raw_packet with no hop rows returns path_hashes=None."""
        api_db_session.add(
            RawPacket(
                raw_hex="AA",
                packet_hash="H1",
                decoded={"payload": {"decoded": {}}},
                received_at=_now(),
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups/H1").json()
        assert data["receptions"][0]["path_hashes"] is None

    def test_representative_raw_hex_and_decoded(self, client_no_auth, api_db_session):
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AABBCC",
                    packet_hash="H1",
                    decoded={"info": "first"},
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="DDEEFF",
                    packet_hash="H1",
                    decoded={"info": "second"},
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups/H1").json()
        assert data["raw_hex"] is not None
        assert data["decoded"] is not None

    def test_observer_count_distinct(self, client_no_auth, api_db_session):
        obs = Node(public_key="x" * 64)
        api_db_session.add(obs)
        api_db_session.flush()
        now = _now()
        # Same observer, two different paths
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="AA",
                    packet_hash="H1",
                    observer_node_id=obs.id,
                    path_len=2,
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="BB",
                    packet_hash="H1",
                    observer_node_id=obs.id,
                    path_len=3,
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/packet-groups/H1").json()
        assert data["reception_count"] == 2
        assert data["observer_count"] == 1


class TestPacketGroupRedaction:
    """Tests for channel-visibility redaction in packet groups."""

    @pytest.fixture
    def channel_packets(self, api_db_session):
        pub_key = "AABBCCDDEEFF00112233445566778899"
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        pub_idx = int(Channel.compute_channel_hash(pub_key), 16)
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)

        api_db_session.add_all(
            [
                Channel(
                    name="Pub",
                    key_hex=pub_key,
                    channel_hash=Channel.compute_channel_hash(pub_key),
                    visibility="community",
                    enabled=True,
                ),
                Channel(
                    name="Adm",
                    key_hex=adm_key,
                    channel_hash=Channel.compute_channel_hash(adm_key),
                    visibility="admin",
                    enabled=True,
                ),
            ]
        )
        now = _now()
        api_db_session.add_all(
            [
                RawPacket(
                    raw_hex="PUBLIC",
                    packet_hash="PUB_HASH",
                    channel_idx=pub_idx,
                    source_pubkey_prefix="AABBCC",
                    received_at=now,
                ),
                RawPacket(
                    raw_hex="SECRET",
                    packet_hash="ADM_HASH",
                    channel_idx=adm_idx,
                    source_pubkey_prefix="FFEEDD",
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()
        return pub_idx, adm_idx

    def test_list_redacts_admin_channel(self, client_no_auth, channel_packets):
        data = client_no_auth.get("/api/v1/packet-groups").json()
        assert data["total"] == 2
        adm = next(i for i in data["items"] if i["packet_hash"] == "ADM_HASH")
        assert adm["redacted"] is True
        assert adm["source_pubkey_prefix"] is None

    def test_list_admin_role_sees_all(self, client_no_auth, channel_packets):
        data = client_no_auth.get(
            "/api/v1/packet-groups", headers={"X-User-Roles": "admin"}
        ).json()
        assert all(not i["redacted"] for i in data["items"])

    def test_detail_redacted_reception(self, client_no_auth, channel_packets):
        data = client_no_auth.get("/api/v1/packet-groups/ADM_HASH").json()
        assert data["redacted"] is True
        r = data["receptions"][0]
        assert r["redacted"] is True
        assert r["path_hashes"] is None
        assert data["raw_hex"] is None

    def test_detail_admin_sees_payload(self, client_no_auth, channel_packets):
        data = client_no_auth.get(
            "/api/v1/packet-groups/ADM_HASH", headers={"X-User-Roles": "admin"}
        ).json()
        assert data["redacted"] is False
        assert data["raw_hex"] == "SECRET"
