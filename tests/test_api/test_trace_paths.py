"""Tests for trace path API routes."""


class TestListTracePaths:
    """Tests for GET /trace-paths endpoint."""

    def test_list_trace_paths_empty(self, client_no_auth):
        """Test listing trace paths when database is empty."""
        response = client_no_auth.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_trace_paths_with_data(self, client_no_auth, sample_trace_path):
        """Test listing trace paths with data in database."""
        response = client_no_auth.get("/api/v1/trace-paths")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["path_hashes"] == sample_trace_path.path_hashes
        assert data["items"][0]["hop_count"] == sample_trace_path.hop_count


class TestGetTracePath:
    """Tests for GET /trace-paths/{id} endpoint."""

    def test_get_trace_path_success(self, client_no_auth, sample_trace_path):
        """Test getting a specific trace path."""
        response = client_no_auth.get(f"/api/v1/trace-paths/{sample_trace_path.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["path_hashes"] == sample_trace_path.path_hashes

    def test_get_trace_path_not_found(self, client_no_auth):
        """Test getting a non-existent trace path."""
        response = client_no_auth.get("/api/v1/trace-paths/nonexistent-id")
        assert response.status_code == 404
