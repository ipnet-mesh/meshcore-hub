"""Tests for trace path API routes."""

from datetime import datetime, timedelta, timezone

from meshcore_hub.common.models import TracePath


class TestMultibytePathHashes:
    """Tests for multibyte path hash support in trace path API responses."""

    def test_list_trace_paths_returns_multibyte_path_hashes(
        self, client_no_auth, api_db_session
    ):
        """Test that GET /trace-paths returns multibyte path hashes faithfully."""
        multibyte_hashes = ["4a2b", "b3fa"]
        trace = TracePath(
            initiator_tag=77777,
            path_hashes=multibyte_hashes,
            hop_count=2,
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add(trace)
        api_db_session.commit()
        api_db_session.refresh(trace)

        response = client_no_auth.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["path_hashes"] == multibyte_hashes

    def test_get_trace_path_returns_mixed_length_path_hashes(
        self, client_no_auth, api_db_session
    ):
        """Test that GET /trace-paths/{id} returns mixed-length path hashes."""
        mixed_hashes = ["4a", "b3fa", "02"]
        trace = TracePath(
            initiator_tag=88888,
            path_hashes=mixed_hashes,
            hop_count=3,
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add(trace)
        api_db_session.commit()
        api_db_session.refresh(trace)

        response = client_no_auth.get(f"/api/v1/trace-paths/{trace.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["path_hashes"] == mixed_hashes


class TestListTracePaths:
    """Tests for GET /trace-paths endpoint."""

    def test_list_trace_paths_empty(self, client_no_auth):
        """Test listing trace paths when database is empty."""
        response = client_no_auth.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_trace_paths_with_data(self, client_no_auth, sample_trace_path):
        """Test listing trace paths with data in database."""
        response = client_no_auth.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["path_hashes"] == sample_trace_path.path_hashes
        assert data["items"][0]["hop_count"] == sample_trace_path.hop_count


class TestGetTracePath:
    """Tests for GET /trace-paths/{id} endpoint."""

    def test_get_trace_path_success(self, client_no_auth, sample_trace_path):
        """Test getting a specific trace path."""
        response = client_no_auth.get(f"/api/v1/trace-paths/{sample_trace_path.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["path_hashes"] == sample_trace_path.path_hashes

    def test_get_trace_path_not_found(self, client_no_auth):
        """Test getting a non-existent trace path."""
        response = client_no_auth.get("/api/v1/trace-paths/nonexistent-id")
        assert response.status_code == 404


class TestListTracePathsFilters:
    """Tests for trace path list query filters."""

    def test_filter_by_observed_by(
        self,
        client_no_auth,
        sample_trace_path,
        sample_trace_path_with_receiver,
        receiver_node,
    ):
        """Test filtering trace paths by receiver node."""
        response = client_no_auth.get(
            f"/api/v1/trace-paths?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_filter_by_since(self, client_no_auth, api_db_session):
        """Test filtering trace paths by since timestamp."""
        from meshcore_hub.common.models import TracePath

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create old trace path
        old_trace = TracePath(
            initiator_tag=11111,
            path_hashes=["old1", "old2"],
            hop_count=2,
            received_at=old_time,
        )
        api_db_session.add(old_trace)
        api_db_session.commit()

        # Filter since yesterday - should not include old trace path
        since = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/trace-paths?since={since}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_until(self, client_no_auth, api_db_session):
        """Test filtering trace paths by until timestamp."""
        from meshcore_hub.common.models import TracePath

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create old trace path
        old_trace = TracePath(
            initiator_tag=22222,
            path_hashes=["until1", "until2"],
            hop_count=2,
            received_at=old_time,
        )
        api_db_session.add(old_trace)
        api_db_session.commit()

        # Filter until 5 days ago - should include old trace path
        until = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/trace-paths?until={until}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1


class TestTracePathObservers:
    """Tests for observer data in trace path API responses."""

    def test_trace_path_observers_populated(self, client_no_auth, api_db_session):
        """Test that trace path list returns observers with data."""
        from meshcore_hub.common.hash_utils import compute_trace_hash
        from meshcore_hub.common.models import EventObserver, Node, TracePath

        observer_node = Node(
            public_key="z" * 64,
            name="TraceObserver",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(observer_node)
        api_db_session.flush()

        event_hash = compute_trace_hash(initiator_tag=44444)
        trace = TracePath(
            initiator_tag=44444,
            path_hashes=["aa", "bb"],
            hop_count=2,
            received_at=datetime.now(timezone.utc),
            observer_node_id=observer_node.id,
            event_hash=event_hash,
        )
        api_db_session.add(trace)
        api_db_session.flush()

        ev_obs = EventObserver(
            event_type="trace",
            event_hash=event_hash,
            observer_node_id=observer_node.id,
            snr=12.0,
            path_len=3,
            observed_at=datetime.now(timezone.utc),
        )
        api_db_session.add(ev_obs)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) >= 1
        trace_item = next(i for i in items if i["initiator_tag"] == 44444)
        assert len(trace_item["observers"]) == 1
        assert trace_item["observers"][0]["snr"] == 12.0
        assert trace_item["observers"][0]["path_len"] == 3
