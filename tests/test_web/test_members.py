"""Tests for the members page route (SPA)."""

import json

from fastapi.testclient import TestClient


class TestMembersPage:
    """Tests for the members page."""

    def test_members_returns_200(self, client: TestClient) -> None:
        """Test that members page returns 200 status code."""
        response = client.get("/members")
        assert response.status_code == 200

    def test_members_returns_html(self, client: TestClient) -> None:
        """Test that members page returns HTML content."""
        response = client.get("/members")
        assert "text/html" in response.headers["content-type"]

    def test_members_contains_network_name(self, client: TestClient) -> None:
        """Test that members page contains the network name."""
        response = client.get("/members")
        assert "Test Network" in response.text

    def test_members_contains_app_config(self, client: TestClient) -> None:
        """Test that members page contains SPA config."""
        response = client.get("/members")
        assert "window.__APP_CONFIG__" in response.text

    def test_members_contains_spa_script(self, client: TestClient) -> None:
        """Test that members page includes SPA application script."""
        response = client.get("/members")
        assert "/static/js/spa/app.js" in response.text

    def test_members_config_has_network_name(self, client: TestClient) -> None:
        """Test that SPA config includes network name."""
        response = client.get("/members")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["network_name"] == "Test Network"
