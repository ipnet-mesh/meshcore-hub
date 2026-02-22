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
def auth_headers_basic() -> dict[str, str]:
    """Basic auth header forwarded by reverse proxy."""
    return {
        "Authorization": "Basic dGVzdDp0ZXN0",
    }


@pytest.fixture
def auth_headers_auth_request() -> dict[str, str]:
    """Auth-request style header from upstream proxy."""
    return {
        "X-Auth-Request-User": "test-user-id",
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

    def test_admin_home_config_authenticated_with_basic_auth(
        self, admin_client, auth_headers_basic
    ):
        """Test admin config shows is_authenticated: true with basic auth header."""
        response = admin_client.get("/a/", headers=auth_headers_basic)
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        assert config["is_authenticated"] is True

    def test_admin_home_config_authenticated_with_auth_request_header(
        self, admin_client, auth_headers_auth_request
    ):
        """Test admin config shows is_authenticated with X-Auth-Request-User."""
        response = admin_client.get("/a/", headers=auth_headers_auth_request)
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


class TestAdminApiProxyAuth:
    """Tests for admin API proxy authentication enforcement.

    When admin is enabled, mutating requests (POST/PUT/DELETE/PATCH) through
    the API proxy must require authentication via X-Forwarded-User header.
    This prevents unauthenticated users from performing admin operations
    even though the web app's HTTP client has a service-level API key.
    """

    def test_proxy_post_blocked_without_auth(self, admin_client, mock_http_client):
        """POST to API proxy returns 401 without auth headers."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})
        response = admin_client.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
        )
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_proxy_put_blocked_without_auth(self, admin_client, mock_http_client):
        """PUT to API proxy returns 401 without auth headers."""
        mock_http_client.set_response("PUT", "/api/v1/members/1", 200, {"id": "1"})
        response = admin_client.put(
            "/api/v1/members/1",
            json={"name": "Updated"},
        )
        assert response.status_code == 401

    def test_proxy_delete_blocked_without_auth(self, admin_client, mock_http_client):
        """DELETE to API proxy returns 401 without auth headers."""
        mock_http_client.set_response("DELETE", "/api/v1/members/1", 204, None)
        response = admin_client.delete("/api/v1/members/1")
        assert response.status_code == 401

    def test_proxy_patch_blocked_without_auth(self, admin_client, mock_http_client):
        """PATCH to API proxy returns 401 without auth headers."""
        mock_http_client.set_response("PATCH", "/api/v1/members/1", 200, {"id": "1"})
        response = admin_client.patch(
            "/api/v1/members/1",
            json={"name": "Patched"},
        )
        assert response.status_code == 401

    def test_proxy_post_allowed_with_auth(
        self, admin_client, auth_headers, mock_http_client
    ):
        """POST to API proxy succeeds with auth headers."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})
        response = admin_client.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
            headers=auth_headers,
        )
        assert response.status_code == 201

    def test_proxy_post_allowed_with_basic_auth(
        self, admin_client, auth_headers_basic, mock_http_client
    ):
        """POST to API proxy succeeds with basic auth header."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})
        response = admin_client.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
            headers=auth_headers_basic,
        )
        assert response.status_code == 201

    def test_proxy_put_allowed_with_auth(
        self, admin_client, auth_headers, mock_http_client
    ):
        """PUT to API proxy succeeds with auth headers."""
        mock_http_client.set_response("PUT", "/api/v1/members/1", 200, {"id": "1"})
        response = admin_client.put(
            "/api/v1/members/1",
            json={"name": "Updated"},
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_proxy_delete_allowed_with_auth(
        self, admin_client, auth_headers, mock_http_client
    ):
        """DELETE to API proxy succeeds with auth headers."""
        mock_http_client.set_response("DELETE", "/api/v1/members/1", 204, None)
        response = admin_client.delete(
            "/api/v1/members/1",
            headers=auth_headers,
        )
        # 204 from the mock API
        assert response.status_code == 204

    def test_proxy_get_allowed_without_auth(self, admin_client, mock_http_client):
        """GET to API proxy is allowed without auth (read-only)."""
        response = admin_client.get("/api/v1/nodes")
        assert response.status_code == 200

    def test_proxy_post_allowed_when_admin_disabled(
        self, admin_client_disabled, mock_http_client
    ):
        """POST to API proxy allowed when admin is disabled (no proxy auth)."""
        mock_http_client.set_response("POST", "/api/v1/members", 201, {"id": "new"})
        response = admin_client_disabled.post(
            "/api/v1/members",
            json={"name": "Test", "member_id": "test"},
        )
        # Should reach the API (which may return its own auth error, but
        # the proxy itself should not block it)
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
