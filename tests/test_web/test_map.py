"""Tests for the map page routes."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_web.conftest import MockHttpClient


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


class TestMapDataInfrastructure:
    """Tests for infrastructure node handling in map data."""

    def test_map_data_includes_infra_center(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that map data includes infrastructure center when infra nodes exist."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Infra Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [{"key": "role", "value": "infra"}],
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

        # Should have infra_center based on infra node only
        assert data["infra_center"] is not None
        assert data["infra_center"]["lat"] == 40.0
        assert data["infra_center"]["lon"] == -74.0

    def test_map_data_infra_center_null_when_no_infra(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that infra_center is null when no infrastructure nodes exist."""
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

        assert data["infra_center"] is None

    def test_map_data_sets_is_infra_flag(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that nodes have correct is_infra flag based on role tag."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Infra Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [{"key": "role", "value": "infra"}],
                    },
                    {
                        "id": "node-2",
                        "public_key": "def456",
                        "name": "Regular Node",
                        "lat": 41.0,
                        "lon": -75.0,
                        "tags": [{"key": "role", "value": "other"}],
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
        assert nodes_by_name["Infra Node"]["is_infra"] is True
        assert nodes_by_name["Regular Node"]["is_infra"] is False

    def test_map_data_debug_includes_infra_count(
        self, web_app: Any, mock_http_client: MockHttpClient
    ) -> None:
        """Test that debug info includes infrastructure node count."""
        mock_http_client.set_response(
            "GET",
            "/api/v1/nodes",
            status_code=200,
            json_data={
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123",
                        "name": "Infra Node",
                        "lat": 40.0,
                        "lon": -74.0,
                        "tags": [{"key": "role", "value": "infra"}],
                    },
                ],
                "total": 1,
            },
        )
        web_app.state.http_client = mock_http_client

        client = TestClient(web_app, raise_server_exceptions=True)
        response = client.get("/map/data")
        data = response.json()

        assert data["debug"]["infra_nodes"] == 1


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
