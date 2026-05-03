"""Tests for Prometheus metrics endpoint."""

import base64
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from meshcore_hub.api.app import create_app
from meshcore_hub.api.dependencies import (
    get_db_manager,
    get_db_session,
    get_mqtt_client,
)
from meshcore_hub.common.models import Node, UserProfile, UserProfileNode


def _make_basic_auth(username: str, password: str) -> str:
    """Create a Basic auth header value."""
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {credentials}"


def _clear_metrics_cache() -> None:
    """Clear the metrics module cache."""
    from meshcore_hub.api.metrics import _cache

    _cache["output"] = b""
    _cache["expires_at"] = 0.0


class TestMetricsEndpoint:
    """Tests for basic metrics endpoint availability."""

    def test_metrics_endpoint_available(self, client_no_auth):
        """Test that /metrics endpoint returns 200."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client_no_auth):
        """Test that metrics returns correct content type."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_contains_expected_names(self, client_no_auth):
        """Test that metrics output contains expected metric names."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        content = response.text
        assert "meshcore_info" in content
        assert "meshcore_nodes_total" in content
        assert "meshcore_nodes_active" in content
        assert "meshcore_advertisements_total" in content
        assert "meshcore_telemetry_total" in content
        assert "meshcore_trace_paths_total" in content
        assert "meshcore_user_profiles_total" in content
        assert "meshcore_user_profiles_by_role" in content
        assert "meshcore_nodes_adopted" in content

    def test_metrics_info_has_version(self, client_no_auth):
        """Test that meshcore_info includes version label."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert 'meshcore_info{version="' in response.text


