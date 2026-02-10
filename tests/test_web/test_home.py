"""Tests for the home page route (SPA)."""

import json

from fastapi.testclient import TestClient


class TestHomePage:
    """Tests for the home page."""

    def test_home_returns_200(self, client: TestClient) -> None:
        """Test that home page returns 200 status code."""
        response = client.get("/")
        assert response.status_code == 200

    def test_home_returns_html(self, client: TestClient) -> None:
        """Test that home page returns HTML content."""
        response = client.get("/")
        assert "text/html" in response.headers["content-type"]

    def test_home_contains_network_name(self, client: TestClient) -> None:
        """Test that home page contains the network name."""
        response = client.get("/")
        assert "Test Network" in response.text

    def test_home_contains_network_city(self, client: TestClient) -> None:
        """Test that home page contains the network city."""
        response = client.get("/")
        assert "Test City" in response.text

    def test_home_contains_network_country(self, client: TestClient) -> None:
        """Test that home page contains the network country."""
        response = client.get("/")
        assert "Test Country" in response.text

    def test_home_contains_app_config(self, client: TestClient) -> None:
        """Test that home page contains the SPA config JSON."""
        response = client.get("/")
        assert "window.__APP_CONFIG__" in response.text

    def test_home_config_contains_network_info(self, client: TestClient) -> None:
        """Test that SPA config contains network information."""
        response = client.get("/")
        # Extract the config JSON from the HTML
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["network_name"] == "Test Network"
        assert config["network_city"] == "Test City"
        assert config["network_country"] == "Test Country"

    def test_home_config_contains_contact_info(self, client: TestClient) -> None:
        """Test that SPA config contains contact information."""
        response = client.get("/")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["network_contact_email"] == "test@example.com"
        assert config["network_contact_discord"] == "https://discord.gg/test"

    def test_home_contains_contact_email(self, client: TestClient) -> None:
        """Test that home page contains the contact email in footer."""
        response = client.get("/")
        assert "test@example.com" in response.text

    def test_home_contains_discord_link(self, client: TestClient) -> None:
        """Test that home page contains the Discord link in footer."""
        response = client.get("/")
        assert "discord.gg/test" in response.text

    def test_home_contains_navigation(self, client: TestClient) -> None:
        """Test that home page contains navigation links."""
        response = client.get("/")
        assert 'href="/"' in response.text
        assert 'href="/nodes"' in response.text
        assert 'href="/messages"' in response.text

    def test_home_contains_spa_app_script(self, client: TestClient) -> None:
        """Test that home page includes the SPA application script."""
        response = client.get("/")
        assert "/static/js/spa/app.js" in response.text

    def test_home_unauthenticated(self, client: TestClient) -> None:
        """Test that home page config shows unauthenticated by default."""
        response = client.get("/")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is False

    def test_home_authenticated(self, client: TestClient) -> None:
        """Test that home page config shows authenticated with auth header."""
        response = client.get("/", headers={"X-Forwarded-User": "test-user"})
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is True
