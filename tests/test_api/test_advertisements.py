"""Tests for advertisement API routes."""

from datetime import datetime, timedelta, timezone

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

    def test_list_advertisements_filter_by_public_key(
        self, client_no_auth, sample_advertisement
    ):
        """Test filtering advertisements by public key."""
        response = client_no_auth.get(
            f"/api/v1/advertisements?public_key={sample_advertisement.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = client_no_auth.get("/api/v1/advertisements?public_key=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0


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

    def test_filter_by_observed_by(
        self,
        client_no_auth,
        sample_advertisement,
        sample_advertisement_with_receiver,
        receiver_node,
    ):
        """Test filtering advertisements by receiver node."""
        response = client_no_auth.get(
            f"/api/v1/advertisements?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

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
