"""Tests for the nodes page routes."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_web.conftest import MockHttpClient


class TestNodesListPage:
    """Tests for the nodes list page."""

    def test_nodes_returns_200(self, client: TestClient) -> None:
        """Test that nodes page returns 200 status code."""
        response = client.get("/nodes")
        assert response.status_code == 200

    def test_nodes_returns_html(self, client: TestClient) -> None:
        """Test that nodes page returns HTML content."""
        response = client.get("/nodes")
        assert "text/html" in response.headers["content-type"]

    def test_nodes_contains_network_name(self, client: TestClient) -> None:
        """Test that nodes page contains the network name."""
        response = client.get("/nodes")
        assert "Test Network" in response.text

    def test_nodes_displays_node_list(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that nodes page displays node data from API."""
        response = client.get("/nodes")
        assert response.status_code == 200
        # Check for node data from mock (names and public key prefixes)
        assert "Node One" in response.text
        assert "Node Two" in response.text
        assert "abc123" in response.text
        assert "def456" in response.text

    def test_nodes_displays_public_keys(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that nodes page displays public keys."""
        response = client.get("/nodes")
        # Should show truncated or full public keys
        assert "abc123" in response.text or "def456" in response.text

    def test_nodes_with_search_param(self, client: TestClient) -> None:
        """Test nodes page with search parameter."""
        response = client.get("/nodes?search=test")
        assert response.status_code == 200

    def test_nodes_with_adv_type_filter(self, client: TestClient) -> None:
        """Test nodes page with adv_type filter."""
        response = client.get("/nodes?adv_type=REPEATER")
        assert response.status_code == 200

    def test_nodes_with_pagination(self, client: TestClient) -> None:
        """Test nodes page with pagination parameters."""
        response = client.get("/nodes?page=1&limit=10")
        assert response.status_code == 200

    def test_nodes_page_2(self, client: TestClient) -> None:
        """Test nodes page 2."""
        response = client.get("/nodes?page=2")
        assert response.status_code == 200


class TestNodeDetailPage:
    """Tests for the node detail page."""

    def test_node_detail_returns_200(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that node detail page returns 200 status code."""
        response = client.get("/nodes/abc123def456abc123def456abc123de")
        assert response.status_code == 200

    def test_node_detail_returns_html(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that node detail page returns HTML content."""
        response = client.get("/nodes/abc123def456abc123def456abc123de")
        assert "text/html" in response.headers["content-type"]

    def test_node_detail_displays_node_info(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that node detail page displays node information."""
        response = client.get("/nodes/abc123def456abc123def456abc123de")
        assert response.status_code == 200
        # Should display node details
        assert "Node One" in response.text
        # Node type is shown as emoji with title attribute
        assert 'title="Repeater"' in response.text

    def test_node_detail_displays_public_key(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that node detail page displays the full public key."""
        response = client.get("/nodes/abc123def456abc123def456abc123de")
        assert "abc123def456abc123def456abc123de" in response.text


class TestNodesPageAPIErrors:
    """Tests for nodes pages handling API errors."""

    def test_nodes_handles_api_error(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that nodes page handles API errors gracefully."""
        mock_http_client.set_response(
            "GET", "/api/v1/nodes", status_code=500, json_data=None
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/nodes")

        # Should still return 200 (page renders with empty list)
        assert response.status_code == 200

    def test_node_detail_handles_not_found(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that node detail page handles 404 from API."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes/nonexistent",
            status_code=404,
            json_data={"detail": "Node not found"},
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/nodes/nonexistent")

        # Should still return 200 (page renders but shows no node)
        assert response.status_code == 200
