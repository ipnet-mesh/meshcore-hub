"""Tests for advertisement API routes."""

from datetime import datetime, timedelta, timezone

from meshcore_hub.common.hash_utils import compute_advertisement_hash
from meshcore_hub.common.models import Advertisement, EventObserver


class TestListAdvertisements:
    """Tests for GET /advertisements endpoint."""

    def test_list_advertisements_empty(self, client_no_auth):
        """Test listing advertisements when database is empty."""
        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_advertisements_with_data(self, client_no_auth, sample_advertisement):
        """Test listing advertisements with data in database."""
        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["public_key"] == sample_advertisement.public_key
        assert data["items"][0]["adv_type"] == sample_advertisement.adv_type

    def test_list_advertisements_with_observers(
        self,
        client_no_auth,
        api_db_session,
        receiver_node,
    ):
        """Test that observers list is included in advertisement response."""
        from hashlib import md5

        event_hash = md5(b"test-ad-observers").hexdigest()
        advert = Advertisement(
            public_key="obs123obs123obs123obs123obs123ob",
            name="ObservedAd",
            adv_type="REPEATER",
            received_at=datetime.now(timezone.utc),
            observer_node_id=receiver_node.id,
            event_hash=event_hash,
        )
        api_db_session.add(advert)
        api_db_session.commit()

        observer = EventObserver(
            event_type="advertisement",
            event_hash=event_hash,
            observer_node_id=receiver_node.id,
            observed_at=datetime.now(timezone.utc),
        )
        api_db_session.add(observer)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert "observers" in item
        assert len(item["observers"]) == 1

    def test_list_advertisements_with_node_tag_name(
        self, client_no_auth, api_db_session, sample_node_with_name_tag
    ):
        """Test that node_tag_name is resolved from name tags."""
        advert = Advertisement(
            public_key=sample_node_with_name_tag.public_key,
            name="AdName",
            adv_type="CLIENT",
            received_at=datetime.now(timezone.utc),
            node_id=sample_node_with_name_tag.id,
        )
        api_db_session.add(advert)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["node_tag_name"] == "Friendly Search Name"


