"""Tests for admin web routes (SPA)."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app
from meshcore_hub.web.oidc import LogtoOidcClient, OidcConfig

from .conftest import MockHttpClient


def _make_oidc_client() -> LogtoOidcClient:
    """Create an OIDC client with pre-populated discovery config."""
    client = LogtoOidcClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        discovery_url="http://logto:3001/oidc",
        external_url="http://localhost:3001",
    )
    client._config = OidcConfig(
        authorization_endpoint="http://localhost:3001/oidc/auth",
        token_endpoint="http://localhost:3001/oidc/token",
        userinfo_endpoint="http://localhost:3001/oidc/me",
        end_session_endpoint="http://localhost:3001/oidc/session/end",
        jwks_uri="http://localhost:3001/oidc/jwks",
        issuer="http://localhost:3001/oidc",
    )
    return client


@pytest.fixture
def admin_app(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with admin enabled (Logto configured)."""
    with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
        from meshcore_hub.common.config import WebSettings

        settings = WebSettings(
            _env_file=None,
            logto_app_id="test-logto-app-id",
            logto_app_secret="test-logto-app-secret",
            session_secret="test-session-secret-for-admin-tests",
        )
        mock_settings.return_value = settings

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
    app.state.oidc_client = _make_oidc_client()
    return app


@pytest.fixture
def admin_app_disabled(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with admin disabled (no Logto configuration)."""
    with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
        from meshcore_hub.common.config import WebSettings

        settings = WebSettings(
            _env_file=None,
            logto_app_id=None,
            logto_app_secret=None,
        )
        mock_settings.return_value = settings

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
    app.state.oidc_client = None
    return app


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

    def test_admin_home_returns_spa_shell(self, admin_client):
        """Test admin home page returns the SPA shell."""
        response = admin_client.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_admin_home_config_admin_enabled(self, admin_client):
        """Test admin config shows admin_enabled: true when Logto is configured."""
        response = admin_client.get("/a/")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["admin_enabled"] is True

    def test_admin_home_config_not_authenticated(self, admin_client):
        """Test admin config shows is_authenticated: false (OIDC not yet implemented)."""
        response = admin_client.get("/a/")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is False

    def test_admin_home_disabled_returns_spa_shell(self, admin_client_disabled):
        """Test admin page returns SPA shell even when disabled.

        The SPA catch-all serves the shell for all routes.
        Client-side code checks admin_enabled to show/hide admin UI.
        """
        response = admin_client_disabled.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_admin_home_disabled_config(self, admin_client_disabled):
        """Test admin config shows admin_enabled: false when Logto is not configured."""
        response = admin_client_disabled.get("/a/")
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

    def test_node_tags_page_disabled_returns_spa_shell(self, admin_client_disabled):
        """Test node tags page returns SPA shell even when admin is disabled."""
        response = admin_client_disabled.get("/a/node-tags")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_node_tags_page_unauthenticated(self, admin_client):
        """Test node tags page returns SPA shell without authentication."""
        response = admin_client.get("/a/node-tags")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text


class TestAdminApiProxyAuth:
    """Tests for admin API proxy authentication enforcement.

    When admin is enabled, mutating requests (POST/PUT/DELETE/PATCH) through
    the API proxy must require authentication via Logto OIDC session.
    This prevents unauthenticated users from performing admin operations
    even though the web app's HTTP client has a service-level API key.
    """

    def test_proxy_post_blocked_without_auth(self, admin_client, mock_http_client):
        """POST to API proxy returns 401 without auth (OIDC session not implemented)."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})
        response = admin_client.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
        )
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_proxy_put_blocked_without_auth(self, admin_client, mock_http_client):
        """PUT to API proxy returns 401 without auth."""
        mock_http_client.set_response("PUT", "/api/v1/members/1", 200, {"id": "1"})
        response = admin_client.put(
            "/api/v1/members/1",
            json={"name": "Updated"},
        )
        assert response.status_code == 401

    def test_proxy_delete_blocked_without_auth(self, admin_client, mock_http_client):
        """DELETE to API proxy returns 401 without auth."""
        mock_http_client.set_response("DELETE", "/api/v1/members/1", 204, None)
        response = admin_client.delete("/api/v1/members/1")
        assert response.status_code == 401

    def test_proxy_patch_blocked_without_auth(self, admin_client, mock_http_client):
        """PATCH to API proxy returns 401 without auth."""
        mock_http_client.set_response("PATCH", "/api/v1/members/1", 200, {"id": "1"})
        response = admin_client.patch(
            "/api/v1/members/1",
            json={"name": "Patched"},
        )
        assert response.status_code == 401

    def test_proxy_get_allowed_without_auth(self, admin_client, mock_http_client):
        """GET to API proxy is allowed without auth (read-only)."""
        response = admin_client.get("/api/v1/nodes")
        assert response.status_code == 200

    def test_proxy_post_allowed_when_admin_disabled(
        self, admin_client_disabled, mock_http_client
    ):
        """POST to API proxy allowed when admin is disabled (no auth required)."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})
        response = admin_client_disabled.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
        )
        assert response.status_code == 201

    def test_proxy_post_allowed_when_authenticated(
        self, admin_client, mock_http_client
    ):
        """POST to API proxy is allowed when user is authenticated via OIDC session."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})

        mock_oidc = admin_client.app.state.oidc_client
        mock_oidc.exchange_code = AsyncMock(
            return_value={
                "access_token": "test-access-token",
                "id_token": "test-id-token",
                "token_type": "Bearer",
            }
        )
        mock_oidc.validate_id_token = MagicMock(
            return_value={
                "sub": "user-123",
                "name": "Test User",
                "email": "test@example.com",
            }
        )
        admin_client.app.state.logto_redirect_uri = "http://testserver/auth/callback"

        login_resp = admin_client.get("/auth/login", follow_redirects=False)
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(login_resp.headers["location"])
        state = parse_qs(parsed.query)["state"][0]

        admin_client.get(
            f"/auth/callback?code=test-code&state={state}", follow_redirects=False
        )

        response = admin_client.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
        )
        assert response.status_code == 201


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
