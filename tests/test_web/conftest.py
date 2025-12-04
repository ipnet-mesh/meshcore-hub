"""Web dashboard test fixtures."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from meshcore_hub.web.app import create_app


class MockHttpClient:
    """Mock HTTP client for testing web routes."""

    def __init__(self) -> None:
        """Initialize mock client with default responses."""
        self._responses: dict[str, dict[str, Any]] = {}
        self._default_responses()

    def _default_responses(self) -> None:
        """Set up default mock API responses."""
        # Default stats response
        self._responses["GET:/api/v1/dashboard/stats"] = {
            "status_code": 200,
            "json": {
                "total_nodes": 10,
                "active_nodes": 5,
                "total_messages": 100,
                "messages_today": 15,
                "total_advertisements": 50,
                "channel_message_counts": {"0": 30, "1": 20},
            },
        }

        # Default nodes list response
        self._responses["GET:/api/v1/nodes"] = {
            "status_code": 200,
            "json": {
                "items": [
                    {
                        "id": "node-1",
                        "public_key": "abc123def456abc123def456abc123de",
                        "name": "Node One",
                        "adv_type": "REPEATER",
                        "last_seen": "2024-01-01T12:00:00Z",
                        "tags": [],
                    },
                    {
                        "id": "node-2",
                        "public_key": "def456abc123def456abc123def456ab",
                        "name": "Node Two",
                        "adv_type": "CLIENT",
                        "last_seen": "2024-01-01T11:00:00Z",
                        "tags": [
                            {"key": "lat", "value": "40.7128"},
                            {"key": "lon", "value": "-74.0060"},
                        ],
                    },
                ],
                "total": 2,
            },
        }

        # Default single node response
        self._responses["GET:/api/v1/nodes/abc123def456abc123def456abc123de"] = {
            "status_code": 200,
            "json": {
                "id": "node-1",
                "public_key": "abc123def456abc123def456abc123de",
                "name": "Node One",
                "adv_type": "REPEATER",
                "last_seen": "2024-01-01T12:00:00Z",
                "tags": [],
            },
        }

        # Default messages response
        self._responses["GET:/api/v1/messages"] = {
            "status_code": 200,
            "json": {
                "items": [
                    {
                        "id": "msg-1",
                        "message_type": "direct",
                        "pubkey_prefix": "abc123",
                        "text": "Hello World",
                        "received_at": "2024-01-01T12:00:00Z",
                        "snr": -5.5,
                        "hops": 2,
                    },
                    {
                        "id": "msg-2",
                        "message_type": "channel",
                        "channel_idx": 0,
                        "text": "Channel message",
                        "received_at": "2024-01-01T11:00:00Z",
                        "snr": None,
                        "hops": None,
                    },
                ],
                "total": 2,
            },
        }

        # Default advertisements response
        self._responses["GET:/api/v1/advertisements"] = {
            "status_code": 200,
            "json": {
                "items": [
                    {
                        "id": "adv-1",
                        "public_key": "abc123def456abc123def456abc123de",
                        "name": "Node One",
                        "adv_type": "REPEATER",
                        "received_at": "2024-01-01T12:00:00Z",
                    },
                ],
                "total": 1,
            },
        }

        # Default telemetry response
        self._responses["GET:/api/v1/telemetry"] = {
            "status_code": 200,
            "json": {
                "items": [
                    {
                        "id": "tel-1",
                        "node_public_key": "abc123def456abc123def456abc123de",
                        "parsed_data": {"battery_level": 85.5},
                        "received_at": "2024-01-01T12:00:00Z",
                    },
                ],
                "total": 1,
            },
        }

        # Default members response (empty)
        self._responses["GET:/api/v1/members"] = {
            "status_code": 200,
            "json": {
                "items": [],
                "total": 0,
                "limit": 100,
                "offset": 0,
            },
        }

        # Health check response
        self._responses["GET:/health"] = {
            "status_code": 200,
            "json": {"status": "healthy"},
        }

    def set_response(
        self, method: str, path: str, status_code: int = 200, json_data: Any = None
    ) -> None:
        """Set a custom response for a specific endpoint.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path
            status_code: Response status code
            json_data: JSON response body
        """
        key = f"{method}:{path}"
        self._responses[key] = {
            "status_code": status_code,
            "json": json_data,
        }

    def _create_response(self, key: str) -> Response:
        """Create a mock response for a given key."""
        response_data = self._responses.get(key)
        if response_data is None:
            # Return 404 for unknown endpoints
            response = MagicMock(spec=Response)
            response.status_code = 404
            response.json.return_value = {"detail": "Not found"}
            return response

        response = MagicMock(spec=Response)
        response.status_code = response_data["status_code"]
        response.json.return_value = response_data["json"]
        return response

    async def get(self, path: str, params: dict | None = None) -> Response:
        """Mock GET request."""
        # Try exact match first
        key = f"GET:{path}"
        if key in self._responses:
            return self._create_response(key)

        # Try without query params for list endpoints
        base_path = path.split("?")[0]
        key = f"GET:{base_path}"
        return self._create_response(key)

    async def post(
        self, path: str, json: dict | None = None, params: dict | None = None
    ) -> Response:
        """Mock POST request."""
        key = f"POST:{path}"
        return self._create_response(key)

    async def aclose(self) -> None:
        """Mock close method."""
        pass


@pytest.fixture
def mock_http_client() -> MockHttpClient:
    """Create a mock HTTP client."""
    return MockHttpClient()


@pytest.fixture
def web_app(mock_http_client: MockHttpClient) -> Any:
    """Create a web app with mocked HTTP client."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        network_contact_discord="https://discord.gg/test",
    )

    # Override the lifespan to use our mock client
    app.state.http_client = mock_http_client

    return app


@pytest.fixture
def client(web_app: Any, mock_http_client: MockHttpClient) -> TestClient:
    """Create a test client for the web app.

    Note: We don't use the context manager to skip lifespan events
    since we've already set up the mock client.
    """
    # Ensure the mock client is attached
    web_app.state.http_client = mock_http_client
    return TestClient(web_app, raise_server_exceptions=True)


@pytest.fixture
def mock_http_client_with_members() -> MockHttpClient:
    """Create a mock HTTP client with members data."""
    client = MockHttpClient()
    client.set_response(
        "GET",
        "/api/v1/members",
        200,
        {
            "items": [
                {
                    "id": "member-1",
                    "name": "Alice",
                    "callsign": "W1ABC",
                    "role": "Admin",
                    "description": None,
                    "contact": "alice@example.com",
                    "public_key": None,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                },
                {
                    "id": "member-2",
                    "name": "Bob",
                    "callsign": "W2XYZ",
                    "role": "Member",
                    "description": None,
                    "contact": None,
                    "public_key": None,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                },
            ],
            "total": 2,
            "limit": 100,
            "offset": 0,
        },
    )
    return client


@pytest.fixture
def web_app_with_members(mock_http_client_with_members: MockHttpClient) -> Any:
    """Create a web app with members API responses configured."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        network_contact_discord="https://discord.gg/test",
    )

    app.state.http_client = mock_http_client_with_members

    return app


@pytest.fixture
def client_with_members(
    web_app_with_members: Any, mock_http_client_with_members: MockHttpClient
) -> TestClient:
    """Create a test client with members API responses configured."""
    web_app_with_members.state.http_client = mock_http_client_with_members
    return TestClient(web_app_with_members, raise_server_exceptions=True)
