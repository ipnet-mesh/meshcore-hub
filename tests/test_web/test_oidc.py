"""Tests for OIDC authentication web routes."""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestOIDCSettingsValidation:
    """Test OIDC configuration validation."""

    def test_oidc_disabled_by_default(self, client: TestClient) -> None:
        """Test that OIDC is disabled by default."""
        response = client.get("/")
        assert response.status_code == 200
        text = response.text
        config = _extract_config(text)
        assert config["oidc_enabled"] is False
        assert config["user"] is None
        assert config["is_admin"] is False
        assert config["is_member"] is False

    def test_oidc_enabled_config_injection(self, client_with_oidc: TestClient) -> None:
        """Test OIDC config injection when enabled (no session)."""
        response = client_with_oidc.get("/")
        assert response.status_code == 200
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["user"] is None
        assert config["is_admin"] is False
        assert config["is_member"] is False


class TestAuthLogin:
    """Test /auth/login endpoint."""

    def test_login_oidc_disabled(self, client: TestClient) -> None:
        """Test login returns 400 when OIDC disabled."""
        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 400

    def test_login_oidc_enabled(self, client_with_oidc: TestClient) -> None:
        """Test login redirects to IdP when OIDC enabled."""
        with patch(
            "meshcore_hub.web.app.oauth.oidc.authorize_redirect",
            new_callable=AsyncMock,
        ) as mock_redirect:
            from starlette.responses import RedirectResponse

            mock_redirect.return_value = RedirectResponse(
                url="https://idp.example.com/authorize?state=abc"
            )
            response = client_with_oidc.get(
                "/auth/login?next=/a/node-tags", follow_redirects=False
            )
            assert response.status_code == 307
            assert "idp.example.com" in response.headers["location"]


class TestAuthCallback:
    """Test /auth/callback endpoint."""

    def test_callback_oidc_disabled(self, client: TestClient) -> None:
        """Test callback returns 400 when OIDC disabled."""
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 400


class TestAuthLogout:
    """Test /auth/logout endpoint."""

    def test_logout_oidc_disabled(self, client: TestClient) -> None:
        """Test logout returns 400 when OIDC disabled."""
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 400

    def test_logout_clears_session(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test logout clears session and redirects."""
        with patch(
            "meshcore_hub.web.app.oauth.oidc.load_server_metadata",
            new_callable=AsyncMock,
        ) as mock_metadata:
            mock_metadata.return_value = {
                "end_session_endpoint": "https://idp.example.com/logout"
            }
            response = client_with_oidc_admin_session.get(
                "/auth/logout", follow_redirects=False
            )
            assert response.status_code == 307


class TestAuthUser:
    """Test /auth/user endpoint."""

    def test_user_oidc_disabled(self, client: TestClient) -> None:
        """Test user endpoint returns 400 when OIDC disabled."""
        response = client.get("/auth/user")
        assert response.status_code == 400

    def test_user_not_authenticated(self, client_with_oidc: TestClient) -> None:
        """Test user endpoint returns 401 when not logged in."""
        response = client_with_oidc.get("/auth/user")
        assert response.status_code == 401

    def test_user_admin_session(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test user endpoint returns admin user."""
        response = client_with_oidc_admin_session.get("/auth/user")
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["name"] == "Admin User"
        assert data["is_admin"] is True
        assert data["is_member"] is True

    def test_user_member_session(
        self, client_with_oidc_member_session: TestClient
    ) -> None:
        """Test user endpoint returns member user."""
        response = client_with_oidc_member_session.get("/auth/user")
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["name"] == "Member User"
        assert data["is_admin"] is False
        assert data["is_member"] is True


class TestAdminRouteProtection:
    """Test admin route protection when OIDC is enabled."""

    def test_no_session_redirects_to_login(self, client_with_oidc: TestClient) -> None:
        """Test admin route redirects to /auth/login without session."""
        response = client_with_oidc.get("/a/", follow_redirects=False)
        assert response.status_code == 307
        assert "/auth/login" in response.headers["location"]

    def test_member_session_gets_spa_shell(
        self, client_with_oidc_member_session: TestClient
    ) -> None:
        """Test member session gets SPA shell (client-side shows access denied)."""
        response = client_with_oidc_member_session.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["is_admin"] is False

    def test_admin_session_gets_spa_shell(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test admin session gets SPA shell with admin config."""
        response = client_with_oidc_admin_session.get("/a/")
        assert response.status_code == 200
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["is_admin"] is True


class TestAPIProxyWriteGating:
    """Test API proxy write method gating when OIDC enabled."""

    def test_get_not_gated(self, client_with_oidc: TestClient) -> None:
        """Test GET requests are not gated."""
        response = client_with_oidc.get("/api/v1/nodes")
        assert response.status_code != 403

    def test_post_blocked_for_non_admin(
        self, client_with_oidc_member_session: TestClient
    ) -> None:
        """Test POST blocked for member session."""
        response = client_with_oidc_member_session.post(
            "/api/v1/node-tags", json={"key": "test", "value": "test"}
        )
        assert response.status_code == 403

    def test_post_allowed_for_admin(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test POST allowed for admin session."""
        response = client_with_oidc_admin_session.post(
            "/api/v1/node-tags",
            json={"key": "test", "value": "test"},
        )
        # Will get 404 from mock since we didn't set up the endpoint,
        # but should not get 403
        assert response.status_code != 403

    def test_write_not_gated_when_oidc_disabled(self, client: TestClient) -> None:
        """Test write methods not gated when OIDC is disabled."""
        response = client.post(
            "/api/v1/node-tags", json={"key": "test", "value": "test"}
        )
        assert response.status_code != 403


class TestBackwardCompatibility:
    """Test backward compatibility when OIDC is disabled."""

    def test_oidc_disabled_config(self, client: TestClient) -> None:
        """Test config has no admin_enabled when OIDC disabled."""
        response = client.get("/")
        config = _extract_config(response.text)
        assert "admin_enabled" not in config
        assert config["oidc_enabled"] is False
        assert config["is_admin"] is False

    def test_admin_routes_serve_spa_shell_when_oidc_disabled(
        self, client: TestClient
    ) -> None:
        """Test admin routes serve SPA shell when OIDC disabled (no redirect)."""
        response = client.get("/a/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_footer_no_admin_link_when_oidc_disabled(self, client: TestClient) -> None:
        """Test footer has no admin link when OIDC disabled."""
        response = client.get("/")
        assert response.status_code == 200
        assert 'href="/a/"' not in response.text


class TestConfigInjection:
    """Test config injection values for OIDC state."""

    def test_admin_session_config(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test admin session injects correct config values."""
        response = client_with_oidc_admin_session.get("/")
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["user"]["name"] == "Admin User"
        assert config["is_admin"] is True
        assert config["is_member"] is True

    def test_member_session_config(
        self, client_with_oidc_member_session: TestClient
    ) -> None:
        """Test member session injects correct config values."""
        response = client_with_oidc_member_session.get("/")
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["user"]["name"] == "Member User"
        assert config["is_admin"] is False
        assert config["is_member"] is True

    def test_no_session_config(self, client_with_oidc: TestClient) -> None:
        """Test no session injects correct config values."""
        response = client_with_oidc.get("/")
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["user"] is None
        assert config["is_admin"] is False
        assert config["is_member"] is False


def _extract_config(text: str) -> dict[str, Any]:
    """Extract __APP_CONFIG__ from SPA HTML."""
    start = text.find("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
    end = text.find(";", start)
    return json.loads(text[start:end])  # type: ignore[no-any-return]
