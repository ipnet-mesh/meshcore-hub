"""Web-tier tests for the /feeds alias, proxy forwarding, and discovery."""

FEED_XML = '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"></rss>'


class TestFeedsAliasProxy:
    def test_alias_proxies_to_api_and_headers_survive(self, client, mock_http_client):
        """TR-8 regression: the API's Cache-Control/ETag arrive intact —
        no middleware rewrites responses that already carry cache-control."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/feeds/messages.xml",
            text=FEED_XML,
            headers={
                "content-type": "application/rss+xml; charset=utf-8",
                "cache-control": "public, max-age=300",
                "etag": '"feedetag"',
            },
        )
        response = client.get("/feeds/messages.xml")
        assert response.status_code == 200
        assert mock_http_client.last_request_url == "/api/v1/feeds/messages.xml"
        assert response.text == FEED_XML
        assert response.headers["cache-control"] == "public, max-age=300"
        assert response.headers["etag"] == '"feedetag"'
        assert response.headers["content-type"].startswith("application/rss+xml")

    def test_alias_forwards_conditional_and_origin_headers(
        self, client, mock_http_client
    ):
        """If-None-Match (end-to-end 304s) and X-Forwarded-* (absolute
        links) must reach the API tier through the alias."""
        mock_http_client.set_response(
            "GET", "/api/v1/feeds/messages.xml", text=FEED_XML
        )
        client.get(
            "/feeds/messages.xml",
            headers={
                "If-None-Match": '"abc123"',
                "X-Forwarded-Host": "hub.example.com",
                "X-Forwarded-Proto": "https",
            },
        )
        forwarded = mock_http_client.last_request_headers or {}
        assert forwarded.get("if-none-match") == '"abc123"'
        assert forwarded.get("x-forwarded-host") == "hub.example.com"
        assert forwarded.get("x-forwarded-proto") == "https"

    def test_api_proxy_forwards_if_none_match(self, client, mock_http_client):
        """The main /api proxy forwards conditional headers too (SPA ETag
        revalidation benefit, TR-5)."""
        client.get("/api/v1/messages", headers={"If-None-Match": '"etag1"'})
        forwarded = mock_http_client.last_request_headers or {}
        assert forwarded.get("if-none-match") == '"etag1"'

    def test_alias_synthesizes_forwarded_headers_without_outer_proxy(
        self, client, mock_http_client
    ):
        """Reported bug: feed links pointed at the internal API service URL.

        Without an outer reverse proxy the incoming request carries no
        X-Forwarded-Host, so the web tier must synthesize the forwarding
        headers from its own Host header + scheme — the API then builds
        item links against the public origin instead of http://api:8000.
        """
        client.get("/feeds/messages.xml", headers={"Host": "hub.example.com"})
        forwarded = mock_http_client.last_request_headers or {}
        assert forwarded.get("x-forwarded-host") == "hub.example.com"
        assert forwarded.get("x-forwarded-proto") == "http"

    def test_alias_passes_through_outer_proxy_forwarded_chain(
        self, client, mock_http_client
    ):
        """Headers set by an outer reverse proxy win over synthesis."""
        client.get(
            "/feeds/messages.xml",
            headers={
                "X-Forwarded-Host": "mesh.example.org",
                "X-Forwarded-Proto": "https",
            },
        )
        forwarded = mock_http_client.last_request_headers or {}
        assert forwarded.get("x-forwarded-host") == "mesh.example.org"
        assert forwarded.get("x-forwarded-proto") == "https"

    def test_alias_anonymous_access_allowed(self, client, mock_http_client):
        """Feeds are _OPEN in the endpoint access map — anonymous OK."""
        mock_http_client.set_response("GET", "/api/v1/feeds/nodes.xml", text=FEED_XML)
        response = client.get("/feeds/nodes.xml")
        assert response.status_code == 200

    def test_alias_404_when_feeds_disabled(
        self, web_app, client, mock_http_client, monkeypatch
    ):
        monkeypatch.setattr(
            web_app.state,
            "features",
            {**web_app.state.features, "feeds": False},
        )
        response = client.get("/feeds/messages.xml")
        assert response.status_code == 404

    def test_alias_503_in_maintenance(
        self, web_app, client, mock_http_client, monkeypatch
    ):
        """The alias shares the proxy helper, so maintenance mode gates it."""
        monkeypatch.setattr(web_app.state, "system_maintenance", True)
        response = client.get("/feeds/messages.xml")
        assert response.status_code == 503
        assert response.json()["code"] == "MAINTENANCE"


class TestFeedAutodiscovery:
    def test_spa_head_contains_links(self, client):
        html = client.get("/").text
        assert 'rel="alternate"' in html
        assert 'type="application/rss+xml"' in html
        assert 'type="application/atom+xml"' in html
        assert 'href="/feeds/messages.xml"' in html
        assert 'href="/feeds/adverts.atom"' in html
        assert 'href="/feeds/nodes.xml"' in html
        assert "Test Network — Public Messages (RSS)" in html

    def test_spa_head_omits_links_when_feeds_disabled(
        self, web_app, client, monkeypatch
    ):
        monkeypatch.setattr(
            web_app.state,
            "features",
            {**web_app.state.features, "feeds": False},
        )
        html = client.get("/").text
        assert 'rel="alternate"' not in html

    def test_spa_head_gates_per_feed(self, web_app, client, monkeypatch):
        """With the messages page disabled, its feed link is omitted but
        the other feeds are still advertised."""
        monkeypatch.setattr(
            web_app.state,
            "features",
            {**web_app.state.features, "messages": False},
        )
        html = client.get("/").text
        assert "/feeds/messages.xml" not in html
        assert "/feeds/messages.atom" not in html
        assert 'href="/feeds/nodes.xml"' in html
