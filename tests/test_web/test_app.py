"""Tests for web app: config JSON escaping, API access control."""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import (
    _AUTHENTICATED,
    _OPEN,
    _build_config_json,
    _build_endpoint_access,
    _sanitize_header_value,
    check_api_access,
    create_app,
)

from .conftest import ALL_FEATURES_ENABLED, MockHttpClient, get_app_config


@pytest.fixture
def xss_app(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with a network name containing a script injection payload."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="</script><script>alert(1)</script>",
        network_city="Test City",
        network_country="Test Country",
        network_radio_profile="Test Profile",
        network_radio_frequency=868.0,
        network_radio_bandwidth=125.0,
        network_radio_spreading_factor=7,
        network_radio_coding_rate=5,
        network_radio_tx_power=20.0,
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


class TestApiProxyQueryParams:
    """The proxy must forward repeated query params without collapsing them."""

    def test_repeated_query_params_all_forwarded(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        # Multi-valued observer filter: the backend must receive BOTH values.
        # dict(request.query_params) would drop "A" and only forward "B",
        # making OR-filtered messages disappear when a second observer is added.
        client.get("/api/v1/messages?observed_by=A&observed_by=B")

        forwarded = mock_http_client.last_request_params
        pairs = list(forwarded)  # list of (key, value) tuples
        assert ("observed_by", "A") in pairs
        assert ("observed_by", "B") in pairs

    def test_single_query_param_forwarded(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        client.get("/api/v1/messages?observed_by=A&limit=10")

        pairs = list(mock_http_client.last_request_params)
        assert ("observed_by", "A") in pairs
        assert ("limit", "10") in pairs


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

    def test_built_mapping_allows_anonymous_packet_groups(self) -> None:
        """The real mapping exposes packet-groups as open (regression for 403).

        ``v1/packet-groups`` is not a prefix of ``v1/packets`` ("packets" vs
        "packet-"), so it needs its own entry or the proxy denies it.
        """
        mapping = _build_endpoint_access(role_admin="admin")
        assert check_api_access(
            "v1/packet-groups", "GET", False, frozenset(), mapping=mapping
        )
        # Detail route is covered by prefix match.
        assert check_api_access(
            "v1/packet-groups/abc123", "GET", False, frozenset(), mapping=mapping
        )


class TestRadioConfigSettingsFallback:
    """Tests that radio config falls back to settings when params are None."""

    def test_radio_params_fall_back_to_settings(
        self, mock_http_client: MockHttpClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Radio config uses settings defaults when no CLI params are passed."""
        monkeypatch.setenv("OIDC_ENABLED", "false")
        monkeypatch.setenv("NETWORK_ANNOUNCEMENT", "")
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_radio_profile=None,
            network_radio_frequency=None,
            network_radio_bandwidth=None,
            network_radio_spreading_factor=None,
            network_radio_coding_rate=None,
            network_radio_tx_power=None,
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client

        assert app.state.network_radio_profile == "EU/UK Narrow"
        assert app.state.network_radio_frequency == 869.618
        assert app.state.network_radio_bandwidth == 62.5
        assert app.state.network_radio_spreading_factor == 8
        assert app.state.network_radio_coding_rate == 8
        assert app.state.network_radio_tx_power == 22.0


class TestFlashBannerVisibility:
    """Tests for the network announcement flash banner visibility."""

    def test_banner_present_when_announcement_set(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Banner content is exposed in the SPA config when network_announcement is set."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="Scheduled maintenance at 22:00",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert config["network_announcement"]
        assert "Scheduled maintenance at 22:00" in config["network_announcement"]

    def test_banner_absent_when_announcement_none(self, client: TestClient) -> None:
        """Banner content is absent from the config when network_announcement is not set."""
        config = get_app_config(client.get("/").text)
        assert not config["network_announcement"]

    def test_banner_absent_for_empty_string(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Banner is not exposed when announcement is an empty string."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert not config["network_announcement"]

    def test_banner_absent_for_whitespace_only(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Banner is not exposed when announcement is whitespace-only."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="   ",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert not config["network_announcement"]


class TestFlashBannerMarkdown:
    """Tests for Markdown rendering in the flash banner."""

    def test_bold_rendered(self, mock_http_client: MockHttpClient) -> None:
        """Markdown bold is rendered to <strong> in the config content."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="**important**",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert "<strong>important</strong>" in config["network_announcement"]

    def test_link_rendered(self, mock_http_client: MockHttpClient) -> None:
        """Markdown link is rendered to <a> tag in the config content."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="[click here](https://example.com)",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert (
            '<a href="https://example.com">click here</a>'
            in config["network_announcement"]
        )

    def test_raw_html_passed_through(self, mock_http_client: MockHttpClient) -> None:
        """Raw HTML in announcement is passed through by the Markdown library.

        This is safe because the announcement source is an operator-controlled
        environment variable, not user input — same trust model as custom pages
        in pages.py. The React banner renders it via dangerouslySetInnerHTML.
        """
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_announcement="<b>bold</b>",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert "<b>bold</b>" in config["network_announcement"]


class TestSystemAnnouncementBanner:
    """Tests for the non-dismissable system announcement banner."""

    def test_system_banner_present_when_set(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """System banner content is exposed and Markdown-rendered in the config."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            system_announcement="**Outage** at 22:00",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert config["system_announcement"]
        assert "<strong>Outage</strong> at 22:00" in config["system_announcement"]

    def test_system_banner_absent_when_none(self, client: TestClient) -> None:
        """System banner content is absent from the config when not set."""
        config = get_app_config(client.get("/").text)
        assert not config["system_announcement"]

    def test_system_banner_absent_for_empty_string(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """System banner is not exposed for an empty string."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            system_announcement="",
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/").text)
        assert not config["system_announcement"]

    # NOTE: system-banner stacking order and the absence of a dismiss control are
    # now rendering behaviour of the React <Announcements> component, covered by
    # the frontend test suite (components/Announcements.test.tsx).


class TestSystemMaintenance:
    """Tests for maintenance mode behaviour."""

    def test_maintenance_disables_all_features(self) -> None:
        """All feature flags are forced off in maintenance mode."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            system_maintenance=True,
            features=ALL_FEATURES_ENABLED,
        )
        assert all(value is False for value in app.state.features.values())

    def test_maintenance_nav_only_home(self, mock_http_client: MockHttpClient) -> None:
        """Config exposes all features off in maintenance, so the React nav shows only Home."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            system_maintenance=True,
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        config = get_app_config(client.get("/dashboard").text)
        assert not any(config["features"].values())

    def test_maintenance_flag_in_config_json(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """The SPA config JSON exposes system_maintenance so the SPA can gate."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            system_maintenance=True,
            features=ALL_FEATURES_ENABLED,
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        assert '"system_maintenance": true' in client.get("/").text

    def test_maintenance_off_by_default(self, client: TestClient) -> None:
        """Without maintenance, nav links render normally (regression)."""
        html = client.get("/").text
        assert '"system_maintenance": false' in html

    def test_spam_score_threshold_in_config_json(self, client: TestClient) -> None:
        """The SPA config exposes spam_score_threshold so the spam badge and the
        API hide-filter agree on what counts as spam."""
        html = client.get("/").text
        assert '"spam_score_threshold": 0.65' in html


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


class TestSanitizeHeaderValue:
    """Unit tests for the _sanitize_header_value RFC 7230 guard."""

    def test_strips_trailing_whitespace(self) -> None:
        assert _sanitize_header_value("Matt ") == "Matt"

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert _sanitize_header_value("  Matt  ") == "Matt"

    def test_strips_trailing_crlf(self) -> None:
        assert _sanitize_header_value("Matt\r\n") == "Matt"

    def test_strips_embedded_del(self) -> None:
        assert _sanitize_header_value("Ma\x7ftt") == "Matt"

    def test_strips_embedded_nul(self) -> None:
        assert _sanitize_header_value("\x00foo\x00") == "foo"

    def test_strips_embedded_cr_and_lf(self) -> None:
        assert _sanitize_header_value("Ma\r\ntt") == "Matt"

    def test_whitespace_only_yields_empty(self) -> None:
        assert _sanitize_header_value("   ") == ""

    def test_tab_preserved(self) -> None:
        # HTAB (0x09) is allowed by RFC 7230 and must survive sanitization.
        assert _sanitize_header_value("Ma\ttt") == "Ma\ttt"

    def test_clean_value_passthrough(self) -> None:
        assert _sanitize_header_value("clean") == "clean"

    def test_strips_all_ctl_chars(self) -> None:
        # Every CTL char 0x00-0x1F except HTAB/SP, plus DEL, is removed.
        removed = [chr(c) for c in range(0x00, 0x20) if chr(c) not in "\t "]
        dirty = "x" + "".join(removed) + "\x7f" + "y"
        assert _sanitize_header_value(dirty) == "xy"


class TestProxyHeaderSanitization:
    """The API proxy must sanitize X-User-Name before forwarding (regression)."""

    def test_trailing_whitespace_name_forwarded_clean(
        self,
        client_with_oidc: TestClient,
        mock_http_client: MockHttpClient,
    ) -> None:
        """Reported bug: name='Matt ' caused 502; must now forward 'Matt'."""
        dirty_user = {"sub": "user-1", "name": "Matt ", "roles": ["member"]}
        with (
            patch("meshcore_hub.web.app.get_session_user", return_value=dirty_user),
            patch("meshcore_hub.web.oidc.get_session_user", return_value=dirty_user),
        ):
            response = client_with_oidc.get("/api/v1/nodes")

        assert response.status_code != 502
        forwarded = mock_http_client.last_request_headers
        assert forwarded is not None
        assert forwarded["X-User-Name"] == "Matt"

    def test_whitespace_only_name_omits_header(
        self,
        client_with_oidc: TestClient,
        mock_http_client: MockHttpClient,
    ) -> None:
        """A whitespace-only name must NOT emit an empty X-User-Name header."""
        ws_user = {"sub": "user-1", "name": "   ", "roles": ["member"]}
        with (
            patch("meshcore_hub.web.app.get_session_user", return_value=ws_user),
            patch("meshcore_hub.web.oidc.get_session_user", return_value=ws_user),
        ):
            response = client_with_oidc.get("/api/v1/nodes")

        assert response.status_code != 502
        forwarded = mock_http_client.last_request_headers
        assert forwarded is not None
        assert "X-User-Name" not in forwarded

    def test_control_char_name_forwarded_clean(
        self,
        client_with_oidc: TestClient,
        mock_http_client: MockHttpClient,
    ) -> None:
        """Embedded DEL/CR/LF in the name must be dropped before forwarding."""
        dirty_user = {"sub": "user-1", "name": "Ma\x7f\r\ntt", "roles": ["member"]}
        with (
            patch("meshcore_hub.web.app.get_session_user", return_value=dirty_user),
            patch("meshcore_hub.web.oidc.get_session_user", return_value=dirty_user),
        ):
            response = client_with_oidc.get("/api/v1/nodes")

        assert response.status_code != 502
        forwarded = mock_http_client.last_request_headers
        assert forwarded is not None
        assert forwarded["X-User-Name"] == "Matt"


class TestBootstrapHeaderSanitization:
    """The auth-callback bootstrap must forward a sanitized X-User-Name."""

    def test_trailing_whitespace_stripped_on_bootstrap(
        self,
        client_with_oidc: TestClient,
        mock_http_client: MockHttpClient,
    ) -> None:
        """Bootstrap GET forwards clean name after strip_userinfo trims it."""
        token = {"userinfo": {"sub": "user-1", "name": "Matt "}}
        with patch(
            "meshcore_hub.web.app.oauth.oidc.authorize_access_token",
            new_callable=AsyncMock,
            return_value=token,
        ):
            client_with_oidc.get("/auth/callback", follow_redirects=False)

        forwarded = mock_http_client.last_get_headers
        assert forwarded is not None
        assert forwarded["X-User-Name"] == "Matt"

    def test_control_char_dropped_on_bootstrap(
        self,
        client_with_oidc: TestClient,
        mock_http_client: MockHttpClient,
    ) -> None:
        """Defense-in-depth: DEL survives strip_userinfo but is removed at header."""
        token = {"userinfo": {"sub": "user-1", "name": "Ma\x7ftt"}}
        with patch(
            "meshcore_hub.web.app.oauth.oidc.authorize_access_token",
            new_callable=AsyncMock,
            return_value=token,
        ):
            client_with_oidc.get("/auth/callback", follow_redirects=False)

        forwarded = mock_http_client.last_get_headers
        assert forwarded is not None
        assert forwarded["X-User-Name"] == "Matt"
