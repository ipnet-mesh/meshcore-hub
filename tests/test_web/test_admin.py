"""Tests for admin web routes (SPA)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app

from .conftest import MockHttpClient


@pytest.fixture
def admin_app(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with admin enabled."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        admin_enabled=True,
    )

    app.state.http_client = mock_http_client

    return app


@pytest.fixture
def admin_app_disabled(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with admin disabled."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        admin_enabled=False,
    )

    app.state.http_client = mock_http_client

    return app


@pytest.fixture
def auth_headers() -> dict:
    """Authentication headers for admin requests."""
    return {
        "X-Forwarded-User": "test-user-id",
        "X-Forwarded-Email": "test@example.com",
        "X-Forwarded-Preferred-Username": "testuser",
    }


@pytest.fixture
def admin_client(admin_app: Any, mock_http_client: MockHttpClient) -> TestClient:
    """Create a test client with admin enabled."""
    admin_app.state.http_client = mock_http_client
    return TestClient(admin_app, raise_server_exceptions=True)


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
    window.__APP_CONFIG__.admin_enabled and is_authenticated.
    """

    def test_admin_home_returns_spa_shell(self, admin_client, auth_headers):
        """Test admin home page returns the SPA shell."""
        response = admin_client.get("/a/", headers=auth_headers)
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_admin_home_config_admin_enabled(self, admin_client, auth_headers):
        """Test admin config shows admin_enabled: true."""
        response = admin_client.get("/a/", headers=auth_headers)
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["admin_enabled"] is True

    def test_admin_home_config_authenticated(self, admin_client, auth_headers):
        """Test admin config shows is_authenticated: true with auth headers."""
        response = admin_client.get("/a/", headers=auth_headers)
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is True

    def test_admin_home_disabled_returns_spa_shell(
        self, admin_client_disabled, auth_headers
    ):
        """Test admin page returns SPA shell even when disabled.

        The SPA catch-all serves the shell for all routes.
        Client-side code checks admin_enabled to show/hide admin UI.
        """
        response = admin_client_disabled.get("/a/", headers=auth_headers)
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_admin_home_disabled_config(self, admin_client_disabled, auth_headers):
        """Test admin config shows admin_enabled: false when disabled."""
        response = admin_client_disabled.get("/a/", headers=auth_headers)
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["admin_enabled"] is False

    def test_admin_home_unauthenticated_returns_spa_shell(self, admin_client):
        """Test admin page returns SPA shell without authentication.

        The SPA catch-all serves the shell for all routes.
        Client-side code checks is_authenticated to show access denied.
        """
        response = admin_client.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_admin_home_unauthenticated_config(self, admin_client):
        """Test admin config shows is_authenticated: false without auth headers."""
        response = admin_client.get("/a/")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is False


class TestAdminNodeTags:
    """Tests for admin node tags page (SPA)."""

    def test_node_tags_page_returns_spa_shell(self, admin_client, auth_headers):
        """Test node tags page returns the SPA shell."""
        response = admin_client.get("/a/node-tags", headers=auth_headers)
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_node_tags_page_with_public_key(self, admin_client, auth_headers):
        """Test node tags page with public_key param returns SPA shell."""
        response = admin_client.get(
            "/a/node-tags?public_key=abc123def456abc123def456abc123de",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_node_tags_page_disabled_returns_spa_shell(
        self, admin_client_disabled, auth_headers
    ):
        """Test node tags page returns SPA shell even when admin is disabled."""
        response = admin_client_disabled.get("/a/node-tags", headers=auth_headers)
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_node_tags_page_unauthenticated(self, admin_client):
        """Test node tags page returns SPA shell without authentication."""
        response = admin_client.get("/a/node-tags")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text


class TestAdminFooterLink:
    """Tests for admin link in footer."""

    def test_admin_link_visible_when_enabled(self, admin_client):
        """Test that admin link appears in footer when enabled."""
        response = admin_client.get("/")
        assert response.status_code == 200
        assert 'href="/a/"' in response.text
        assert "Admin" in response.text

    def test_admin_link_hidden_when_disabled(self, admin_client_disabled):
        """Test that admin link does not appear in footer when disabled."""
        response = admin_client_disabled.get("/")
        assert response.status_code == 200
        assert 'href="/a/"' not in response.text
