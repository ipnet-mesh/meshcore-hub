"""Tests for web app: config JSON escaping, API access control."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import (
    _AUTHENTICATED,
    _OPEN,
    _build_config_json,
    check_api_access,
    create_app,
)

from .conftest import ALL_FEATURES_ENABLED, MockHttpClient


@pytest.fixture
def xss_app(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with a network name containing a script injection payload."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="</script><script>alert(1)</script>",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        features=ALL_FEATURES_ENABLED,
    )
    app.state.http_client = mock_http_client
    return app


@pytest.fixture
def xss_client(xss_app: Any, mock_http_client: MockHttpClient) -> TestClient:
    """Create a test client whose network_name contains a script injection payload."""
    xss_app.state.http_client = mock_http_client
    return TestClient(xss_app, raise_server_exceptions=True)


class TestConfigJsonXssEscaping:
    """Tests that _build_config_json escapes </script> to prevent XSS breakout."""

    def test_script_tag_escaped_in_rendered_html(self, xss_client: TestClient) -> None:
        """Config value containing </script> is escaped to <\\/script> in the HTML."""
        response = xss_client.get("/")
        assert response.status_code == 200

        html = response.text

        # The literal "</script>" must NOT appear inside the config JSON block.
        # Find the config JSON assignment to isolate the embedded block.
        config_marker = "window.__APP_CONFIG__ = "
        start = html.find(config_marker)
        assert start != -1, "Config JSON block not found in rendered HTML"
        start += len(config_marker)
        end = html.find(";", start)
        config_block = html[start:end]

        # The raw closing tag must be escaped
        assert "</script>" not in config_block
        assert "<\\/script>" in config_block

    def test_normal_config_values_unaffected(self, client: TestClient) -> None:
        """Config values without special characters render unchanged."""
        response = client.get("/")
        assert response.status_code == 200

        html = response.text
        config_marker = "window.__APP_CONFIG__ = "
        start = html.find(config_marker)
        assert start != -1
        start += len(config_marker)
        end = html.find(";", start)
        config_block = html[start:end]

        config = json.loads(config_block)
        assert config["network_name"] == "Test Network"
        assert config["network_city"] == "Test City"
        assert config["network_country"] == "Test Country"

    def test_escaped_json_is_parseable(self, xss_client: TestClient) -> None:
        """The escaped JSON is still valid and parseable by json.loads."""
        response = xss_client.get("/")
        assert response.status_code == 200

        html = response.text
        config_marker = "window.__APP_CONFIG__ = "
        start = html.find(config_marker)
        assert start != -1
        start += len(config_marker)
        end = html.find(";", start)
        config_block = html[start:end]

        # json.loads handles <\/ sequences correctly (they are valid JSON)
        config = json.loads(config_block)
        assert isinstance(config, dict)
        # The parsed value should contain the original unescaped string
        assert config["network_name"] == "</script><script>alert(1)</script>"

    def test_build_config_json_direct_escaping(self, web_app: Any) -> None:
        """Calling _build_config_json directly escapes </ sequences."""
        from starlette.requests import Request

        # Inject a malicious value into the app state
        web_app.state.network_name = "</script><script>alert(1)</script>"

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
        request = Request(scope)

        result = _build_config_json(web_app, request)

        # Raw output must not contain literal "</script>"
        assert "</script>" not in result
        assert "<\\/script>" in result

        # Result must still be valid JSON
        parsed = json.loads(result)
        assert parsed["network_name"] == "</script><script>alert(1)</script>"

    def test_build_config_json_no_escaping_needed(self, web_app: Any) -> None:
        """_build_config_json leaves normal values intact when no </ present."""
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
        request = Request(scope)

        result = _build_config_json(web_app, request)

        # No escaping artifacts for normal values
        assert "<\\/" not in result

        parsed = json.loads(result)
        assert parsed["network_name"] == "Test Network"
        assert parsed["network_city"] == "Test City"

    def test_build_config_json_includes_test_role_name(self, web_app: Any) -> None:
        """_build_config_json includes role_names.test in the config."""
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
        request = Request(scope)

        result = _build_config_json(web_app, request)
        parsed = json.loads(result)
        assert "role_names" in parsed
        assert "test" in parsed["role_names"]
        assert parsed["role_names"]["test"] == "test"


class TestCheckApiAccess:
    """Unit tests for check_api_access with _OPEN, _AUTHENTICATED, and role-based levels."""

    def test_open_allows_anonymous(self) -> None:
        mapping = {"v1/nodes": {"GET": _OPEN}}
        assert check_api_access("v1/nodes", "GET", False, frozenset(), mapping=mapping)

    def test_authenticated_requires_oidc_session(self) -> None:
        mapping = {"v1/user/profile": {"PUT": _AUTHENTICATED}}
        assert check_api_access(
            "v1/user/profile",
            "PUT",
            True,
            frozenset(),
            user_id="user-1",
            mapping=mapping,
        )

    def test_authenticated_rejects_no_session(self) -> None:
        mapping = {"v1/user/profile": {"PUT": _AUTHENTICATED}}
        assert not check_api_access(
            "v1/user/profile",
            "PUT",
            True,
            frozenset(),
            user_id=None,
            mapping=mapping,
        )

    def test_authenticated_rejects_oidc_disabled(self) -> None:
        mapping = {"v1/user/profile": {"PUT": _AUTHENTICATED}}
        assert not check_api_access(
            "v1/user/profile",
            "PUT",
            False,
            frozenset(),
            user_id="user-1",
            mapping=mapping,
        )

    def test_authenticated_ignores_roles(self) -> None:
        mapping = {"v1/user/profile": {"PUT": _AUTHENTICATED}}
        assert check_api_access(
            "v1/user/profile",
            "PUT",
            True,
            frozenset(),
            user_id="user-1",
            mapping=mapping,
        )

    def test_role_required_denies_roleless(self) -> None:
        roles = frozenset({"admin", "operator"})
        mapping = {"v1/adoptions": {"POST": roles}}
        assert not check_api_access(
            "v1/adoptions",
            "POST",
            True,
            frozenset(),
            user_id="user-1",
            mapping=mapping,
        )

    def test_role_required_allows_matching_role(self) -> None:
        roles = frozenset({"admin", "operator"})
        mapping = {"v1/adoptions": {"POST": roles}}
        assert check_api_access(
            "v1/adoptions",
            "POST",
            True,
            frozenset({"operator"}),
            user_id="user-1",
            mapping=mapping,
        )


class TestFlashBannerVisibility:
    """Tests for the network announcement flash banner visibility."""

    def test_banner_present_when_announcement_set(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Banner HTML is present when network_announcement is set."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="Scheduled maintenance at 22:00",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        assert 'id="flash-banner"' in html
        assert "Scheduled maintenance at 22:00" in html

    def test_banner_absent_when_announcement_none(self, client: TestClient) -> None:
        """Banner HTML is absent when network_announcement is not set."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        assert 'id="flash-banner"' not in html

    def test_banner_absent_for_empty_string(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Banner is not shown when announcement is an empty string."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert 'id="flash-banner"' not in response.text

    def test_banner_absent_for_whitespace_only(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Banner is not shown when announcement is whitespace-only."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="   ",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert 'id="flash-banner"' not in response.text


class TestFlashBannerMarkdown:
    """Tests for Markdown rendering in the flash banner."""

    def test_bold_rendered(self, mock_http_client: MockHttpClient) -> None:
        """Markdown bold is rendered to <strong>."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="**important**",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "<strong>important</strong>" in response.text

    def test_link_rendered(self, mock_http_client: MockHttpClient) -> None:
        """Markdown link is rendered to <a> tag."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="[click here](https://example.com)",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert '<a href="https://example.com">click here</a>' in response.text

    def test_raw_html_passed_through(self, mock_http_client: MockHttpClient) -> None:
        """Raw HTML in announcement is passed through by the Markdown library.

        This is safe because the announcement source is an operator-controlled
        environment variable, not user input — same trust model as custom pages
        in pages.py.
        """
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="<b>bold</b>",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "<b>bold</b>" in response.text


class TestRolelessUserProfileUpdate:
    """Integration test: role-less OIDC user can PUT their own profile through the proxy."""

    def test_roleless_user_can_update_profile(
        self,
        client_with_oidc_no_roles_session: TestClient,
        mock_http_client: MockHttpClient,
    ) -> None:
        mock_http_client.set_response(
            "PUT",
            "/api/v1/user/profile/noroles-1",
            200,
            {"id": "profile-1", "name": "No Roles User", "callsign": None},
        )
        response = client_with_oidc_no_roles_session.put(
            "/api/v1/user/profile/noroles-1",
            json={"callsign": "NR1"},
        )
        assert response.status_code == 200
