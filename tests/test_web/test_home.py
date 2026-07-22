"""Tests for the home page route (SPA)."""

from fastapi.testclient import TestClient

from tests.test_web.conftest import get_app_config


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
        config = get_app_config(client.get("/").text)
        assert config["network_name"] == "Test Network"
        assert config["network_city"] == "Test City"
        assert config["network_country"] == "Test Country"

    def test_home_config_contains_contact_info(self, client: TestClient) -> None:
        """Test that SPA config contains contact information for the React footer."""
        config = get_app_config(client.get("/").text)
        assert config["network_contact_email"] == "test@example.com"
        assert config["network_contact_discord"] == "https://discord.gg/test"

    def test_home_contains_spa_mount(self, client: TestClient) -> None:
        """Test that home page renders the React SPA mount point."""
        response = client.get("/")
        assert 'id="app"' in response.text
