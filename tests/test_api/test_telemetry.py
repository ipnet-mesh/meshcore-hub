"""Tests for telemetry API routes."""

from datetime import datetime, timedelta, timezone


class TestListTelemetry:
    """Tests for GET /telemetry endpoint."""

    def test_list_telemetry_empty(self, client_no_auth):
        """Test listing telemetry when database is empty."""
        response = client_no_auth.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_telemetry_with_data(self, client_no_auth, sample_telemetry):
        """Test listing telemetry with data in database."""
        response = client_no_auth.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["node_public_key"] == sample_telemetry.node_public_key
        assert data["items"][0]["parsed_data"] == sample_telemetry.parsed_data

    def test_list_telemetry_filter_by_node(self, client_no_auth, sample_telemetry):
        """Test filtering telemetry by node public key."""
        response = client_no_auth.get(
            f"/api/v1/telemetry?node_public_key={sample_telemetry.node_public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = client_no_auth.get("/api/v1/telemetry?node_public_key=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0


class TestGetTelemetry:
    """Tests for GET /telemetry/{id} endpoint."""

    def test_get_telemetry_success(self, client_no_auth, sample_telemetry):
        """Test getting a specific telemetry record."""
        response = client_no_auth.get(f"/api/v1/telemetry/{sample_telemetry.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["node_public_key"] == sample_telemetry.node_public_key

    def test_get_telemetry_not_found(self, client_no_auth):
        """Test getting a non-existent telemetry record."""
        response = client_no_auth.get("/api/v1/telemetry/nonexistent-id")
        assert response.status_code == 404


class TestListTelemetryFilters:
    """Tests for telemetry list query filters."""

    def test_filter_by_observed_by(
        self,
        client_no_auth,
        sample_telemetry,
        sample_telemetry_with_receiver,
        receiver_node,
    ):
        """Test filtering telemetry by receiver node."""
        response = client_no_auth.get(
            f"/api/v1/telemetry?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_filter_by_since(self, client_no_auth, api_db_session):
        """Test filtering telemetry by since timestamp."""
        from meshcore_hub.common.models import Telemetry

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create old telemetry
        old_telemetry = Telemetry(
            node_public_key="old123old123old123old123old123ol",
            parsed_data={"battery_level": 10.0},
            received_at=old_time,
        )
        api_db_session.add(old_telemetry)
        api_db_session.commit()

        # Filter since yesterday - should not include old telemetry
        since = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/telemetry?since={since}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_until(self, client_no_auth, api_db_session):
        """Test filtering telemetry by until timestamp."""
        from meshcore_hub.common.models import Telemetry

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create old telemetry
        old_telemetry = Telemetry(
            node_public_key="until123until123until123until12",
            parsed_data={"battery_level": 20.0},
            received_at=old_time,
        )
        api_db_session.add(old_telemetry)
        api_db_session.commit()

        # Filter until 5 days ago - should include old telemetry
        until = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/telemetry?until={until}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1


class TestTelemetryObservers:
    """Tests for observer data in telemetry API responses."""

    def test_telemetry_observers_populated(self, client_no_auth, api_db_session):
        """Test that telemetry list returns observers with data."""
        from meshcore_hub.common.hash_utils import compute_telemetry_hash
        from meshcore_hub.common.models import EventObserver, Node, Telemetry

        observer_node = Node(
            public_key="z" * 64,
            name="TelObserver",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(observer_node)
        api_db_session.flush()

        now = datetime.now(timezone.utc)
        event_hash = compute_telemetry_hash(
            node_public_key="tel123tel123tel123tel123tel123tel",
            parsed_data={"temperature": 22.0},
            received_at=now,
        )
        telemetry = Telemetry(
            node_public_key="tel123tel123tel123tel123tel123tel",
            parsed_data={"temperature": 22.0},
            received_at=now,
            observer_node_id=observer_node.id,
            event_hash=event_hash,
        )
        api_db_session.add(telemetry)
        api_db_session.flush()

        ev_obs = EventObserver(
            event_type="telemetry",
            event_hash=event_hash,
            observer_node_id=observer_node.id,
            snr=8.5,
            path_len=2,
            observed_at=now,
        )
        api_db_session.add(ev_obs)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) >= 1
        tel_item = next(
            i
            for i in items
            if i["node_public_key"] == "tel123tel123tel123tel123tel123tel"
        )
        assert len(tel_item["observers"]) == 1
        assert tel_item["observers"][0]["snr"] == 8.5
        assert tel_item["observers"][0]["path_len"] == 2
