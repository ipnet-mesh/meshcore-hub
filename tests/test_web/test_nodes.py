"""Tests for the nodes page routes (SPA)."""

import json

from fastapi.testclient import TestClient


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

    def test_nodes_contains_app_config(self, client: TestClient) -> None:
        """Test that nodes page contains SPA config."""
        response = client.get("/nodes")
        assert "window.__APP_CONFIG__" in response.text

    def test_nodes_contains_spa_script(self, client: TestClient) -> None:
        """Test that nodes page includes SPA application script."""
        response = client.get("/nodes")
        assert "/static/js/spa/app.js" in response.text

    def test_nodes_with_search_param(self, client: TestClient) -> None:
        """Test nodes page with search parameter returns SPA shell."""
        response = client.get("/nodes?search=test")
        assert response.status_code == 200

    def test_nodes_with_adv_type_filter(self, client: TestClient) -> None:
        """Test nodes page with adv_type filter returns SPA shell."""
        response = client.get("/nodes?adv_type=REPEATER")
        assert response.status_code == 200

    def test_nodes_with_pagination(self, client: TestClient) -> None:
        """Test nodes page with pagination parameters returns SPA shell."""
        response = client.get("/nodes?page=1&limit=10")
        assert response.status_code == 200

    def test_nodes_page_2(self, client: TestClient) -> None:
        """Test nodes page 2 returns SPA shell."""
        response = client.get("/nodes?page=2")
        assert response.status_code == 200


class TestNodeDetailPage:
    """Tests for the node detail page."""

    def test_node_detail_returns_200(self, client: TestClient) -> None:
        """Test that node detail page returns 200 status code."""
        response = client.get(
            "/nodes/abc123def456abc123def456abc123def456abc123def456abc123def456abc1"
        )
        assert response.status_code == 200

    def test_node_detail_returns_html(self, client: TestClient) -> None:
        """Test that node detail page returns HTML content."""
        response = client.get(
            "/nodes/abc123def456abc123def456abc123def456abc123def456abc123def456abc1"
        )
        assert "text/html" in response.headers["content-type"]

    def test_node_detail_contains_app_config(self, client: TestClient) -> None:
        """Test that node detail page contains SPA config."""
        response = client.get(
            "/nodes/abc123def456abc123def456abc123def456abc123def456abc123def456abc1"
        )
        assert "window.__APP_CONFIG__" in response.text

    def test_node_detail_nonexistent_returns_spa_shell(
        self, client: TestClient
    ) -> None:
        """Test that node detail for nonexistent node returns SPA shell.

        In the SPA architecture, all routes return the same shell.
        The SPA client handles 404 display when the API returns not found.
        """
        response = client.get("/nodes/nonexistent")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text


class TestNodesConfig:
    """Tests for nodes page SPA config content."""

    def test_nodes_config_has_network_name(self, client: TestClient) -> None:
        """Test that SPA config includes network name."""
        response = client.get("/nodes")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["network_name"] == "Test Network"
