"""Tests for telemetry API routes."""


class TestListTelemetry:
    """Tests for GET /telemetry endpoint."""

    def test_list_telemetry_empty(self, client_no_auth):
        """Test listing telemetry when database is empty."""
        response = client_no_auth.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_telemetry_with_data(self, client_no_auth, sample_telemetry):
        """Test listing telemetry with data in database."""
        response = client_no_auth.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["node_public_key"] == sample_telemetry.node_public_key
        assert data["items"][0]["parsed_data"] == sample_telemetry.parsed_data

    def test_list_telemetry_filter_by_node(self, client_no_auth, sample_telemetry):
        """Test filtering telemetry by node public key."""
        response = client_no_auth.get(
            f"/api/v1/telemetry?node_public_key={sample_telemetry.node_public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = client_no_auth.get("/api/v1/telemetry?node_public_key=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0


class TestGetTelemetry:
    """Tests for GET /telemetry/{id} endpoint."""

    def test_get_telemetry_success(self, client_no_auth, sample_telemetry):
        """Test getting a specific telemetry record."""
        response = client_no_auth.get(f"/api/v1/telemetry/{sample_telemetry.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["node_public_key"] == sample_telemetry.node_public_key

    def test_get_telemetry_not_found(self, client_no_auth):
        """Test getting a non-existent telemetry record."""
        response = client_no_auth.get("/api/v1/telemetry/nonexistent-id")
        assert response.status_code == 404
