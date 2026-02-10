"""Tests for feature flags functionality."""

import json

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app
from tests.test_web.conftest import MockHttpClient


class TestFeatureFlagsConfig:
    """Test feature flags in config."""

    def test_all_features_enabled_by_default(self, client: TestClient) -> None:
        """All features should be enabled by default in config JSON."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        # Extract config JSON from script tag
        start = html.index("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
        end = html.index(";", start)
        config = json.loads(html[start:end])
        features = config["features"]
        assert all(features.values()), "All features should be enabled by default"

    def test_features_dict_has_all_keys(self, client: TestClient) -> None:
        """Features dict should have all 7 expected keys."""
        response = client.get("/")
        html = response.text
        start = html.index("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
        end = html.index(";", start)
        config = json.loads(html[start:end])
        features = config["features"]
        expected_keys = {
            "dashboard",
            "nodes",
            "advertisements",
            "messages",
            "map",
            "members",
            "pages",
        }
        assert set(features.keys()) == expected_keys

    def test_disabled_features_in_config(self, client_no_features: TestClient) -> None:
        """Disabled features should be false in config JSON."""
        response = client_no_features.get("/")
        html = response.text
        start = html.index("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
        end = html.index(";", start)
        config = json.loads(html[start:end])
        features = config["features"]
        assert all(not v for v in features.values()), "All features should be disabled"


class TestFeatureFlagsNav:
    """Test feature flags affect navigation."""

    def test_enabled_features_show_nav_links(self, client: TestClient) -> None:
        """Enabled features should show nav links."""
        response = client.get("/")
        html = response.text
        assert 'href="/dashboard"' in html
        assert 'href="/nodes"' in html
        assert 'href="/advertisements"' in html
        assert 'href="/messages"' in html
        assert 'href="/map"' in html
        assert 'href="/members"' in html

    def test_disabled_features_hide_nav_links(
        self, client_no_features: TestClient
    ) -> None:
        """Disabled features should not show nav links."""
        response = client_no_features.get("/")
        html = response.text
        assert 'href="/dashboard"' not in html
        assert 'href="/nodes"' not in html
        assert 'href="/advertisements"' not in html
        assert 'href="/messages"' not in html
        assert 'href="/map"' not in html
        assert 'href="/members"' not in html

    def test_home_link_always_present(self, client_no_features: TestClient) -> None:
        """Home link should always be present."""
        response = client_no_features.get("/")
        html = response.text
        assert 'href="/"' in html


class TestFeatureFlagsEndpoints:
    """Test feature flags affect endpoints."""

    def test_map_data_returns_404_when_disabled(
        self, client_no_features: TestClient
    ) -> None:
        """/map/data should return 404 when map feature is disabled."""
        response = client_no_features.get("/map/data")
        assert response.status_code == 404
        assert response.json()["detail"] == "Map feature is disabled"

    def test_map_data_returns_200_when_enabled(self, client: TestClient) -> None:
        """/map/data should return 200 when map feature is enabled."""
        response = client.get("/map/data")
        assert response.status_code == 200

    def test_custom_page_returns_404_when_disabled(
        self, client_no_features: TestClient
    ) -> None:
        """/spa/pages/{slug} should return 404 when pages feature is disabled."""
        response = client_no_features.get("/spa/pages/about")
        assert response.status_code == 404
        assert response.json()["detail"] == "Pages feature is disabled"

    def test_custom_pages_empty_when_disabled(
        self, client_no_features: TestClient
    ) -> None:
        """Custom pages should be empty in config when pages feature is disabled."""
        response = client_no_features.get("/")
        html = response.text
        start = html.index("window.__APP_CONFIG__ = ") + len("window.__APP_CONFIG__ = ")
        end = html.index(";", start)
        config = json.loads(html[start:end])
        assert config["custom_pages"] == []


class TestFeatureFlagsSEO:
    """Test feature flags affect SEO endpoints."""

    def test_sitemap_includes_all_when_enabled(self, client: TestClient) -> None:
        """Sitemap should include all pages when all features are enabled."""
        response = client.get("/sitemap.xml")
        assert response.status_code == 200
        content = response.text
        assert "/dashboard" in content
        assert "/nodes" in content
        assert "/advertisements" in content
        assert "/map" in content
        assert "/members" in content

    def test_sitemap_excludes_disabled_features(
        self, client_no_features: TestClient
    ) -> None:
        """Sitemap should exclude disabled features."""
        response = client_no_features.get("/sitemap.xml")
        assert response.status_code == 200
        content = response.text
        assert "/dashboard" not in content
        assert "/nodes" not in content
        assert "/advertisements" not in content
        assert "/map" not in content
        assert "/members" not in content

    def test_sitemap_always_includes_home(self, client_no_features: TestClient) -> None:
        """Sitemap should always include the home page."""
        response = client_no_features.get("/sitemap.xml")
        assert response.status_code == 200
        content = response.text
        # Home page has an empty path, so check for base URL loc
        assert "<loc>" in content

    def test_robots_txt_adds_disallow_for_disabled(
        self, client_no_features: TestClient
    ) -> None:
        """Robots.txt should add Disallow for disabled features."""
        response = client_no_features.get("/robots.txt")
        assert response.status_code == 200
        content = response.text
        assert "Disallow: /dashboard" in content
        assert "Disallow: /nodes" in content
        assert "Disallow: /advertisements" in content
        assert "Disallow: /map" in content
        assert "Disallow: /members" in content
        assert "Disallow: /pages" in content

    def test_robots_txt_default_disallows_when_enabled(
        self, client: TestClient
    ) -> None:
        """Robots.txt should only disallow messages and nodes/ when all enabled."""
        response = client.get("/robots.txt")
        assert response.status_code == 200
        content = response.text
        assert "Disallow: /messages" in content
        assert "Disallow: /nodes/" in content
        # Should not disallow the full /nodes path (only /nodes/ for detail pages)
        lines = content.strip().split("\n")
        disallow_lines = [
            line.strip() for line in lines if line.startswith("Disallow:")
        ]
        assert "Disallow: /nodes" not in disallow_lines or any(
            line == "Disallow: /nodes/" for line in disallow_lines
        )


class TestFeatureFlagsIndividual:
    """Test individual feature flags."""

    @pytest.fixture
    def _make_client(self, mock_http_client: MockHttpClient):
        """Factory to create a client with specific features disabled."""

        def _create(disabled_feature: str) -> TestClient:
            features = {
                "dashboard": True,
                "nodes": True,
                "advertisements": True,
                "messages": True,
                "map": True,
                "members": True,
                "pages": True,
            }
            features[disabled_feature] = False
            app = create_app(
                api_url="http://localhost:8000",
                api_key="test-api-key",
                network_name="Test Network",
                features=features,
            )
            app.state.http_client = mock_http_client
            return TestClient(app, raise_server_exceptions=True)

        return _create

    def test_disable_map_only(self, _make_client) -> None:
        """Disabling only map should hide map but show others."""
        client = _make_client("map")
        response = client.get("/")
        html = response.text
        assert 'href="/map"' not in html
        assert 'href="/dashboard"' in html
        assert 'href="/nodes"' in html

        # Map data endpoint should 404
        response = client.get("/map/data")
        assert response.status_code == 404

    def test_disable_dashboard_only(self, _make_client) -> None:
        """Disabling only dashboard should hide dashboard but show others."""
        client = _make_client("dashboard")
        response = client.get("/")
        html = response.text
        assert 'href="/dashboard"' not in html
        assert 'href="/nodes"' in html
        assert 'href="/map"' in html


class TestDashboardAutoDisable:
    """Test that dashboard is automatically disabled when it has no content."""

    def test_dashboard_auto_disabled_when_all_stats_off(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Dashboard should auto-disable when nodes, adverts, messages all off."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
            features={
                "dashboard": True,
                "nodes": False,
                "advertisements": False,
                "messages": False,
                "map": True,
                "members": True,
                "pages": True,
            },
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        html = response.text
        assert 'href="/dashboard"' not in html

        # Check config JSON also reflects it
        config = json.loads(html.split("window.__APP_CONFIG__ = ")[1].split(";")[0])
        assert config["features"]["dashboard"] is False

    def test_map_auto_disabled_when_nodes_off(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Map should auto-disable when nodes is off (map depends on nodes)."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
            features={
                "dashboard": True,
                "nodes": False,
                "advertisements": True,
                "messages": True,
                "map": True,
                "members": True,
                "pages": True,
            },
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        html = response.text
        assert 'href="/map"' not in html

        # Check config JSON also reflects it
        config = json.loads(html.split("window.__APP_CONFIG__ = ")[1].split(";")[0])
        assert config["features"]["map"] is False

        # Map data endpoint should 404
        response = client.get("/map/data")
        assert response.status_code == 404

    def test_dashboard_stays_enabled_with_one_stat(
        self, mock_http_client: MockHttpClient
    ) -> None:
        """Dashboard should stay enabled when at least one stat feature is on."""
        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
            features={
                "dashboard": True,
                "nodes": True,
                "advertisements": False,
                "messages": False,
                "map": True,
                "members": True,
                "pages": True,
            },
        )
        app.state.http_client = mock_http_client
        client = TestClient(app, raise_server_exceptions=True)

        response = client.get("/")
        assert 'href="/dashboard"' in response.text
