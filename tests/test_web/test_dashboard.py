"""Tests for the dashboard page route."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_web.conftest import MockHttpClient


class TestDashboardPage:
    """Tests for the dashboard page."""

    def test_dashboard_returns_200(self, client: TestClient) -> None:
        """Test that dashboard page returns 200 status code."""
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_dashboard_returns_html(self, client: TestClient) -> None:
        """Test that dashboard page returns HTML content."""
        response = client.get("/dashboard")
        assert "text/html" in response.headers["content-type"]

    def test_dashboard_contains_network_name(self, client: TestClient) -> None:
        """Test that dashboard page contains the network name."""
        response = client.get("/dashboard")
        assert "Test Network" in response.text

    def test_dashboard_serves_spa_shell(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """The dashboard route serves the SPA shell.

        Dashboard statistics are fetched and rendered client-side by React from
        the API, so they are not present in the server-rendered shell; we assert
        the mount point and embedded config instead.
        """
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert 'id="app"' in response.text
        assert "window.__APP_CONFIG__" in response.text


class TestDashboardPageAPIErrors:
    """Tests for dashboard page handling API errors."""

    def test_dashboard_handles_api_error(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that dashboard page handles API errors gracefully."""
        # Set error response for stats endpoint
        mock_http_client.set_response(
            "GET", "/api/v1/dashboard/stats", status_code=500, json_data=None
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/dashboard")

        # Should still return 200 (page renders with defaults)
        assert response.status_code == 200

    def test_dashboard_handles_api_not_found(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that dashboard page handles API 404 gracefully."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/dashboard/stats",
            status_code=404,
            json_data={"detail": "Not found"},
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/dashboard")

        # Should still return 200 (page renders with defaults)
        assert response.status_code == 200
