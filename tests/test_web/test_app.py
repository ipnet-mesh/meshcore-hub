"""Tests for web app: config JSON escaping."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import _build_config_json, create_app

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
