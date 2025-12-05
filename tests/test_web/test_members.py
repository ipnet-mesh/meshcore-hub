"""Tests for the members page route."""

from fastapi.testclient import TestClient


class TestMembersPage:
    """Tests for the members page."""

    def test_members_returns_200(self, client: TestClient) -> None:
        """Test that members page returns 200 status code."""
        response = client.get("/members")
        assert response.status_code == 200

    def test_members_returns_html(self, client: TestClient) -> None:
        """Test that members page returns HTML content."""
        response = client.get("/members")
        assert "text/html" in response.headers["content-type"]

    def test_members_contains_network_name(self, client: TestClient) -> None:
        """Test that members page contains the network name."""
        response = client.get("/members")
        assert "Test Network" in response.text

    def test_members_without_data_shows_empty(self, client: TestClient) -> None:
        """Test that members page with no API data shows no members."""
        response = client.get("/members")
        # Should still render successfully
        assert response.status_code == 200

    def test_members_with_api_data_shows_members(
        self, client_with_members: TestClient
    ) -> None:
        """Test that members page with API data shows member data."""
        response = client_with_members.get("/members")
        assert response.status_code == 200
        # Check for member data from mock API response
        assert "Alice" in response.text
        assert "Bob" in response.text
        assert "W1ABC" in response.text
        assert "W2XYZ" in response.text

    def test_members_with_nodes_shows_node_links(
        self, client_with_members: TestClient
    ) -> None:
        """Test that members page shows associated nodes with links."""
        response = client_with_members.get("/members")
        assert response.status_code == 200
        # Alice has a node associated - check for friendly name display
        assert "Alice Chat" in response.text
        # Check for partial public key underneath
        assert "abc123def456" in response.text
        # Check for link to node detail page (full public key)
        assert (
            "/nodes/abc123def456abc123def456abc123def456abc123def456abc123def456abc1"
            in response.text
        )
