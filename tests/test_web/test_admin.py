"""Tests for admin web routes (SPA)."""

import json
from typing import Any, Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app

from .conftest import ADMIN_USER, MockHttpClient


@pytest.fixture
def admin_app(mock_http_client: MockHttpClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Create a web app with OIDC enabled for admin access."""
    from .conftest import ALL_FEATURES_ENABLED

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "OIDC_DISCOVERY_URL",
        "https://idp.example.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("OIDC_SESSION_SECRET", "test-session-secret")

    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        features=ALL_FEATURES_ENABLED,
    )

    app.state.http_client = mock_http_client
    return app


@pytest.fixture
def admin_app_disabled(
    mock_http_client: MockHttpClient, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Create a web app with OIDC disabled (admin disabled)."""
    monkeypatch.setenv("OIDC_ENABLED", "false")
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
    )

    app.state.http_client = mock_http_client

    return app


@pytest.fixture
def admin_client(
    admin_app: Any, mock_http_client: MockHttpClient
) -> Generator[TestClient, None, None]:
    """Create a test client with OIDC admin session."""
    admin_app.state.http_client = mock_http_client
    with (
        patch("meshcore_hub.web.app.get_session_user", return_value=ADMIN_USER),
        patch("meshcore_hub.web.oidc.get_session_user", return_value=ADMIN_USER),
    ):
        yield TestClient(admin_app, raise_server_exceptions=True)


@pytest.fixture
def admin_client_disabled(
    admin_app_disabled: Any, mock_http_client: MockHttpClient
) -> TestClient:
    """Create a test client with admin disabled."""
    admin_app_disabled.state.http_client = mock_http_client
    return TestClient(admin_app_disabled, raise_server_exceptions=True)


class TestAdminHome:
    """Tests for admin home page (SPA).

    In the SPA architecture, admin routes serve the same shell HTML.
    Admin access control is handled client-side based on
    window.__APP_CONFIG__.is_admin when OIDC is enabled.
    """

    def test_admin_home_returns_spa_shell(self, admin_client):
        """Test admin home page returns the SPA shell."""
        response = admin_client.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_admin_home_config_is_admin(self, admin_client):
        """Test admin config shows is_admin: true."""
        response = admin_client.get("/a/")
        config = _extract_config(response.text)
        assert config["is_admin"] is True
        assert config["oidc_enabled"] is True

    def test_admin_home_disabled_returns_spa_shell(
        self,
        admin_client_disabled,
    ):
        """Test admin page returns SPA shell even when OIDC disabled.

        The SPA catch-all serves the shell for all routes.
        Client-side code checks oidc_enabled/is_admin to show/hide admin UI.
        """
        response = admin_client_disabled.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text


class TestAdminNodeTags:
    """Tests for admin node tags page (SPA)."""

    def test_node_tags_page_returns_spa_shell(self, admin_client):
        """Test node tags page returns the SPA shell."""
        response = admin_client.get("/a/node-tags")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_node_tags_page_with_public_key(self, admin_client):
        """Test node tags page with public_key param returns SPA shell."""
        response = admin_client.get(
            "/a/node-tags?public_key=abc123def456abc123def456abc123de",
        )
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_node_tags_page_disabled_returns_spa_shell(
        self,
        admin_client_disabled,
    ):
        """Test node tags page returns SPA shell even when admin is disabled."""
        response = admin_client_disabled.get("/a/node-tags")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text


class TestAdminFooterLink:
    """Tests for admin link in footer."""

    def test_admin_link_visible_when_oidc_enabled(self, admin_client):
        """Test that admin link appears in footer when OIDC is enabled."""
        response = admin_client.get("/")
        assert response.status_code == 200
        assert 'href="/a/"' in response.text
        assert "Admin" in response.text

    def test_admin_link_hidden_when_oidc_disabled(self, admin_client_disabled):
        """Test that admin link does not appear in footer when OIDC disabled."""
        response = admin_client_disabled.get("/")
        assert response.status_code == 200
        assert 'href="/a/"' not in response.text


def _extract_config(text: str) -> dict[str, Any]:
    """Extract __APP_CONFIG__ from SPA HTML."""
    start = text.find("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
    end = text.find(";", start)
    return json.loads(text[start:end])  # type: ignore[no-any-return]
