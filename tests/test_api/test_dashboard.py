"""Tests for dashboard API routes."""


class TestDashboardStats:
    """Tests for GET /dashboard/stats endpoint."""

    def test_get_stats_empty(self, client_no_auth):
        """Test getting stats with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_nodes"] == 0
        assert data["active_nodes"] == 0
        assert data["total_messages"] == 0
        assert data["messages_today"] == 0
        assert data["total_advertisements"] == 0
        assert data["channel_message_counts"] == {}

    def test_get_stats_with_data(
        self, client_no_auth, sample_node, sample_message, sample_advertisement
    ):
        """Test getting stats with data in database."""
        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_nodes"] == 1
        assert data["active_nodes"] == 1  # Node was just created
        assert data["total_messages"] == 1
        assert data["total_advertisements"] == 1


class TestDashboardHtml:
    """Tests for GET /dashboard endpoint."""

    def test_dashboard_html_response(self, client_no_auth):
        """Test dashboard returns HTML."""
        response = client_no_auth.get("/api/v1/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<!DOCTYPE html>" in response.text
        assert "MeshCore Hub Dashboard" in response.text

    def test_dashboard_contains_stats(
        self, client_no_auth, sample_node, sample_message
    ):
        """Test dashboard HTML contains stat values."""
        response = client_no_auth.get("/api/v1/dashboard")
        assert response.status_code == 200
        # Check that stats are present
        assert "Total Nodes" in response.text
        assert "Active Nodes" in response.text
        assert "Total Messages" in response.text

    def test_dashboard_contains_recent_data(self, client_no_auth, sample_node):
        """Test dashboard HTML contains recent nodes."""
        response = client_no_auth.get("/api/v1/dashboard")
        assert response.status_code == 200
        assert "Recent Nodes" in response.text
        # The node name should appear in the table
        assert sample_node.name in response.text
