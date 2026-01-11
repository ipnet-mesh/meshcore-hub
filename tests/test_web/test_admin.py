"""Tests for admin web routes."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.app import create_app

from .conftest import MockHttpClient


@pytest.fixture
def mock_http_client_admin() -> MockHttpClient:
    """Create a mock HTTP client for admin tests."""
    client = MockHttpClient()

    # Mock the nodes API response for admin dropdown
    client.set_response(
        "GET",
        "/api/v1/nodes",
        200,
        {
            "items": [
                {
                    "public_key": "abc123def456abc123def456abc123de",
                    "name": "Node One",
                    "adv_type": "REPEATER",
                    "first_seen": "2024-01-01T00:00:00Z",
                    "last_seen": "2024-01-01T12:00:00Z",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "tags": [],
                },
                {
                    "public_key": "xyz789xyz789xyz789xyz789xyz789xy",
                    "name": "Node Two",
                    "adv_type": "CHAT",
                    "first_seen": "2024-01-01T00:00:00Z",
                    "last_seen": "2024-01-01T11:00:00Z",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "tags": [],
                },
            ],
            "total": 2,
            "limit": 100,
            "offset": 0,
        },
    )

    # Mock node tags response
    client.set_response(
        "GET",
        "/api/v1/nodes/abc123def456abc123def456abc123de/tags",
        200,
        [
            {
                "key": "environment",
                "value": "production",
                "value_type": "string",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "key": "location",
                "value": "building-a",
                "value_type": "string",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        ],
    )

    # Mock create tag response
    client.set_response(
        "POST",
        "/api/v1/nodes/abc123def456abc123def456abc123de/tags",
        201,
        {
            "key": "new_tag",
            "value": "new_value",
            "value_type": "string",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
    )

    # Mock update tag response
    client.set_response(
        "PUT",
        "/api/v1/nodes/abc123def456abc123def456abc123de/tags/environment",
        200,
        {
            "key": "environment",
            "value": "staging",
            "value_type": "string",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
        },
    )

    # Mock move tag response
    client.set_response(
        "PUT",
        "/api/v1/nodes/abc123def456abc123def456abc123de/tags/environment/move",
        200,
        {
            "key": "environment",
            "value": "production",
            "value_type": "string",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
        },
    )

    # Mock delete tag response
    client.set_response(
        "DELETE",
        "/api/v1/nodes/abc123def456abc123def456abc123de/tags/environment",
        204,
        None,
    )

    return client


@pytest.fixture
def admin_app(mock_http_client_admin: MockHttpClient) -> Any:
    """Create a web app with admin enabled."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        admin_enabled=True,
    )

    app.state.http_client = mock_http_client_admin

    return app


@pytest.fixture
def admin_app_disabled(mock_http_client_admin: MockHttpClient) -> Any:
    """Create a web app with admin disabled."""
    app = create_app(
        api_url="http://localhost:8000",
        api_key="test-api-key",
        network_name="Test Network",
        network_city="Test City",
        network_country="Test Country",
        network_radio_config="Test Radio Config",
        network_contact_email="test@example.com",
        admin_enabled=False,
    )

    app.state.http_client = mock_http_client_admin

    return app


@pytest.fixture
def admin_client(admin_app: Any, mock_http_client_admin: MockHttpClient) -> TestClient:
    """Create a test client with admin enabled."""
    admin_app.state.http_client = mock_http_client_admin
    return TestClient(admin_app, raise_server_exceptions=True)


@pytest.fixture
def admin_client_disabled(
    admin_app_disabled: Any, mock_http_client_admin: MockHttpClient
) -> TestClient:
    """Create a test client with admin disabled."""
    admin_app_disabled.state.http_client = mock_http_client_admin
    return TestClient(admin_app_disabled, raise_server_exceptions=True)


class TestAdminHome:
    """Tests for admin home page."""

    def test_admin_home_enabled(self, admin_client):
        """Test admin home page when enabled."""
        response = admin_client.get("/a/")
        assert response.status_code == 200
        assert "Admin" in response.text
        assert "Node Tags" in response.text

    def test_admin_home_disabled(self, admin_client_disabled):
        """Test admin home page when disabled."""
        response = admin_client_disabled.get("/a/")
        assert response.status_code == 404


