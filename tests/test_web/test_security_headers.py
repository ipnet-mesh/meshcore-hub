"""Tests for web security headers and CSP nonce middleware."""

import re
from typing import Any

from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app
from tests.test_web.conftest import ALL_FEATURES_ENABLED, MockHttpClient

_NONCE_RE = re.compile(r"nonce-([A-Za-z0-9_-]{16,})")


def _make_app(**settings_overrides: Any) -> Any:
    """Build a web app with the mock HTTP client and settings overrides."""
    import meshcore_hub.common.config as config_module

    original_get_settings = config_module.get_web_settings

    try:
        if settings_overrides:
            config_module.get_web_settings = lambda: original_get_settings().model_copy(
                update=settings_overrides
            )
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
            features=ALL_FEATURES_ENABLED,
        )
    finally:
        config_module.get_web_settings = original_get_settings

    app.state.http_client = MockHttpClient()
    return app


class TestSecurityHeaders:
    """Security headers are applied to web responses."""

    def test_hardening_headers_present(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "geolocation=()" in response.headers["permissions-policy"]

    def test_csp_directives(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=True)
        csp = client.get("/").headers["content-security-policy"]
        assert csp.startswith("default-src 'self'")
        assert "script-src 'self' 'nonce-" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "img-src 'self' data: https:" in csp
        assert "connect-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_csp_extra_setting_appended(self) -> None:
        app = _make_app(web_csp_extra="img-src https://tiles.example.com")
        csp = (
            TestClient(app, raise_server_exceptions=True)
            .get("/")
            .headers["content-security-policy"]
        )
        assert csp.endswith("img-src https://tiles.example.com")

    def test_inline_scripts_carry_matching_nonce(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/")
        csp = response.headers["content-security-policy"]
        header_nonce = _NONCE_RE.search(csp)
        assert header_nonce is not None

        html = response.text
        nonce_attrs = re.findall(r'<script nonce="([^"]+)"', html)
        # Theme bootstrap + __APP_CONFIG__ scripts both carry the nonce
        assert len(nonce_attrs) == 2
        assert all(n == header_nonce.group(1) for n in nonce_attrs)
        # No un-nonced inline scripts remain (external src= scripts are
        # covered by script-src 'self')
        inline = re.findall(r"<script(?![^>]*(?:nonce|src=))[^>]*>", html)
        assert inline == []

    def test_nonce_rotates_per_request(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=True)
        csp1 = client.get("/").headers["content-security-policy"]
        csp2 = client.get("/").headers["content-security-policy"]
        nonce1 = _NONCE_RE.search(csp1)
        nonce2 = _NONCE_RE.search(csp2)
        assert nonce1 is not None and nonce2 is not None
        assert nonce1.group(1) != nonce2.group(1)

    def test_headers_on_non_html_routes(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "content-security-policy" in response.headers

        map_response = client.get("/map/data")
        assert map_response.headers["x-frame-options"] == "DENY"


class TestSecurityHeadersKillSwitch:
    """WEB_SECURITY_HEADERS=false disables all header setting."""

    def test_no_headers_when_disabled(self) -> None:
        app = _make_app(web_security_headers=False)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/")
        assert "content-security-policy" not in response.headers
        assert "x-frame-options" not in response.headers
        assert "x-content-type-options" not in response.headers
