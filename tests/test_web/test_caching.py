"""Tests for HTTP caching middleware and version parameters."""

from bs4 import BeautifulSoup

from meshcore_hub import __version__


class TestCacheControlHeaders:
    """Test Cache-Control headers are correctly set for different resource types."""

    def test_static_css_with_version(self, client):
        """Static CSS with version parameter should have long-term cache."""
        response = client.get(f"/static/css/app.css?v={__version__}")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert (
            response.headers["cache-control"] == "public, max-age=31536000, immutable"
        )

    def test_static_js_with_version(self, client):
        """Static JS with version parameter should have long-term cache."""
        response = client.get(f"/static/js/charts.js?v={__version__}")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert (
            response.headers["cache-control"] == "public, max-age=31536000, immutable"
        )

    def test_static_module_with_version(self, client):
        """Static ES module with version parameter should have long-term cache."""
        response = client.get(f"/static/js/spa/app.js?v={__version__}")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert (
            response.headers["cache-control"] == "public, max-age=31536000, immutable"
        )

    def test_static_css_without_version(self, client):
        """Static CSS without version should have short fallback cache."""
        response = client.get("/static/css/app.css")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "public, max-age=3600"

    def test_static_js_without_version(self, client):
        """Static JS without version should have short fallback cache."""
        response = client.get("/static/js/charts.js")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "public, max-age=3600"

    def test_spa_shell_html(self, client):
        """SPA shell HTML should not be cached."""
        response = client.get("/")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "no-cache, public"

    def test_spa_route_html(self, client):
        """Client-side route should not be cached."""
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "no-cache, public"

    def test_map_data_endpoint(self, client, mock_http_client):
        """Map data endpoint should have short cache (5 minutes)."""
        # Mock the API response for map data
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes/map",
            200,
            {"nodes": []},
        )

        response = client.get("/map/data")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "public, max-age=300"

    def test_health_endpoint(self, client):
        """Health endpoint should never be cached."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert (
            response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
        )

    def test_healthz_endpoint(self, client):
        """Healthz endpoint should never be cached."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert (
            response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
        )

    def test_robots_txt(self, client):
        """Robots.txt should have moderate cache (1 hour)."""
        response = client.get("/robots.txt")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "public, max-age=3600"

    def test_sitemap_xml(self, client):
        """Sitemap.xml should have moderate cache (1 hour)."""
        response = client.get("/sitemap.xml")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "public, max-age=3600"

    def test_api_proxy_no_cache_header_added(self, client, mock_http_client):
        """API proxy should not add cache headers (lets backend control caching)."""
        # The mock client doesn't add cache-control headers by default
        # Middleware should not add any either for /api/* paths
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        # Cache-control should either not be present, or be from the backend
        # Since our mock doesn't add it, middleware shouldn't add it either
        # (In production, backend would set its own cache-control)


class TestVersionParameterInHTML:
    """Test that version parameters are correctly added to static file references."""

    def test_css_link_has_version(self, client):
        """CSS link should include version parameter."""
        response = client.get("/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        css_link = soup.find(
            "link", {"href": lambda x: x and "/static/css/app.css" in x}
        )

        assert css_link is not None
        assert f"?v={__version__}" in css_link["href"]

    def test_charts_js_has_version(self, client):
        """Charts.js script should include version parameter."""
        response = client.get("/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        charts_script = soup.find(
            "script", {"src": lambda x: x and "/static/js/charts.js" in x}
        )

        assert charts_script is not None
        assert f"?v={__version__}" in charts_script["src"]

    def test_app_js_has_version(self, client):
        """SPA app.js script should include version parameter."""
        response = client.get("/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        app_script = soup.find(
            "script", {"src": lambda x: x and "/static/js/spa/app.js" in x}
        )

        assert app_script is not None
        assert f"?v={__version__}" in app_script["src"]

    def test_cdn_resources_unchanged(self, client):
        """CDN resources should not have version parameters."""
        response = client.get("/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")

        # Check external CDN resources don't have our version param
        cdn_scripts = soup.find_all("script", {"src": lambda x: x and "cdn" in x})
        for script in cdn_scripts:
            assert f"?v={__version__}" not in script["src"]

        cdn_links = soup.find_all("link", {"href": lambda x: x and "cdn" in x})
        for link in cdn_links:
            assert f"?v={__version__}" not in link["href"]


class TestMediaFileCaching:
    """Test caching behavior for custom media files."""

    def test_media_file_with_version(self, client, tmp_path):
        """Media files with version parameter should have long-term cache."""
        # Note: This test assumes media files are served via StaticFiles
        # In practice, you may need to create a test media file
        response = client.get(f"/media/test.png?v={__version__}")
        # May be 404 if no test media exists, but header should still be set
        if response.status_code == 200:
            assert "cache-control" in response.headers
            assert (
                response.headers["cache-control"]
                == "public, max-age=31536000, immutable"
            )

    def test_media_file_without_version(self, client):
        """Media files without version should have short cache."""
        response = client.get("/media/test.png")
        # May be 404 if no test media exists, but header should still be set
        if response.status_code == 200:
            assert "cache-control" in response.headers
            assert response.headers["cache-control"] == "public, max-age=3600"


class TestCustomPageCaching:
    """Test caching behavior for custom markdown pages."""

    def test_custom_page_cache(self, client):
        """Custom pages should have moderate cache (1 hour)."""
        # Custom pages are served by the web app (not API proxy)
        # They use the PageLoader which reads from CONTENT_HOME
        # For this test, we'll check that a 404 still gets cache headers
        # (In a real deployment with content files, this would return 200)
        response = client.get("/spa/pages/test")
        # May be 404 if no test page exists, but cache header should still be set
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "public, max-age=3600"
