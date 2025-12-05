"""Tests for advertisement API routes."""


class TestListAdvertisements:
    """Tests for GET /advertisements endpoint."""

    def test_list_advertisements_empty(self, client_no_auth):
        """Test listing advertisements when database is empty."""
        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_advertisements_with_data(self, client_no_auth, sample_advertisement):
        """Test listing advertisements with data in database."""
        response = client_no_auth.get("/api/v1/advertisements")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["public_key"] == sample_advertisement.public_key
        assert data["items"][0]["adv_type"] == sample_advertisement.adv_type

    def test_list_advertisements_filter_by_public_key(
        self, client_no_auth, sample_advertisement
    ):
        """Test filtering advertisements by public key."""
        response = client_no_auth.get(
            f"/api/v1/advertisements?public_key={sample_advertisement.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = client_no_auth.get("/api/v1/advertisements?public_key=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0


class TestGetAdvertisement:
    """Tests for GET /advertisements/{id} endpoint."""

    def test_get_advertisement_success(self, client_no_auth, sample_advertisement):
        """Test getting a specific advertisement."""
        response = client_no_auth.get(
            f"/api/v1/advertisements/{sample_advertisement.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == sample_advertisement.public_key

    def test_get_advertisement_not_found(self, client_no_auth):
        """Test getting a non-existent advertisement."""
        response = client_no_auth.get("/api/v1/advertisements/nonexistent-id")
        assert response.status_code == 404
