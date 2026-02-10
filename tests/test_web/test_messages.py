"""Tests for the messages page route (SPA)."""

import json

from fastapi.testclient import TestClient


class TestMessagesPage:
    """Tests for the messages page."""

    def test_messages_returns_200(self, client: TestClient) -> None:
        """Test that messages page returns 200 status code."""
        response = client.get("/messages")
        assert response.status_code == 200

    def test_messages_returns_html(self, client: TestClient) -> None:
        """Test that messages page returns HTML content."""
        response = client.get("/messages")
        assert "text/html" in response.headers["content-type"]

    def test_messages_contains_network_name(self, client: TestClient) -> None:
        """Test that messages page contains the network name."""
        response = client.get("/messages")
        assert "Test Network" in response.text

    def test_messages_contains_app_config(self, client: TestClient) -> None:
        """Test that messages page contains SPA config."""
        response = client.get("/messages")
        assert "window.__APP_CONFIG__" in response.text

    def test_messages_contains_spa_script(self, client: TestClient) -> None:
        """Test that messages page includes SPA application script."""
        response = client.get("/messages")
        assert "/static/js/spa/app.js" in response.text


class TestMessagesPageFilters:
    """Tests for messages page with query parameters.

    In the SPA architecture, all routes return the same shell.
    Query parameters are handled client-side.
    """

    def test_messages_with_type_filter(self, client: TestClient) -> None:
        """Test messages page with message type filter returns SPA shell."""
        response = client.get("/messages?message_type=direct")
        assert response.status_code == 200

    def test_messages_with_channel_filter(self, client: TestClient) -> None:
        """Test messages page with channel filter returns SPA shell."""
        response = client.get("/messages?channel_idx=0")
        assert response.status_code == 200

    def test_messages_with_search(self, client: TestClient) -> None:
        """Test messages page with search parameter returns SPA shell."""
        response = client.get("/messages?search=hello")
        assert response.status_code == 200

    def test_messages_with_pagination(self, client: TestClient) -> None:
        """Test messages page with pagination parameters returns SPA shell."""
        response = client.get("/messages?page=1&limit=25")
        assert response.status_code == 200

    def test_messages_page_2(self, client: TestClient) -> None:
        """Test messages page 2 returns SPA shell."""
        response = client.get("/messages?page=2")
        assert response.status_code == 200

    def test_messages_with_all_filters(self, client: TestClient) -> None:
        """Test messages page with multiple filters returns SPA shell."""
        response = client.get(
            "/messages?message_type=channel&channel_idx=1&page=1&limit=10"
        )
        assert response.status_code == 200


class TestMessagesConfig:
    """Tests for messages page SPA config content."""

    def test_messages_config_has_network_name(self, client: TestClient) -> None:
        """Test that SPA config includes network name."""
        response = client.get("/messages")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["network_name"] == "Test Network"
