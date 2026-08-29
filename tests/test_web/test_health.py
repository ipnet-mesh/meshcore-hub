"""Tests for the health check endpoints."""

from typing import Any

from fastapi.testclient import TestClient

from meshcore_hub import __version__
from tests.test_web.conftest import MockHttpClient


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Test that health endpoint returns 200 status code."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client: TestClient) -> None:
        """Test that health endpoint returns JSON content."""
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]

    def test_health_returns_healthy_status(self, client: TestClient) -> None:
        """Test that health endpoint returns healthy status."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_returns_version(self, client: TestClient) -> None:
        """Test that health endpoint returns version."""
        response = client.get("/health")
        data = response.json()
        assert data["version"] == __version__


class TestHealthReadyEndpoint:
    """Tests for the /health/ready endpoint."""

    def test_health_ready_returns_200(self, client: TestClient) -> None:
        """Test that health/ready endpoint returns 200 status code."""
        response = client.get("/health/ready")
        assert response.status_code == 200

    def test_health_ready_returns_json(self, client: TestClient) -> None:
        """Test that health/ready endpoint returns JSON content."""
        response = client.get("/health/ready")
        assert "application/json" in response.headers["content-type"]

    def test_health_ready_returns_ready_status(self, client: TestClient) -> None:
        """Test that health/ready returns ready status when API is connected."""
        response = client.get("/health/ready")
        data = response.json()
        assert data["status"] == "ready"
        assert data["api"] == "connected"

    def test_health_ready_with_api_error(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that health/ready handles API errors gracefully."""
        mock_http_client.set_response("GET", "/health", status_code=500, json_data=None)
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert "status 500" in data["api"]

    def test_health_ready_with_api_404(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that health/ready handles API 404 response."""
        mock_http_client.set_response(
            "GET", "/health", status_code=404, json_data={"detail": "Not found"}
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert "status 404" in data["api"]

    def test_health_ready_with_api_unreachable(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that health/ready returns 503 when the API call raises."""
        web_app.state.http_client = mock_http_client
        mock_http_client.set_response(
            "GET", "/health", exc=RuntimeError("connection refused")
        )

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["api"] == "RuntimeError"