class TestAdminNodeTags:
    """Tests for admin node tags page."""

    def test_node_tags_page_no_selection(self, admin_client):
        """Test node tags page without selecting a node."""
        response = admin_client.get("/a/node-tags")
        assert response.status_code == 200
        assert "Node Tags" in response.text
        assert "Select a Node" in response.text
        # Should show node dropdown
        assert "Node One" in response.text
        assert "Node Two" in response.text

    def test_node_tags_page_with_selection(self, admin_client):
        """Test node tags page with a node selected."""
        response = admin_client.get(
            "/a/node-tags?public_key=abc123def456abc123def456abc123de"
        )
        assert response.status_code == 200
        assert "Node Tags" in response.text
        # Should show the selected node's tags
        assert "environment" in response.text
        assert "production" in response.text
        assert "location" in response.text
        assert "building-a" in response.text

    def test_node_tags_page_disabled(self, admin_client_disabled):
        """Test node tags page when admin is disabled."""
        response = admin_client_disabled.get("/a/node-tags")
        assert response.status_code == 404

    def test_node_tags_page_with_message(self, admin_client):
        """Test node tags page displays success message."""
        response = admin_client.get(
            "/a/node-tags?public_key=abc123def456abc123def456abc123de"
            "&message=Tag%20created%20successfully"
        )
        assert response.status_code == 200
        assert "Tag created successfully" in response.text

    def test_node_tags_page_with_error(self, admin_client):
        """Test node tags page displays error message."""
        response = admin_client.get(
            "/a/node-tags?public_key=abc123def456abc123def456abc123de"
            "&error=Tag%20already%20exists"
        )
        assert response.status_code == 200
        assert "Tag already exists" in response.text


class TestAdminCreateTag:
    """Tests for creating node tags."""

    def test_create_tag_success(self, admin_client):
        """Test creating a new tag."""
        response = admin_client.post(
            "/a/node-tags",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "new_tag",
                "value": "new_value",
                "value_type": "string",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "message=" in response.headers["location"]
        assert "created" in response.headers["location"]

    def test_create_tag_disabled(self, admin_client_disabled):
        """Test creating tag when admin is disabled."""
        response = admin_client_disabled.post(
            "/a/node-tags",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "new_tag",
                "value": "new_value",
                "value_type": "string",
            },
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestAdminUpdateTag:
    """Tests for updating node tags."""

    def test_update_tag_success(self, admin_client):
        """Test updating a tag."""
        response = admin_client.post(
            "/a/node-tags/update",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "environment",
                "value": "staging",
                "value_type": "string",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "message=" in response.headers["location"]
        assert "updated" in response.headers["location"]

    def test_update_tag_not_found(
        self, admin_app, mock_http_client_admin: MockHttpClient
    ):
        """Test updating a non-existent tag returns error."""
        # Set up 404 response for this specific tag
        mock_http_client_admin.set_response(
            "PUT",
            "/api/v1/nodes/abc123def456abc123def456abc123de/tags/nonexistent",
            404,
            {"detail": "Tag not found"},
        )
        admin_app.state.http_client = mock_http_client_admin
        client = TestClient(admin_app, raise_server_exceptions=True)

        response = client.post(
            "/a/node-tags/update",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "nonexistent",
                "value": "value",
                "value_type": "string",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "error=" in response.headers["location"]
        assert "not+found" in response.headers["location"].lower()

    def test_update_tag_disabled(self, admin_client_disabled):
        """Test updating tag when admin is disabled."""
        response = admin_client_disabled.post(
            "/a/node-tags/update",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "environment",
                "value": "staging",
                "value_type": "string",
            },
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestAdminMoveTag:
    """Tests for moving node tags."""

    def test_move_tag_success(self, admin_client):
        """Test moving a tag to another node."""
        response = admin_client.post(
            "/a/node-tags/move",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "environment",
                "new_public_key": "xyz789xyz789xyz789xyz789xyz789xy",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        # Should redirect to destination node
        assert "xyz789xyz789xyz789xyz789xyz789xy" in response.headers["location"]
        assert "message=" in response.headers["location"]
        assert "moved" in response.headers["location"]


class TestAdminDeleteTag:
    """Tests for deleting node tags."""

    def test_delete_tag_success(self, admin_client):
        """Test deleting a tag."""
        response = admin_client.post(
            "/a/node-tags/delete",
            data={
                "public_key": "abc123def456abc123def456abc123de",
                "key": "environment",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "message=" in response.headers["location"]
        assert "deleted" in response.headers["location"]
