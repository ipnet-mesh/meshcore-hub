"""Tests for OIDC authentication routes."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app
from meshcore_hub.web.oidc import LogtoOidcClient, OidcConfig, OidcUser

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
def admin_app_with_oidc(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with admin enabled and a mock OIDC client."""
    with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
        from meshcore_hub.common.config import WebSettings

        settings = WebSettings(
            _env_file=None,
            logto_app_id="test-logto-app-id",
            logto_app_secret="test-logto-app-secret",
            session_secret="test-session-secret-for-testing",
        )
        mock_settings.return_value = settings

        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
        )

    app.state.http_client = mock_http_client
    app.state.oidc_client = _make_oidc_client()
    return app


@pytest.fixture
def oidc_client(
    admin_app_with_oidc: Any, mock_http_client: MockHttpClient
) -> TestClient:
    """Create a test client with OIDC configured."""
    admin_app_with_oidc.state.http_client = mock_http_client
    return TestClient(admin_app_with_oidc, raise_server_exceptions=True)


class TestAuthLogin:
    """Tests for GET /auth/login."""

    def test_login_redirects_to_logto(self, oidc_client: TestClient) -> None:
        """Login redirects to Logto authorization endpoint."""
        response = oidc_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert "localhost:3001/oidc/auth" in location
        assert "client_id=test-client-id" in location
        assert "response_type=code" in location
        assert "scope=openid+profile+email" in location
        assert "state=" in location

    def test_login_stores_state_in_session(self, oidc_client: TestClient) -> None:
        """Login stores OAuth state parameter in session cookie."""
        response = oidc_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302
        cookies = response.cookies
        assert "meshcore_session" in cookies

    def test_login_without_oidc_client_redirects_home(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Login redirects to home when OIDC is not configured."""
        with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
            from meshcore_hub.common.config import WebSettings

            settings = WebSettings(_env_file=None)
            mock_settings.return_value = settings

            app = create_app(api_url="http://localhost:8000", network_name="Test")

        app.state.http_client = mock_http_client
        app.state.oidc_client = None
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_login_uses_configured_redirect_uri(self, oidc_client: TestClient) -> None:
        """Login uses LOGTO_REDIRECT_URI when configured."""
        oidc_client.app.state.logto_redirect_uri = "https://example.com/auth/callback"  # type: ignore[attr-defined]
        response = oidc_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert "redirect_uri=https%3A%2F%2Fexample.com" in location


class TestAuthCallback:
    """Tests for GET /auth/callback."""

    def test_callback_rejects_invalid_state(self, oidc_client: TestClient) -> None:
        """Callback rejects requests with mismatched state."""
        response = oidc_client.get(
            "/auth/callback?code=abc&state=wrong-state", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_callback_rejects_missing_state(self, oidc_client: TestClient) -> None:
        """Callback rejects requests with no state parameter."""
        response = oidc_client.get("/auth/callback?code=abc", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_callback_successful_exchange(self, oidc_client: TestClient) -> None:
        """Callback exchanges code for tokens and sets session."""
        oidc_client.app.state.logto_redirect_uri = "http://localhost:8080/auth/callback"  # type: ignore[attr-defined]

        mock_oidc = oidc_client.app.state.oidc_client  # type: ignore[attr-defined]
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

        session_client = oidc_client

        response = session_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302

        location = response.headers["location"]
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        state = params["state"][0]

        response2 = session_client.get(
            f"/auth/callback?code=test-code&state={state}", follow_redirects=False
        )
        assert response2.status_code == 302
        assert response2.headers["location"] == "/a/"

    def test_callback_without_oidc_client_redirects_home(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Callback redirects to home when OIDC is not configured."""
        with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
            from meshcore_hub.common.config import WebSettings

            settings = WebSettings(_env_file=None)
            mock_settings.return_value = settings

            app = create_app(api_url="http://localhost:8000", network_name="Test")

        app.state.http_client = mock_http_client
        app.state.oidc_client = None
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get(
            "/auth/callback?code=abc&state=xyz", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"


class TestAuthLogout:
    """Tests for GET /auth/logout."""

    def test_logout_clears_session(self, oidc_client: TestClient) -> None:
        """Logout clears the session and redirects to Logto."""
        response = oidc_client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert "localhost:3001/oidc/session/end" in location

    def test_logout_with_post_logout_uri(self, oidc_client: TestClient) -> None:
        """Logout includes post_logout_redirect_uri in Logto URL."""
        oidc_client.app.state.logto_post_logout_redirect_uri = "https://example.com/"  # type: ignore[attr-defined]
        response = oidc_client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert "post_logout_redirect_uri=" in location

    def test_logout_without_oidc_client(self, mock_http_client: MockHttpClient) -> None:
        """Logout redirects to home when OIDC is not configured."""
        with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
            from meshcore_hub.common.config import WebSettings

            settings = WebSettings(_env_file=None)
            mock_settings.return_value = settings

            app = create_app(api_url="http://localhost:8000", network_name="Test")

        app.state.http_client = mock_http_client
        app.state.oidc_client = None
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"


class TestOidcUser:
    """Tests for OidcUser data class."""

    def test_to_dict(self) -> None:
        user = OidcUser(sub="user-123", name="Test User", email="test@example.com")
        d = user.to_dict()
        assert d == {
            "sub": "user-123",
            "name": "Test User",
            "email": "test@example.com",
            "picture": None,
            "username": None,
        }

    def test_from_dict(self) -> None:
        d = {"sub": "user-456", "name": "Another", "email": "a@b.com"}
        user = OidcUser.from_dict(d)
        assert user.sub == "user-456"
        assert user.name == "Another"

    def test_round_trip(self) -> None:
        original = OidcUser(
            sub="abc", name="Test", email="t@t.com", picture="http://pic"
        )
        restored = OidcUser.from_dict(original.to_dict())
        assert restored.sub == original.sub
        assert restored.name == original.name
        assert restored.email == original.email
        assert restored.picture == original.picture


class TestOidcConfig:
    """Tests for OidcConfig."""

    def test_ready_when_configured(self) -> None:
        config = OidcConfig(
            authorization_endpoint="http://example.com/auth",
            token_endpoint="http://example.com/token",
        )
        assert config.ready is True

    def test_not_ready_when_empty(self) -> None:
        config = OidcConfig()
        assert config.ready is False


class TestRewriteUrl:
    """Tests for LogtoOidcClient._rewrite_url."""

    def test_rewrites_internal_hostname(self) -> None:
        client = LogtoOidcClient(
            client_id="id",
            client_secret="secret",
            discovery_url="http://logto:3001/oidc",
            external_url="http://logto.example.com:3001",
        )
        rewritten = client._rewrite_url("http://logto:3001/oidc/auth")
        assert rewritten == "http://logto.example.com:3001/oidc/auth"

    def test_rewrites_with_scheme_change(self) -> None:
        client = LogtoOidcClient(
            client_id="id",
            client_secret="secret",
            discovery_url="http://logto:3001/oidc",
            external_url="https://logto.example.com",
        )
        rewritten = client._rewrite_url("http://logto:3001/oidc/auth")
        assert rewritten == "https://logto.example.com/oidc/auth"

    def test_no_rewrite_when_same_hostname(self) -> None:
        client = LogtoOidcClient(
            client_id="id",
            client_secret="secret",
            discovery_url="http://localhost:3001/oidc",
            external_url="http://localhost:3001",
        )
        rewritten = client._rewrite_url("http://localhost:3001/oidc/auth")
        assert rewritten == "http://localhost:3001/oidc/auth"

    def test_no_rewrite_when_no_external_url(self) -> None:
        client = LogtoOidcClient(
            client_id="id",
            client_secret="secret",
            discovery_url="http://logto:3001/oidc",
            external_url="",
        )
        rewritten = client._rewrite_url("http://logto:3001/oidc/auth")
        assert rewritten == "http://logto:3001/oidc/auth"

    def test_no_rewrite_empty_url(self) -> None:
        client = LogtoOidcClient(
            client_id="id",
            client_secret="secret",
            discovery_url="http://logto:3001/oidc",
            external_url="http://example.com",
        )
        assert client._rewrite_url("") == ""


class TestLogtoOidcClient:
    """Tests for LogtoOidcClient."""

    def test_get_authorization_url(self) -> None:
        client = _make_oidc_client()
        url, state = client.get_authorization_url("http://localhost:8080/auth/callback")
        assert "localhost:3001/oidc/auth" in url
        assert "client_id=test-client-id" in url
        assert "response_type=code" in url
        assert state

    def test_get_authorization_url_custom_state(self) -> None:
        client = _make_oidc_client()
        url, state = client.get_authorization_url(
            "http://localhost:8080/auth/callback", state="my-custom-state"
        )
        assert state == "my-custom-state"
        assert "state=my-custom-state" in url

    def test_get_logout_url(self) -> None:
        client = _make_oidc_client()
        url = client.get_logout_url(
            id_token_hint="test-token",
            post_logout_redirect_uri="https://example.com/",
        )
        assert "localhost:3001/oidc/session/end" in url
        assert "id_token_hint=test-token" in url
        assert "post_logout_redirect_uri=" in url

    def test_get_logout_url_no_end_session(self) -> None:
        client = _make_oidc_client()
        client._config.end_session_endpoint = ""
        url = client.get_logout_url(post_logout_redirect_uri="https://example.com/")
        assert url == "https://example.com/"

    def test_build_redirect_uri(self) -> None:
        client = _make_oidc_client()
        uri = client.build_redirect_uri("http://localhost:8080")
        assert uri == "http://localhost:8080/auth/callback"

    def test_build_post_logout_uri(self) -> None:
        client = _make_oidc_client()
        uri = client.build_post_logout_uri("http://localhost:8080")
        assert uri == "http://localhost:8080/"

    def test_external_url(self) -> None:
        client = _make_oidc_client()
        assert client.external_url == "http://localhost:3001"


class TestIsAuthenticated:
    """Tests for _is_authenticated helper."""

    def test_authenticated_with_session(self, oidc_client: TestClient) -> None:
        """is_authenticated is true when session has user with sub."""
        from meshcore_hub.web.app import _is_authenticated

        request = MagicMock()
        request.session = {"user": {"sub": "user-123", "name": "Test"}}
        assert _is_authenticated(request) is True

    def test_not_authenticated_empty_session(self, oidc_client: TestClient) -> None:
        """is_authenticated is false when session is empty."""
        from meshcore_hub.web.app import _is_authenticated

        request = MagicMock()
        request.session = {}
        assert _is_authenticated(request) is False

    def test_not_authenticated_no_sub(self, oidc_client: TestClient) -> None:
        """is_authenticated is false when user dict has no sub."""
        from meshcore_hub.web.app import _is_authenticated

        request = MagicMock()
        request.session = {"user": {"name": "Test"}}
        assert _is_authenticated(request) is False

    def test_config_shows_authenticated(self, oidc_client: TestClient) -> None:
        """SPA config reflects is_authenticated when session has user."""
        oidc_client.app.state.oidc_client = _make_oidc_client()  # type: ignore[attr-defined]

        response = oidc_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302

        from urllib.parse import parse_qs, urlparse

        location = response.headers["location"]
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        state = params["state"][0]

        mock_oidc = oidc_client.app.state.oidc_client  # type: ignore[attr-defined]
        mock_oidc.exchange_code = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "access_token": "test-access-token",
                "id_token": "test-id-token",
                "token_type": "Bearer",
            }
        )
        mock_oidc.validate_id_token = MagicMock(  # type: ignore[method-assign]
            return_value={
                "sub": "user-123",
                "name": "Test User",
                "email": "test@example.com",
            }
        )

        oidc_client.get(
            f"/auth/callback?code=test-code&state={state}", follow_redirects=False
        )

        resp = oidc_client.get("/a/", follow_redirects=False)
        assert resp.status_code == 200
        text = resp.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])
        assert config["is_authenticated"] is True
