"""Tests for the map page routes."""

from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.test_web.conftest import MEMBER_USER, MockHttpClient


class TestMapPage:
    """Tests for the map page."""

    def test_map_returns_200(self, client: TestClient) -> None:
        """Test that map page returns 200 status code."""
        response = client.get("/map")
        assert response.status_code == 200

    def test_map_returns_html(self, client: TestClient) -> None:
        """Test that map page returns HTML content."""
        response = client.get("/map")
        assert "text/html" in response.headers["content-type"]

    def test_map_contains_network_name(self, client: TestClient) -> None:
        """Test that map page contains the network name."""
        response = client.get("/map")
        assert "Test Network" in response.text

    def test_map_contains_leaflet(self, client: TestClient) -> None:
        """Test that map page includes Leaflet library."""
        response = client.get("/map")
        # Should include Leaflet JS/CSS
        assert "leaflet" in response.text.lower()


class TestMapDataEndpoint:
    """Tests for the map data JSON endpoint."""

    def test_map_data_returns_200(self, client: TestClient) -> None:
        """Test that map data endpoint returns 200 status code."""
        response = client.get("/map/data")
        assert response.status_code == 200

    def test_map_data_returns_json(self, client: TestClient) -> None:
        """Test that map data endpoint returns JSON content."""
        response = client.get("/map/data")
        assert "application/json" in response.headers["content-type"]

    def test_map_data_contains_nodes(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data contains nodes with location."""
        response = client.get("/map/data")
        data = response.json()

        assert "nodes" in data
        # The mock includes a node with lat/lon tags
        nodes = data["nodes"]
        # Should have at least one node with location
        assert len(nodes) == 1
        assert nodes[0]["name"] == "Node Two"
        assert nodes[0]["lat"] == 40.7128
        assert nodes[0]["lon"] == -74.0060

    def test_map_data_contains_center(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data contains network center location."""
        response = client.get("/map/data")
        data = response.json()

        assert "center" in data
        center = data["center"]
        assert center["lat"] == 40.7128
        assert center["lon"] == -74.0060

    def test_map_data_excludes_nodes_without_location(
        self, client: TestClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data excludes nodes without location tags."""
        response = client.get("/map/data")
        data = response.json()

        nodes = data["nodes"]
        # Node One has no location tags, so should not appear
        node_names = [n["name"] for n in nodes]
        assert "Node One" not in node_names


class TestMapDataProfilesAccess:
    """Tests for viewer-gated profile data in /map/data."""

    PROFILES_PAYLOAD = {
        "items": [
            {
                "id": "profile-1",
                "name": "Op One",
                "callsign": "OP1ABC",
                "roles": ["operator"],
            }
        ],
        "total": 1,
    }

    @staticmethod
    def _restrict_profiles(web_app: Any) -> None:
        """Restrict GET v1/user/profiles to the member role."""
        web_app.state.endpoint_access["v1/user/profiles"]["GET"] = frozenset({"member"})

    def test_restricted_profiles_hidden_from_anonymous(
        self, web_app_with_oidc: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Anonymous viewers get no profiles when the mapping restricts them."""
        self._restrict_profiles(web_app_with_oidc)
        web_app_with_oidc.state.http_client = mock_http_client

        client = TestClient(web_app_with_oidc, raise_server_exceptions=True)
        response = client.get("/map/data")

        assert response.status_code == 200
        assert response.json()["profiles"] == []
        # Viewer-dependent payload must never be publicly cacheable
        assert "private" in response.headers["cache-control"]

    def test_restricted_profiles_visible_to_member(
        self, web_app_with_oidc: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Viewers with the required role still receive profiles."""
        self._restrict_profiles(web_app_with_oidc)
        mock_http_client.set_response(
            "GET", "/api/v1/user/profiles", json_data=self.PROFILES_PAYLOAD
        )
        web_app_with_oidc.state.http_client = mock_http_client

        with (
            patch("meshcore_hub.web.app.get_session_user", return_value=MEMBER_USER),
            patch("meshcore_hub.web.oidc.get_session_user", return_value=MEMBER_USER),
        ):
            client = TestClient(web_app_with_oidc, raise_server_exceptions=True)
            response = client.get("/map/data")

        assert response.status_code == 200
        profiles = response.json()["profiles"]
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Op One"
        assert "private" in response.headers["cache-control"]

    def test_open_mapping_serves_profiles_to_anonymous(
        self, web_app_with_oidc: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Default open mapping serves profiles even to anonymous viewers."""
        mock_http_client.set_response(
            "GET", "/api/v1/user/profiles", json_data=self.PROFILES_PAYLOAD
        )
        web_app_with_oidc.state.http_client = mock_http_client

        client = TestClient(web_app_with_oidc, raise_server_exceptions=True)
        response = client.get("/map/data")

        assert response.status_code == 200
        assert len(response.json()["profiles"]) == 1
        # OIDC enabled => payload may vary by viewer; keep it private
        assert "private" in response.headers["cache-control"]

    def test_oidc_disabled_keeps_public_cache(self, client: TestClient) -> None:
        """Without OIDC the payload is identical for everyone; public is safe."""
        response = client.get("/map/data")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=300"


class TestMapDataAPIErrors:
    """Tests for map data handling API errors."""

    def test_map_data_handles_api_error(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data handles API errors gracefully."""
        mock_http_client.set_response(
            "GET", "/api/v1/nodes", status_code=500, json_data=None
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")

        # Should still return 200 with empty nodes
        assert response.status_code == 200
        data = response.json()
        assert data["nodes"] == []
        assert "center" in data


class TestMapDataFiltering:
    """Tests for map data location filtering."""

    def test_map_data_filters_invalid_lat(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data filters nodes with invalid latitude."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Bad Lat Node",
                        "tags": [
                            {"key": "lat", "value": "not-a-number"},
                            {"key": "lon", "value": "-74.0060"},
                        ],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        # Node with invalid lat should be excluded
        assert len(data["nodes"]) == 0

    def test_map_data_filters_missing_lon(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data filters nodes with missing longitude."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "No Lon Node",
                        "tags": [
                            {"key": "lat", "value": "40.7128"},
                        ],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        # Node with only lat should be excluded
        assert len(data["nodes"]) == 0

    def test_map_data_filters_zero_coordinates(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data filters nodes with (0, 0) coordinates."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Zero Coord Node",
                        "lat": 0.0,
                        "lon": 0.0,
                        "tags": [],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        # Node at (0, 0) should be excluded
        assert len(data["nodes"]) == 0

    def test_map_data_uses_model_coordinates_as_fallback(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data uses model lat/lon when tags are not present."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Model Coords Node",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "tags": [],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        # Node should use model coordinates
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["lat"] == 51.5074
        assert data["nodes"][0]["lon"] == -0.1278

    def test_map_data_prefers_tag_coordinates_over_model(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that tag coordinates take priority over model coordinates."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Both Coords Node",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "tags": [
                            {"key": "lat", "value": "40.7128"},
                            {"key": "lon", "value": "-74.0060"},
                        ],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        # Node should use tag coordinates, not model
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["lat"] == 40.7128
        assert data["nodes"][0]["lon"] == -74.0060


class TestMapDataAdoptedNodes:
    """Tests for adopted node handling in map data."""

    def test_map_data_includes_adopted_center(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data includes adopted center when adopted nodes exist."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Adopted Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [],
                        "adopted_by": {
                            "user_id": "user-1",
                            "name": "Operator",
                            "callsign": "W1ABC",
                            "profile_id": "profile-1",
                        },
                    },
                    {
                        "id": "node-2",
                        "public_key": "def456",
                        "name": "Regular Node",
                        "lat": 41.0,
                        "lon": -75.0,
                        "tags": [],
                    },
                ],
                "total": 2,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        assert data["adopted_center"] is not None
        assert data["adopted_center"]["lat"] == 40.0
        assert data["adopted_center"]["lon"] == -74.0

    def test_map_data_adopted_center_null_when_no_adopted(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that adopted_center is null when no adopted nodes exist."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Regular Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        assert data["adopted_center"] is None

    def test_map_data_sets_is_adopted_flag(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that nodes have correct is_adopted flag based on adoption."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Adopted Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [],
                        "adopted_by": {
                            "user_id": "user-1",
                            "name": "Operator",
                            "callsign": "W1ABC",
                            "profile_id": "profile-1",
                        },
                    },
                    {
                        "id": "node-2",
                        "public_key": "def456",
                        "name": "Regular Node",
                        "lat": 41.0,
                        "lon": -75.0,
                        "tags": [],
                    },
                ],
                "total": 2,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        nodes_by_name = {n["name"]: n for n in data["nodes"]}
        assert nodes_by_name["Adopted Node"]["is_adopted"] is True
        assert nodes_by_name["Regular Node"]["is_adopted"] is False

    def test_map_data_debug_includes_adopted_count(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that debug info includes adopted node count."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Adopted Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [],
                        "adopted_by": {
                            "user_id": "user-1",
                            "name": "Operator",
                            "callsign": "W1ABC",
                            "profile_id": "profile-1",
                        },
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        assert data["debug"]["adopted_nodes"] == 1


class TestMapDataAdoptedByFilter:
    """Tests for map data adopted_by filter parameter."""

    def test_map_data_accepts_adopted_by_param(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data endpoint accepts adopted_by query parameter."""
        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data?adopted_by=some-profile-uuid")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "profiles" in data

    def test_map_data_adopted_by_empty_returns_all(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data without adopted_by returns nodes normally."""
        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        assert response.status_code == 200
        data = response.json()
        # Default mock has 2 nodes, 1 with coordinates
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["name"] == "Node Two"


class TestMapDataPagination:
    """Tests that /map/data follows API pagination instead of one 500-item page.

    Regression tests: the endpoint used to fetch a single ``limit=500`` page
    (the API's hard max), so networks with more than 500 nodes silently hid
    stale/offline nodes — including adopted infrastructure — from the
    unfiltered map, while the ``adopted_by`` filter (applied before the limit)
    still showed them.
    """

    @staticmethod
    def _node(
        idx: int,
        name: str,
        lat: float | None = None,
        lon: float | None = None,
        last_seen: str | None = "2024-01-01T12:00:00Z",
        adopted_by: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": f"node-{idx}",
            "public_key": f"{idx:064x}",
            "name": name,
            "adv_type": "REPEATER",
            "lat": lat,
            "lon": lon,
            "last_seen": last_seen,
            "tags": [],
            "adopted_by": adopted_by,
        }

    def test_map_data_includes_nodes_beyond_first_page(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """A stale adopted node on page 2 must appear in the unfiltered map."""
        calls: list[dict | None] = []

        def handler(params: dict | None) -> dict[str, Any]:
            calls.append(params)
            offset = (params or {}).get("offset", 0)
            if offset == 0:
                items = [self._node(1, "Recent Node", lat=41.0, lon=-75.0)]
            else:
                items = [
                    self._node(
                        2,
                        "Stale Repeater",
                        lat=40.0,
                        lon=-74.0,
                        last_seen="2023-06-01T00:00:00Z",
                        adopted_by={
                            "user_id": "user-1",
                            "name": "Operator",
                            "callsign": "W1ABC",
                            "profile_id": "profile-1",
                        },
                    )
                ]
            return {"status_code": 200, "json": {"items": items, "total": 2}}

        mock_http_client.set_paged_response("GET", "/api/v1/nodes", handler)

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        assert response.status_code == 200
        data = response.json()

        # Both pages were fetched
        assert len(calls) == 2
        nodes_by_name = {n["name"]: n for n in data["nodes"]}
        assert "Recent Node" in nodes_by_name
        assert "Stale Repeater" in nodes_by_name
        assert nodes_by_name["Stale Repeater"]["is_adopted"] is True
        assert data["adopted_center"] == {"lat": 40.0, "lon": -74.0}
        # debug.total_nodes reports the API total, not the page length
        assert data["debug"]["total_nodes"] == 2

    def test_map_data_forwards_adopted_by_on_every_page(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """The adopted_by filter must be forwarded to every page request."""
        calls: list[dict | None] = []

        def handler(params: dict | None) -> dict[str, Any]:
            # Snapshot: the caller mutates the same params dict between pages
            calls.append(dict(params) if params else None)
            offset = (params or {}).get("offset", 0)
            items = [self._node(offset + 1, f"Node {offset}", lat=40.0, lon=-74.0)]
            return {"status_code": 200, "json": {"items": items, "total": 2}}

        mock_http_client.set_paged_response("GET", "/api/v1/nodes", handler)

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data?adopted_by=some-profile-uuid")
        assert response.status_code == 200

        assert [c.get("offset") if c else None for c in calls] == [0, 1]
        for params in calls:
            assert params is not None
            assert params.get("adopted_by") == "some-profile-uuid"
            assert params.get("limit") == 500

    def test_map_data_terminates_on_short_page_without_total(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """A short page with no total field means "last page" — no extra calls."""
        calls: list[dict | None] = []

        def handler(params: dict | None) -> dict[str, Any]:
            calls.append(params)
            return {
                "status_code": 200,
                "json": {"items": [self._node(1, "Only Node", lat=40.0, lon=-74.0)]},
            }

        mock_http_client.set_paged_response("GET", "/api/v1/nodes", handler)

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        assert response.status_code == 200
        data = response.json()

        assert len(calls) == 1
        assert [n["name"] for n in data["nodes"]] == ["Only Node"]

    def test_map_data_pagination_capped_at_max_pages(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """A pathological API reporting a huge total must not loop forever."""
        from meshcore_hub.web.app import MAP_MAX_PAGES

        calls: list[dict | None] = []

        def handler(params: dict | None) -> dict[str, Any]:
            calls.append(params)
            offset = (params or {}).get("offset", 0)
            items = [self._node(offset, f"Node {offset}", lat=40.0, lon=-74.0)]
            return {"status_code": 200, "json": {"items": items, "total": 10**9}}

        mock_http_client.set_paged_response("GET", "/api/v1/nodes", handler)

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        assert response.status_code == 200
        data = response.json()

        assert len(calls) == MAP_MAX_PAGES
        assert len(data["nodes"]) == MAP_MAX_PAGES
        # debug.total_nodes still reports the API-reported total
        assert data["debug"]["total_nodes"] == 10**9

    def test_map_data_keeps_partial_results_when_later_page_fails(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """A failure on page 2 keeps the nodes collected from page 1."""
        calls: list[dict | None] = []

        def handler(params: dict | None) -> dict[str, Any]:
            calls.append(params)
            offset = (params or {}).get("offset", 0)
            if offset == 0:
                return {
                    "status_code": 200,
                    "json": {
                        "items": [self._node(1, "First Page Node", 40.0, -74.0)],
                        "total": 3,
                    },
                }
            return {"status_code": 500, "json": None}

        mock_http_client.set_paged_response("GET", "/api/v1/nodes", handler)

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        assert response.status_code == 200
        data = response.json()

        assert len(calls) == 2
        assert [n["name"] for n in data["nodes"]] == ["First Page Node"]

    def test_map_data_paginates_profiles(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """The operator dropdown source (profiles) is paginated too."""
        calls: list[dict | None] = []

        def handler(params: dict | None) -> dict[str, Any]:
            # Snapshot: the caller mutates the same params dict between pages
            calls.append(dict(params) if params else None)
            offset = (params or {}).get("offset", 0)
            items: list[dict[str, Any]]
            if offset == 0:
                items = [{"id": "p1", "name": "Op One", "callsign": None, "roles": []}]
            else:
                items = [{"id": "p2", "name": "Op Two", "callsign": None, "roles": []}]
            return {"status_code": 200, "json": {"items": items, "total": 2}}

        mock_http_client.set_paged_response("GET", "/api/v1/user/profiles", handler)

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        assert response.status_code == 200
        data = response.json()

        assert len(calls) == 2
        assert {p["id"] for p in data["profiles"]} == {"p1", "p2"}
