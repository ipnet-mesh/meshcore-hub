"""Tests for node API routes."""


class TestListNodes:
    """Tests for GET /nodes endpoint."""

    def test_list_nodes_empty(self, client_no_auth):
        """Test listing nodes when database is empty."""
        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_nodes_with_data(self, client_no_auth, sample_node):
        """Test listing nodes with data in database."""
        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["public_key"] == sample_node.public_key
        assert data["items"][0]["name"] == sample_node.name
        assert "tags" in data["items"][0]

    def test_list_nodes_includes_tags(
        self, client_no_auth, sample_node, sample_node_tag
    ):
        """Test listing nodes includes their tags."""
        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert len(data["items"][0]["tags"]) == 1
        assert data["items"][0]["tags"][0]["key"] == sample_node_tag.key
        assert data["items"][0]["tags"][0]["value"] == sample_node_tag.value

    def test_list_nodes_pagination(self, client_no_auth, sample_node):
        """Test node list pagination parameters."""
        response = client_no_auth.get("/api/v1/nodes?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_list_nodes_with_auth_required(self, client_with_auth):
        """Test listing nodes requires auth when configured."""
        # Without auth header
        response = client_with_auth.get("/api/v1/nodes")
        assert response.status_code == 401

        # With read key
        response = client_with_auth.get(
            "/api/v1/nodes",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200


class TestGetNode:
    """Tests for GET /nodes/{public_key} endpoint."""

    def test_get_node_success(self, client_no_auth, sample_node):
        """Test getting a specific node."""
        response = client_no_auth.get(f"/api/v1/nodes/{sample_node.public_key}")
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == sample_node.public_key
        assert data["name"] == sample_node.name
        assert "tags" in data
        assert data["tags"] == []

    def test_get_node_with_tags(self, client_no_auth, sample_node, sample_node_tag):
        """Test getting a node includes its tags."""
        response = client_no_auth.get(f"/api/v1/nodes/{sample_node.public_key}")
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == sample_node.public_key
        assert "tags" in data
        assert len(data["tags"]) == 1
        assert data["tags"][0]["key"] == sample_node_tag.key
        assert data["tags"][0]["value"] == sample_node_tag.value

    def test_get_node_not_found(self, client_no_auth):
        """Test getting a non-existent node."""
        response = client_no_auth.get("/api/v1/nodes/nonexistent123")
        assert response.status_code == 404


class TestNodeTags:
    """Tests for node tag endpoints."""

    def test_create_node_tag(self, client_no_auth, sample_node):
        """Test creating a node tag."""
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "location", "value": "building-a"},
        )
        assert response.status_code == 201  # Created
        data = response.json()
        assert data["key"] == "location"
        assert data["value"] == "building-a"

    def test_get_node_tag(self, client_no_auth, sample_node, sample_node_tag):
        """Test getting a specific node tag."""
        response = client_no_auth.get(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == sample_node_tag.key
        assert data["value"] == sample_node_tag.value

    def test_update_node_tag(self, client_no_auth, sample_node, sample_node_tag):
        """Test updating a node tag."""
        response = client_no_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}",
            json={"value": "staging"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == "staging"

    def test_delete_node_tag(self, client_no_auth, sample_node, sample_node_tag):
        """Test deleting a node tag."""
        response = client_no_auth.delete(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}"
        )
        assert response.status_code == 204  # No Content

        # Verify it's deleted
        response = client_no_auth.get(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}"
        )
        assert response.status_code == 404

    def test_tag_crud_requires_admin(self, client_with_auth, sample_node):
        """Test that tag CRUD operations require admin auth."""
        # Without auth
        response = client_with_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "test", "value": "test"},
        )
        assert response.status_code == 401

        # With read key (not admin)
        response = client_with_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "test", "value": "test"},
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 403

        # With admin key
        response = client_with_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "test", "value": "test"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert response.status_code == 201  # Created