class TestGetAdvertisement:
    """Tests for GET /advertisements/{id} endpoint."""

    def test_get_advertisement_success(self, client_no_auth, sample_advertisement):
        """Test getting a specific advertisement."""
        response = client_no_auth.get(
            f"/api/v1/advertisements/{sample_advertisement.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == sample_advertisement.public_key

    def test_get_advertisement_not_found(self, client_no_auth):
        """Test getting a non-existent advertisement."""
        response = client_no_auth.get("/api/v1/advertisements/nonexistent-id")
        assert response.status_code == 404

    def test_get_advertisement_with_observers(
        self,
        client_no_auth,
        api_db_session,
        receiver_node,
    ):
        """Test that get includes observers list."""
        from hashlib import md5

        event_hash = md5(b"test-get-ad-observers").hexdigest()
        advert = Advertisement(
            public_key="getobs123getobs123getobs123getob",
            name="GetObservedAd",
            adv_type="REPEATER",
            received_at=datetime.now(timezone.utc),
            observer_node_id=receiver_node.id,
            event_hash=event_hash,
        )
        api_db_session.add(advert)
        api_db_session.commit()

        observer = EventObserver(
            event_type="advertisement",
            event_hash=event_hash,
            observer_node_id=receiver_node.id,
            observed_at=datetime.now(timezone.utc),
        )
        api_db_session.add(observer)
        api_db_session.commit()

        response = client_no_auth.get(f"/api/v1/advertisements/{advert.id}")
        assert response.status_code == 200
        data = response.json()
        assert "observers" in data
        assert len(data["observers"]) == 1
        assert data["observers"][0]["public_key"] == receiver_node.public_key

    def test_get_advertisement_with_tag_names(
        self, client_no_auth, api_db_session, sample_node_with_name_tag
    ):
        """Test that get includes node_tag_name and observer_tag_name."""
        advert = Advertisement(
            public_key=sample_node_with_name_tag.public_key,
            name="AdName",
            adv_type="CLIENT",
            received_at=datetime.now(timezone.utc),
            node_id=sample_node_with_name_tag.id,
        )
        api_db_session.add(advert)
        api_db_session.commit()

        response = client_no_auth.get(f"/api/v1/advertisements/{advert.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["node_tag_name"] == "Friendly Search Name"


class TestListAdvertisementsFilters:
    """Tests for advertisement list query filters."""

    def test_filter_by_search_public_key(self, client_no_auth, sample_advertisement):
        """Test filtering advertisements by public key search."""
        # Partial public key match
        response = client_no_auth.get("/api/v1/advertisements?search=abc123")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # No match
        response = client_no_auth.get("/api/v1/advertisements?search=zzz999")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_search_name(self, client_no_auth, sample_advertisement):
        """Test filtering advertisements by name search."""
        response = client_no_auth.get("/api/v1/advertisements?search=TestNode")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_list_advertisements_filter_by_observed_by_single(
        self,
        client_no_auth,
        sample_advertisement,
        sample_advertisement_with_receiver,
        receiver_node,
    ):
        """Test filtering advertisements by a single receiver node."""
        response = client_no_auth.get(
            f"/api/v1/advertisements?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_list_advertisements_filter_by_observed_by_multiple(
        self,
        client_no_auth,
        api_db_session,
        receiver_node,
    ):
        """Test filtering advertisements by multiple receiver nodes."""
        # Create second receiver node
        second_receiver = receiver_node.__class__(
            public_key="2nd1232nd1232nd1232nd1232nd1232n",
            name="SecondObserver",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(second_receiver)
        api_db_session.commit()

        # Create two advertisements, each observed by a different receiver
        now = datetime.now(timezone.utc)
        ad1_hash = compute_advertisement_hash(
            public_key="ad1pubad1pubad1pubad1pubad1pubad",
            name="AD1",
            adv_type="CLIENT",
            received_at=now,
        )
        ad2_hash = compute_advertisement_hash(
            public_key="ad2pubad2pubad2pubad2pubad2pubad",
            name="AD2",
            adv_type="CLIENT",
            received_at=now,
        )
        ad1 = Advertisement(
            public_key="ad1pubad1pubad1pubad1pubad1pubad",
            name="AD1",
            adv_type="CLIENT",
            received_at=now,
            observer_node_id=receiver_node.id,
            event_hash=ad1_hash,
        )
        ad2 = Advertisement(
            public_key="ad2pubad2pubad2pubad2pubad2pubad",
            name="AD2",
            adv_type="CLIENT",
            received_at=now,
            observer_node_id=second_receiver.id,
            event_hash=ad2_hash,
        )
        api_db_session.add_all([ad1, ad2])
        api_db_session.commit()

        api_db_session.add_all(
            [
                EventObserver(
                    event_type="advertisement",
                    event_hash=ad1_hash,
                    observer_node_id=receiver_node.id,
                    observed_at=datetime.now(timezone.utc),
                ),
                EventObserver(
                    event_type="advertisement",
                    event_hash=ad2_hash,
                    observer_node_id=second_receiver.id,
                    observed_at=datetime.now(timezone.utc),
                ),
            ]
        )
        api_db_session.commit()

        # Filter by both receivers
        response = client_no_auth.get(
            f"/api/v1/advertisements?observed_by={receiver_node.public_key}&observed_by={second_receiver.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        # Filter by just the first receiver
        response = client_no_auth.get(
            f"/api/v1/advertisements?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "AD1"

    def test_filter_by_observed_by_secondary_observer(
        self,
        client_no_auth,
        api_db_session,
    ):
        """Secondary observer (only in event_observers) sees the ad."""
        from meshcore_hub.common.models import Node

        primary_node = Node(
            public_key="p1advp1advp1advp1advp1advp1advp",
            name="PrimaryObserver",
            first_seen=datetime.now(timezone.utc),
        )
        secondary_node = Node(
            public_key="s1advs1advs1advs1advs1advs1advs1",
            name="SecondaryObserver",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([primary_node, secondary_node])
        api_db_session.commit()

        now = datetime.now(timezone.utc)
        event_hash = compute_advertisement_hash(
            public_key="secobssecobssecobssecobssecobsse",
            name="SecondaryObsAd",
            adv_type="CLIENT",
            received_at=now,
        )
        advert = Advertisement(
            public_key="secobssecobssecobssecobssecobsse",
            name="SecondaryObsAd",
            adv_type="CLIENT",
            received_at=now,
            observer_node_id=primary_node.id,
            event_hash=event_hash,
        )
        api_db_session.add(advert)
        api_db_session.commit()

        api_db_session.add(
            EventObserver(
                event_type="advertisement",
                event_hash=event_hash,
                observer_node_id=secondary_node.id,
                observed_at=datetime.now(timezone.utc),
            )
        )
        api_db_session.commit()

        response = client_no_auth.get(
            f"/api/v1/advertisements?observed_by={secondary_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "SecondaryObsAd"
        assert data["items"][0]["observed_by"] == primary_node.public_key

    def test_filter_by_since(self, client_no_auth, api_db_session):
        """Test filtering advertisements by since timestamp."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create an old advertisement
        old_advert = Advertisement(
            public_key="old123old123old123old123old123ol",
            name="Old Advertisement",
            adv_type="CLIENT",
            received_at=old_time,
        )
        api_db_session.add(old_advert)
        api_db_session.commit()

        # Filter since yesterday - should not include old advertisement
        since = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/advertisements?since={since}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_until(self, client_no_auth, api_db_session):
        """Test filtering advertisements by until timestamp."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create an old advertisement
        old_advert = Advertisement(
            public_key="until123until123until123until12",
            name="Old Advertisement Until",
            adv_type="CLIENT",
            received_at=old_time,
        )
        api_db_session.add(old_advert)
        api_db_session.commit()

        # Filter until 5 days ago - should include old advertisement
        until = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/advertisements?until={until}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_filter_by_public_key(self, client_no_auth, api_db_session):
        """Test filtering advertisements by source public_key."""
        now = datetime.now(timezone.utc)
        ad_a = Advertisement(
            public_key="pka" * 11,
            name="AdAlpha",
            adv_type="CLIENT",
            received_at=now,
        )
        ad_b = Advertisement(
            public_key="pkb" * 11,
            name="AdBeta",
            adv_type="CLIENT",
            received_at=now,
        )
        api_db_session.add_all([ad_a, ad_b])
        api_db_session.commit()

        response = client_no_auth.get(
            f"/api/v1/advertisements?public_key={ad_a.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["public_key"] == ad_a.public_key

    def test_filter_by_public_key_no_match(self, client_no_auth, api_db_session):
        """Test filtering by public_key with no matching ads returns empty."""
        now = datetime.now(timezone.utc)
        ad = Advertisement(
            public_key="pkx" * 11,
            name="AdX",
            adv_type="CLIENT",
            received_at=now,
        )
        api_db_session.add(ad)
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/advertisements?public_key=nonexistent0000000000000000000"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestAdvertisementSort:
    """Tests for advertisement list sort parameters."""

    def test_sort_by_time_default(self, client_no_auth, api_db_session):
        """Default sort is received_at DESC."""
        now = datetime.now(timezone.utc)
        ad_old = Advertisement(
            public_key="aa" * 16,
            name="Old",
            adv_type="CLIENT",
            received_at=now - timedelta(hours=1),
        )
        ad_new = Advertisement(
            public_key="bb" * 16,
            name="New",
            adv_type="CLIENT",
            received_at=now,
        )
        api_db_session.add_all([ad_old, ad_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "New"
        assert items[1]["name"] == "Old"

    def test_sort_by_time_asc(self, client_no_auth, api_db_session):
        """sort=time&order=asc returns oldest first."""
        now = datetime.now(timezone.utc)
        ad_old = Advertisement(
            public_key="aa" * 16,
            name="Old",
            adv_type="CLIENT",
            received_at=now - timedelta(hours=1),
        )
        ad_new = Advertisement(
            public_key="bb" * 16,
            name="New",
            adv_type="CLIENT",
            received_at=now,
        )
        api_db_session.add_all([ad_old, ad_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements?sort=time&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Old"
        assert items[1]["name"] == "New"

    def test_sort_by_node_name(self, client_no_auth, api_db_session):
        """sort=node_name sorts by display name (COALESCE)."""
        from meshcore_hub.common.models import Node

        now = datetime.now(timezone.utc)
        node_b = Node(
            public_key="aa" * 16,
            name="Bravo",
            first_seen=now,
        )
        node_a = Node(
            public_key="bb" * 16,
            name="Alpha",
            first_seen=now,
        )
        api_db_session.add_all([node_b, node_a])
        api_db_session.commit()

        ad_b = Advertisement(
            public_key="aa" * 16,
            name="AdBravo",
            adv_type="CLIENT",
            received_at=now,
            node_id=node_b.id,
        )
        ad_a = Advertisement(
            public_key="bb" * 16,
            name="AdAlpha",
            adv_type="CLIENT",
            received_at=now,
            node_id=node_a.id,
        )
        api_db_session.add_all([ad_b, ad_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements?sort=node_name&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["node_name"] == "Alpha"
        assert items[1]["node_name"] == "Bravo"

    def test_sort_by_node_name_tag_priority(self, client_no_auth, api_db_session):
        """Name tag takes priority over SourceNode.name in sort."""
        from meshcore_hub.common.models import Node, NodeTag

        now = datetime.now(timezone.utc)
        node_b = Node(
            public_key="aa" * 16,
            name="Alpha",
            first_seen=now,
        )
        node_a = Node(
            public_key="bb" * 16,
            name="Bravo",
            first_seen=now,
        )
        api_db_session.add_all([node_b, node_a])
        api_db_session.commit()

        tag_b = NodeTag(node_id=node_b.id, key="name", value="Zebra")
        tag_a = NodeTag(node_id=node_a.id, key="name", value="Aardvark")
        api_db_session.add_all([tag_b, tag_a])
        api_db_session.commit()

        ad_b = Advertisement(
            public_key="aa" * 16,
            name="AdB",
            adv_type="CLIENT",
            received_at=now,
            node_id=node_b.id,
        )
        ad_a = Advertisement(
            public_key="bb" * 16,
            name="AdA",
            adv_type="CLIENT",
            received_at=now,
            node_id=node_a.id,
        )
        api_db_session.add_all([ad_b, ad_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements?sort=node_name&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["node_name"] == "Bravo"
        assert items[1]["node_name"] == "Alpha"

    def test_sort_by_public_key(self, client_no_auth, api_db_session):
        """sort=public_key orders by public_key."""
        now = datetime.now(timezone.utc)
        ad_b = Advertisement(
            public_key="bb" * 16,
            name="Bravo",
            adv_type="CLIENT",
            received_at=now,
        )
        ad_a = Advertisement(
            public_key="aa" * 16,
            name="Alpha",
            adv_type="CLIENT",
            received_at=now,
        )
        api_db_session.add_all([ad_b, ad_a])
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/advertisements?sort=public_key&order=asc"
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["public_key"] == "aa" * 16

    def test_sort_invalid_ignored(self, client_no_auth, api_db_session):
        """Invalid sort value falls back to default (time desc)."""
        now = datetime.now(timezone.utc)
        ad_old = Advertisement(
            public_key="aa" * 16,
            name="Old",
            adv_type="CLIENT",
            received_at=now - timedelta(hours=1),
        )
        ad_new = Advertisement(
            public_key="bb" * 16,
            name="New",
            adv_type="CLIENT",
            received_at=now,
        )
        api_db_session.add_all([ad_old, ad_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements?sort=invalid_column")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "New"


class TestListAdvertisementsRouteTypeFilter:
    """Tests for route_type query parameter on advertisements endpoint."""

    def test_default_filter_shows_flood_and_null(self, client_no_auth, api_db_session):
        """Default route_type filter shows flood, transport_flood, and NULL."""
        now = datetime.now(timezone.utc)
        flood_ad = Advertisement(
            public_key="aa" * 16,
            name="Flood",
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
        )
        null_ad = Advertisement(
            public_key="bb" * 16,
            name="Historical",
            adv_type="CLIENT",
            received_at=now,
            route_type=None,
        )
        direct_ad = Advertisement(
            public_key="cc" * 16,
            name="Direct",
            adv_type="CLIENT",
            received_at=now,
            route_type="direct",
        )
        api_db_session.add_all([flood_ad, null_ad, direct_ad])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        names = {item["name"] for item in data["items"]}
        assert names == {"Flood", "Historical"}

    def test_filter_all_shows_all(self, client_no_auth, api_db_session):
        """route_type=all shows all advertisements."""
        now = datetime.now(timezone.utc)
        flood_ad = Advertisement(
            public_key="aa" * 16,
            name="Flood",
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
        )
        direct_ad = Advertisement(
            public_key="cc" * 16,
            name="Direct",
            adv_type="CLIENT",
            received_at=now,
            route_type="direct",
        )
        api_db_session.add_all([flood_ad, direct_ad])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements?route_type=all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_filter_direct_only(self, client_no_auth, api_db_session):
        """route_type=direct shows only direct and NULL."""
        now = datetime.now(timezone.utc)
        flood_ad = Advertisement(
            public_key="aa" * 16,
            name="Flood",
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
        )
        direct_ad = Advertisement(
            public_key="cc" * 16,
            name="Direct",
            adv_type="CLIENT",
            received_at=now,
            route_type="direct",
        )
        null_ad = Advertisement(
            public_key="dd" * 16,
            name="Historical",
            adv_type="CLIENT",
            received_at=now,
            route_type=None,
        )
        api_db_session.add_all([flood_ad, direct_ad, null_ad])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements?route_type=direct")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        names = {item["name"] for item in data["items"]}
        assert names == {"Direct", "Historical"}

    def test_route_type_in_response(self, client_no_auth, api_db_session):
        """route_type and advert_timestamp are included in response."""
        now = datetime.now(timezone.utc)
        ad = Advertisement(
            public_key="aa" * 16,
            name="Test",
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
        )
        api_db_session.add(ad)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["route_type"] == "flood"
        assert data["items"][0]["advert_timestamp"] is None

    def test_get_advertisement_includes_route_type(
        self, client_no_auth, api_db_session
    ):
        """GET /{id} includes route_type and advert_timestamp."""
        now = datetime.now(timezone.utc)
        ad = Advertisement(
            public_key="aa" * 16,
            name="Test",
            adv_type="CLIENT",
            received_at=now,
            route_type="transport_flood",
        )
        api_db_session.add(ad)
        api_db_session.commit()

        response = client_no_auth.get(f"/api/v1/advertisements/{ad.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["route_type"] == "transport_flood"