class TestMetricsAuth:
    """Tests for metrics endpoint authentication."""

    def test_no_auth_when_no_read_key(self, client_no_auth):
        """Test that no auth is required when no read key is configured."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200

    def test_401_when_read_key_set_no_auth(self, client_with_auth):
        """Test 401 when read key is set but no auth provided."""
        _clear_metrics_cache()
        response = client_with_auth.get("/metrics")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_success_with_correct_basic_auth(self, client_with_auth):
        """Test successful auth with correct Basic credentials."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": _make_basic_auth("metrics", "test-read-key")},
        )
        assert response.status_code == 200

    def test_fail_with_wrong_password(self, client_with_auth):
        """Test 401 with incorrect password."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": _make_basic_auth("metrics", "wrong-key")},
        )
        assert response.status_code == 401

    def test_fail_with_wrong_username(self, client_with_auth):
        """Test 401 with incorrect username."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={
                "Authorization": _make_basic_auth("admin", "test-read-key"),
            },
        )
        assert response.status_code == 401

    def test_fail_with_bearer_auth(self, client_with_auth):
        """Test that Bearer auth does not work for metrics."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 401


class TestMetricsData:
    """Tests for metrics data accuracy."""

    def test_nodes_total_reflects_database(self, client_no_auth, sample_node):
        """Test that nodes_total matches actual node count."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        # Should have at least 1 node
        assert "meshcore_nodes_total 1.0" in response.text

    def test_messages_total_reflects_database(self, client_no_auth, sample_message):
        """Test that messages_total reflects database state."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "meshcore_messages_total" in response.text

    def test_advertisements_total_reflects_database(
        self, client_no_auth, sample_advertisement
    ):
        """Test that advertisements_total reflects database state."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "meshcore_advertisements_total 1.0" in response.text

    def test_nodes_by_type_has_labels(self, client_no_auth, sample_node):
        """Test that nodes_by_type includes adv_type labels."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert 'meshcore_nodes_by_type{adv_type="REPEATER"}' in response.text

    def test_telemetry_total_reflects_database(self, client_no_auth, sample_telemetry):
        """Test that telemetry_total reflects database state."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "meshcore_telemetry_total 1.0" in response.text

    def test_trace_paths_total_reflects_database(
        self, client_no_auth, sample_trace_path
    ):
        """Test that trace_paths_total reflects database state."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "meshcore_trace_paths_total 1.0" in response.text

    def test_node_last_seen_timestamp_no_adoption(self, api_db_session, client_no_auth):
        """Test that node_last_seen_timestamp includes adopted=false for unadopted nodes."""
        seen_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        node = Node(
            public_key="lastseen1234lastseen1234lastseen",
            name="Seen Node",
            adv_type="REPEATER",
            first_seen=seen_at,
            last_seen=seen_at,
        )
        api_db_session.add(node)
        api_db_session.commit()

        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert (
            "meshcore_node_last_seen_timestamp_seconds"
            '{adopted="false",'
            'adv_type="REPEATER",'
            'node_name="Seen Node",'
            'public_key="lastseen1234lastseen1234lastseen"}'
        ) in response.text

    def test_node_last_seen_timestamp_with_adoption(
        self, api_db_session, client_no_auth
    ):
        """Test that node_last_seen_timestamp includes adopted label from adoption."""
        seen_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        profile = UserProfile(
            user_id="auth0|test123",
            name="Test Operator",
        )
        api_db_session.add(profile)
        api_db_session.flush()

        adopted_node = Node(
            public_key="adopted1234adopted1234adopted12",
            name="Adopted Node",
            adv_type="REPEATER",
            first_seen=seen_at,
            last_seen=seen_at,
        )
        unadopted_node = Node(
            public_key="unadopted1234unadopted1234unad",
            name="Unadopted Node",
            adv_type="CLIENT",
            first_seen=seen_at,
            last_seen=seen_at,
        )
        api_db_session.add_all([adopted_node, unadopted_node])
        api_db_session.flush()

        adoption = UserProfileNode(
            user_profile_id=profile.id,
            node_id=adopted_node.id,
        )
        api_db_session.add(adoption)
        api_db_session.commit()

        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert (
            "meshcore_node_last_seen_timestamp_seconds"
            '{adopted="true",'
            'adv_type="REPEATER",'
            'node_name="Adopted Node",'
            'public_key="adopted1234adopted1234adopted12"}'
        ) in response.text
        assert (
            "meshcore_node_last_seen_timestamp_seconds"
            '{adopted="false",'
            'adv_type="CLIENT",'
            'node_name="Unadopted Node",'
            'public_key="unadopted1234unadopted1234unad"}'
        ) in response.text

    def test_node_last_seen_timestamp_skips_null(self, api_db_session, client_no_auth):
        """Test that nodes with last_seen=None are excluded from the metric."""
        node = Node(
            public_key="neverseen1234neverseen1234neversx",
            name="Never Seen",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
            last_seen=None,
        )
        api_db_session.add(node)
        api_db_session.commit()

        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "neverseen1234neverseen1234neversx" not in response.text

    def test_node_last_seen_timestamp_multiple_nodes(
        self, api_db_session, client_no_auth
    ):
        """Test that multiple nodes each get their own labeled time series."""
        seen1 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        seen2 = datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc)
        node1 = Node(
            public_key="multinode1multinode1multinode1mu",
            name="Node One",
            adv_type="REPEATER",
            first_seen=seen1,
            last_seen=seen1,
        )
        node2 = Node(
            public_key="multinode2multinode2multinode2mu",
            name="Node Two",
            adv_type="CHAT",
            first_seen=seen2,
            last_seen=seen2,
        )
        api_db_session.add_all([node1, node2])
        api_db_session.commit()

        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert ('public_key="multinode1multinode1multinode1mu"') in response.text
        assert ('public_key="multinode2multinode2multinode2mu"') in response.text

    def test_nodes_with_location(self, api_db_session, client_no_auth):
        """Test that nodes_with_location counts correctly."""
        node = Node(
            public_key="locationtest1234locationtest1234",
            name="GPS Node",
            adv_type="CHAT",
            lat=37.7749,
            lon=-122.4194,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(node)
        api_db_session.commit()

        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "meshcore_nodes_with_location 1.0" in response.text

    def test_nodes_adopted_metric(self, api_db_session, client_no_auth):
        """Test that meshcore_nodes_adopted gauge reflects adopted node count."""
        seen_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        profile = UserProfile(user_id="auth0|metric_test", name="Metric Op")
        api_db_session.add(profile)
        api_db_session.flush()

        node1 = Node(
            public_key="adopted_metric_0000000000000000",
            first_seen=seen_at,
            last_seen=seen_at,
        )
        node2 = Node(
            public_key="unadopted_metric_00000000000000",
            first_seen=seen_at,
            last_seen=seen_at,
        )
        api_db_session.add_all([node1, node2])
        api_db_session.flush()

        adoption = UserProfileNode(user_profile_id=profile.id, node_id=node1.id)
        api_db_session.add(adoption)
        api_db_session.commit()

        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200
        assert "meshcore_nodes_adopted 1.0" in response.text


class TestMetricsDisabled:
    """Tests for when metrics are disabled."""

    def test_metrics_404_when_disabled(
        self, test_db_path, api_db_engine, mock_mqtt, mock_db_manager
    ):
        """Test that /metrics returns 404 when disabled."""
        db_url = f"sqlite:///{test_db_path}"

        with patch("meshcore_hub.api.app._db_manager", mock_db_manager):
            app = create_app(
                database_url=db_url,
                metrics_enabled=False,
            )

            Session = sessionmaker(bind=api_db_engine)

            def override_get_db_manager(request=None):
                return mock_db_manager

            def override_get_db_session():
                session = Session()
                try:
                    yield session
                finally:
                    session.close()

            def override_get_mqtt_client(request=None):
                return mock_mqtt

            app.dependency_overrides[get_db_manager] = override_get_db_manager
            app.dependency_overrides[get_db_session] = override_get_db_session
            app.dependency_overrides[get_mqtt_client] = override_get_mqtt_client

            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/metrics")
            assert response.status_code == 404


class TestMetricsCache:
    """Tests for metrics caching behavior."""

    def test_cache_returns_same_output(self, client_no_auth):
        """Test that cached responses return the same content."""
        _clear_metrics_cache()
        response1 = client_no_auth.get("/metrics")
        response2 = client_no_auth.get("/metrics")
        assert response1.text == response2.text
