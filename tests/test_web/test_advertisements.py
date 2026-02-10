"""Tests for the advertisements page route (SPA)."""

import json

from fastapi.testclient import TestClient


class TestAdvertisementsPage:
    """Tests for the advertisements page."""

    def test_advertisements_returns_200(self, client: TestClient) -> None:
        """Test that advertisements page returns 200 status code."""
        response = client.get("/advertisements")
        assert response.status_code == 200

    def test_advertisements_returns_html(self, client: TestClient) -> None:
        """Test that advertisements page returns HTML content."""
        response = client.get("/advertisements")
        assert "text/html" in response.headers["content-type"]

    def test_advertisements_contains_network_name(self, client: TestClient) -> None:
        """Test that advertisements page contains the network name."""
        response = client.get("/advertisements")
        assert "Test Network" in response.text

    def test_advertisements_contains_app_config(self, client: TestClient) -> None:
        """Test that advertisements page contains SPA config."""
        response = client.get("/advertisements")
        assert "window.__APP_CONFIG__" in response.text

    def test_advertisements_contains_spa_script(self, client: TestClient) -> None:
        """Test that advertisements page includes SPA application script."""
        response = client.get("/advertisements")
        assert "/static/js/spa/app.js" in response.text


class TestAdvertisementsPageFilters:
    """Tests for advertisements page with query parameters.

    In the SPA architecture, all routes return the same shell.
    Query parameters are handled client-side.
    """

    def test_advertisements_with_search(self, client: TestClient) -> None:
        """Test advertisements page with search parameter returns SPA shell."""
        response = client.get("/advertisements?search=node")
        assert response.status_code == 200

    def test_advertisements_with_member_filter(self, client: TestClient) -> None:
        """Test advertisements page with member_id filter returns SPA shell."""
        response = client.get("/advertisements?member_id=alice")
        assert response.status_code == 200

    def test_advertisements_with_public_key_filter(self, client: TestClient) -> None:
        """Test advertisements page with public_key filter returns SPA shell."""
        response = client.get(
            "/advertisements?public_key=abc123def456abc123def456abc123de"
        )
        assert response.status_code == 200

    def test_advertisements_with_pagination(self, client: TestClient) -> None:
        """Test advertisements page with pagination parameters returns SPA shell."""
        response = client.get("/advertisements?page=1&limit=25")
        assert response.status_code == 200

    def test_advertisements_page_2(self, client: TestClient) -> None:
        """Test advertisements page 2 returns SPA shell."""
        response = client.get("/advertisements?page=2")
        assert response.status_code == 200

    def test_advertisements_with_all_filters(self, client: TestClient) -> None:
        """Test advertisements page with multiple filters returns SPA shell."""
        response = client.get(
            "/advertisements?search=test&member_id=alice&page=1&limit=10"
        )
        assert response.status_code == 200


class TestAdvertisementsConfig:
    """Tests for advertisements page SPA config content."""

    def test_advertisements_config_has_network_name(self, client: TestClient) -> None:
        """Test that SPA config includes network name."""
        response = client.get("/advertisements")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["network_name"] == "Test Network"

    def test_advertisements_config_unauthenticated(self, client: TestClient) -> None:
        """Test that SPA config shows unauthenticated without auth header."""
        response = client.get("/advertisements")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is False
