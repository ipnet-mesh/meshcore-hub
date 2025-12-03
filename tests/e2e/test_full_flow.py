"""End-to-end tests for the full MeshCore Hub flow.

These tests require Docker Compose services to be running:

    docker compose -f tests/e2e/docker-compose.test.yml up -d
    pytest tests/e2e/
    docker compose -f tests/e2e/docker-compose.test.yml down -v

The tests verify:
1. API health endpoints
2. Web dashboard health endpoints
3. Node listing and retrieval
4. Message listing
5. Statistics endpoint
6. Command sending (admin only)
"""

import httpx


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_api_health(self, api_client: httpx.Client) -> None:
        """Test API basic health endpoint."""
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_api_ready(self, api_client: httpx.Client) -> None:
        """Test API readiness endpoint with database check."""
        response = api_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"

    def test_web_health(self, web_client: httpx.Client) -> None:
        """Test Web dashboard health endpoint."""
        response = web_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_web_ready(self, web_client: httpx.Client) -> None:
        """Test Web dashboard readiness with API connectivity."""
        response = web_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["api"] == "connected"


class TestAPIEndpoints:
    """Test API data endpoints."""

    def test_list_nodes(self, api_client: httpx.Client) -> None:
        """Test listing nodes."""
        response = api_client.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_list_messages(self, api_client: httpx.Client) -> None:
        """Test listing messages."""
        response = api_client.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_list_advertisements(self, api_client: httpx.Client) -> None:
        """Test listing advertisements."""
        response = api_client.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_get_stats(self, api_client: httpx.Client) -> None:
        """Test getting network statistics."""
        response = api_client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_nodes" in data
        assert "active_nodes" in data
        assert "total_messages" in data

    def test_list_telemetry(self, api_client: httpx.Client) -> None:
        """Test listing telemetry records."""
        response = api_client.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_list_trace_paths(self, api_client: httpx.Client) -> None:
        """Test listing trace paths."""
        response = api_client.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_list_members(self, api_client: httpx.Client) -> None:
        """Test listing members."""
        response = api_client.get("/api/v1/members")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data


class TestWebDashboard:
    """Test web dashboard pages."""

    def test_home_page(self, web_client: httpx.Client) -> None:
        """Test home page loads."""
        response = web_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_network_page(self, web_client: httpx.Client) -> None:
        """Test network overview page loads."""
        response = web_client.get("/network")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_nodes_page(self, web_client: httpx.Client) -> None:
        """Test nodes listing page loads."""
        response = web_client.get("/nodes")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_messages_page(self, web_client: httpx.Client) -> None:
        """Test messages page loads."""
        response = web_client.get("/messages")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_map_page(self, web_client: httpx.Client) -> None:
        """Test map page loads."""
        response = web_client.get("/map")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_members_page(self, web_client: httpx.Client) -> None:
        """Test members page loads."""
        response = web_client.get("/members")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestAuthentication:
    """Test API authentication."""

    def test_read_access_with_read_key(self, api_client: httpx.Client) -> None:
        """Test read access works with read key."""
        response = api_client.get("/api/v1/nodes")
        assert response.status_code == 200

    def test_admin_access_with_admin_key(self, admin_client: httpx.Client) -> None:
        """Test admin access works with admin key."""
        # Admin key should have read access
        response = admin_client.get("/api/v1/nodes")
        assert response.status_code == 200


class TestCommands:
    """Test command endpoints (requires admin access)."""

    def test_send_message_requires_admin(self, api_client: httpx.Client) -> None:
        """Test that send message requires admin key."""
        response = api_client.post(
            "/api/v1/commands/send-message",
            json={
                "destination": "0" * 64,
                "text": "Test message",
            },
        )
        # Read key should not have admin access
        assert response.status_code == 403

    def test_send_channel_message_admin(self, admin_client: httpx.Client) -> None:
        """Test sending channel message with admin key."""
        response = admin_client.post(
            "/api/v1/commands/send-channel-message",
            json={
                "channel_idx": 0,
                "text": "Test channel message",
            },
        )
        # Should succeed with admin key (202 = accepted for processing)
        assert response.status_code == 202

    def test_send_advertisement_admin(self, admin_client: httpx.Client) -> None:
        """Test sending advertisement with admin key."""
        response = admin_client.post(
            "/api/v1/commands/send-advertisement",
            json={
                "flood": False,
            },
        )
        assert response.status_code == 202
