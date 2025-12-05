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


class TestDashboardActivity:
    """Tests for GET /dashboard/activity endpoint."""

    def test_get_activity_empty(self, client_no_auth):
        """Test getting activity with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/activity")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        # All counts should be 0
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_activity_custom_days(self, client_no_auth):
        """Test getting activity with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/activity?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_activity_max_days(self, client_no_auth):
        """Test that activity is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/activity?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_activity_with_data(self, client_no_auth, sample_advertisement):
        """Test getting activity with advertisement in database."""
        response = client_no_auth.get("/api/v1/dashboard/activity")
        assert response.status_code == 200
        data = response.json()
        # At least one day should have a count > 0
        total_count = sum(point["count"] for point in data["data"])
        assert total_count >= 1


class TestMessageActivity:
    """Tests for GET /dashboard/message-activity endpoint."""

    def test_get_message_activity_empty(self, client_no_auth):
        """Test getting message activity with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        # All counts should be 0
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_message_activity_custom_days(self, client_no_auth):
        """Test getting message activity with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_message_activity_max_days(self, client_no_auth):
        """Test that message activity is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_message_activity_with_data(self, client_no_auth, sample_message):
        """Test getting message activity with message in database."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity")
        assert response.status_code == 200
        data = response.json()
        # At least one day should have a count > 0
        total_count = sum(point["count"] for point in data["data"])
        assert total_count >= 1


class TestNodeCountHistory:
    """Tests for GET /dashboard/node-count endpoint."""

    def test_get_node_count_empty(self, client_no_auth):
        """Test getting node count with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/node-count")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        # All counts should be 0
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_node_count_custom_days(self, client_no_auth):
        """Test getting node count with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/node-count?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_node_count_max_days(self, client_no_auth):
        """Test that node count is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/node-count?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_node_count_with_data(self, client_no_auth, sample_node):
        """Test getting node count with node in database."""
        response = client_no_auth.get("/api/v1/dashboard/node-count")
        assert response.status_code == 200
        data = response.json()
        # At least one day should have a count > 0 (cumulative)
        # The last day should have count >= 1
        assert data["data"][-1]["count"] >= 1
