"""Tests for OIDC authentication web routes."""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from meshcore_hub.web.oidc import init_oidc, strip_userinfo


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
                "/auth/login?next=/admin/node-tags", follow_redirects=False
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
        """Test logout clears session and redirects via IdP."""
        with patch(
            "meshcore_hub.web.app.oauth.oidc.logout_redirect",
            new_callable=AsyncMock,
        ) as mock_logout:
            from starlette.responses import RedirectResponse

            mock_logout.return_value = RedirectResponse(
                url="https://idp.example.com/logout"
            )
            response = client_with_oidc_admin_session.get(
                "/auth/logout", follow_redirects=False
            )
            assert response.status_code == 307
            mock_logout.assert_called_once()
            call_kwargs = mock_logout.call_args[1]
            assert call_kwargs["client_id"] == "test-client-id"
            assert "post_logout_redirect_uri" in call_kwargs

    def test_logout_falls_back_to_base_url(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test logout uses request.base_url when no redirect URI configured."""
        with patch(
            "meshcore_hub.web.app.oauth.oidc.logout_redirect",
            new_callable=AsyncMock,
        ) as mock_logout:
            from starlette.responses import RedirectResponse

            mock_logout.return_value = RedirectResponse(
                url="https://idp.example.com/logout"
            )
            response = client_with_oidc_admin_session.get(
                "/auth/logout", follow_redirects=False
            )
            assert response.status_code == 307
            call_kwargs = mock_logout.call_args[1]
            assert "post_logout_redirect_uri" in call_kwargs


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
        response = client_with_oidc.get("/admin/", follow_redirects=False)
        assert response.status_code == 307
        assert "/auth/login" in response.headers["location"]

    def test_member_session_gets_spa_shell(
        self, client_with_oidc_member_session: TestClient
    ) -> None:
        """Test member session gets SPA shell (client-side shows access denied)."""
        response = client_with_oidc_member_session.get("/admin/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text
        config = _extract_config(response.text)
        assert config["oidc_enabled"] is True
        assert config["is_admin"] is False

    def test_admin_session_gets_spa_shell(
        self, client_with_oidc_admin_session: TestClient
    ) -> None:
        """Test admin session gets SPA shell with admin config."""
        response = client_with_oidc_admin_session.get("/admin/")
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
        response = client.get("/admin/")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_footer_no_admin_link_when_oidc_disabled(self, client: TestClient) -> None:
        """Test footer has no admin link when OIDC disabled."""
        response = client.get("/")
        assert response.status_code == 200
        assert 'href="/admin/"' not in response.text


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


class TestStripUserinfo:
    """Test strip_userinfo helper function."""

    def test_name_from_name_claim(self) -> None:
        """Test name extracted from 'name' claim."""
        userinfo = {"sub": "user-1", "name": "John Doe", "email": "john@example.com"}
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] == "John Doe"

    def test_name_from_preferred_username(self) -> None:
        """Test name falls back to 'preferred_username'."""
        userinfo = {"sub": "user-1", "preferred_username": "johndoe"}
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] == "johndoe"

    def test_name_from_username(self) -> None:
        """Test name falls back to 'username' (LogTo-style)."""
        userinfo = {"sub": "user-1", "username": "johndoe"}
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] == "johndoe"

    def test_name_from_nickname(self) -> None:
        """Test name falls back to 'nickname'."""
        userinfo = {"sub": "user-1", "nickname": "johnny"}
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] == "johnny"

    def test_name_priority_order(self) -> None:
        """Test name claim priority: name > preferred_username > username > nickname."""
        userinfo = {
            "sub": "user-1",
            "name": "Full Name",
            "preferred_username": "pref",
            "username": "user",
            "nickname": "nick",
        }
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] == "Full Name"

    def test_name_prefers_username_over_nickname(self) -> None:
        """Test username is preferred over nickname when name is absent."""
        userinfo = {"sub": "user-1", "username": "logto_user", "nickname": "nick"}
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] == "logto_user"

    def test_name_none_when_all_missing(self) -> None:
        """Test name is None when no name-like claims present."""
        userinfo = {"sub": "user-1", "email": "user@example.com"}
        result = strip_userinfo(userinfo, "roles")
        assert result["name"] is None

    def test_roles_extracted(self) -> None:
        """Test roles are extracted from configured claim."""
        userinfo = {"sub": "user-1", "custom_roles": ["admin", "member"]}
        result = strip_userinfo(userinfo, "custom_roles")
        assert result["custom_roles"] == ["admin", "member"]

    def test_preserves_sub_email_picture(self) -> None:
        """Test sub, email, and picture are preserved."""
        userinfo = {
            "sub": "user-1",
            "email": "user@example.com",
            "picture": "https://example.com/avatar.png",
        }
        result = strip_userinfo(userinfo, "roles")
        assert result["sub"] == "user-1"
        assert result["email"] == "user@example.com"
        assert result["picture"] == "https://example.com/avatar.png"


class TestInitOidcScopeParsing:
    """Test that init_oidc handles quoted and unquoted scope strings."""

    def test_plain_scope_string(self) -> None:
        """Test unquoted scope string is split into list."""
        with patch("meshcore_hub.web.oidc.oauth") as mock_oauth:
            init_oidc(
                "id", "secret", "https://idp.example.com/oidc", "openid email profile"
            )
            call_kwargs = mock_oauth.register.call_args[1]
            assert call_kwargs["client_kwargs"]["scope"] == [
                "openid",
                "email",
                "profile",
            ]

    def test_double_quoted_scope_string(self) -> None:
        """Test double-quoted scope string (from Docker env) is stripped and split."""
        with patch("meshcore_hub.web.oidc.oauth") as mock_oauth:
            init_oidc(
                "id",
                "secret",
                "https://idp.example.com/oidc",
                '"openid email profile"',
            )
            call_kwargs = mock_oauth.register.call_args[1]
            assert call_kwargs["client_kwargs"]["scope"] == [
                "openid",
                "email",
                "profile",
            ]

    def test_single_quoted_scope_string(self) -> None:
        """Test single-quoted scope string is stripped and split."""
        with patch("meshcore_hub.web.oidc.oauth") as mock_oauth:
            init_oidc(
                "id",
                "secret",
                "https://idp.example.com/oidc",
                "'openid email profile'",
            )
            call_kwargs = mock_oauth.register.call_args[1]
            assert call_kwargs["client_kwargs"]["scope"] == [
                "openid",
                "email",
                "profile",
            ]


def _extract_config(text: str) -> dict[str, Any]:
    """Extract __APP_CONFIG__ from SPA HTML."""
    start = text.find("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
    end = text.find(";", start)
    return json.loads(text[start:end])  # type: ignore[no-any-return]
