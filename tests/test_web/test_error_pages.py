"""Tests for custom error page rendering."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app

from .conftest import ALL_FEATURES_ENABLED, MockHttpClient


@pytest.fixture
def error_app(mock_http_client: MockHttpClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Create a web app for testing error pages."""
    monkeypatch.setenv("OIDC_ENABLED", "false")
    monkeypatch.setenv("WEB_DATETIME_LOCALE", "en-US")
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        features=ALL_FEATURES_ENABLED,
    )
    app.state.http_client = mock_http_client
    return app


@pytest.fixture
def error_client(error_app: Any, mock_http_client: MockHttpClient) -> TestClient:
    return TestClient(error_app, raise_server_exceptions=False)


@pytest.fixture
def oidc_broken_app(
    mock_http_client: MockHttpClient, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Create a web app with OIDC enabled but broken config."""
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_ID", "broken")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "broken")
    monkeypatch.setenv(
        "OIDC_DISCOVERY_URL",
        "https://nonexistent.example.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("OIDC_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("WEB_DATETIME_LOCALE", "en-US")
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        features=ALL_FEATURES_ENABLED,
    )
    app.state.http_client = mock_http_client
    return app


@pytest.fixture
def oidc_broken_client(
    oidc_broken_app: Any, mock_http_client: MockHttpClient
) -> TestClient:
    return TestClient(oidc_broken_app, raise_server_exceptions=False)


class TestUnhandledExceptions:
    """Test custom error page rendering for unhandled exceptions."""

    def test_500_returns_html(self, oidc_broken_client: TestClient) -> None:
        """Test 500 from OIDC misconfiguration returns styled HTML."""
        response = oidc_broken_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 500
        assert "text/html" in response.headers["content-type"]
        assert "500" in response.text
        assert "Internal server error" in response.text
        assert "Go Home" in response.text

    def test_500_html_has_no_js_dependency(
        self, oidc_broken_client: TestClient
    ) -> None:
        """Test error page is self-contained (no JS dependencies)."""
        response = oidc_broken_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 500
        assert "<style>" in response.text
        assert "window.__APP_CONFIG__" not in response.text

    def test_500_html_shows_network_name(self, oidc_broken_client: TestClient) -> None:
        """Test error page includes the network name."""
        response = oidc_broken_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 500
        assert "Test Network" in response.text

    def test_404_api_returns_json(self, error_client: TestClient) -> None:
        """Test 404 on /api/ path returns JSON."""
        response = error_client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert "detail" in data


class TestErrorPageTheme:
    """Test error page respects theme setting."""

    def test_dark_theme(self, oidc_broken_client: TestClient) -> None:
        """Test error page uses dark theme by default."""
        response = oidc_broken_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 500
        assert 'data-theme="dark"' in response.text

    def test_light_theme(
        self, mock_http_client: MockHttpClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test error page uses light theme when configured."""
        monkeypatch.setenv("OIDC_ENABLED", "true")
        monkeypatch.setenv("OIDC_CLIENT_ID", "broken")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "broken")
        monkeypatch.setenv(
            "OIDC_DISCOVERY_URL",
            "https://nonexistent.example.com/.well-known/openid-configuration",
        )
        monkeypatch.setenv("OIDC_SESSION_SECRET", "test-session-secret")
        monkeypatch.setenv("WEB_THEME", "light")
        monkeypatch.setenv("WEB_DATETIME_LOCALE", "en-US")
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 500
        assert 'data-theme="light"' in response.text
