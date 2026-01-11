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


class TestMoveNodeTag:
    """Tests for PUT /nodes/{public_key}/tags/{key}/move endpoint."""

    # 64-character public key for testing
    DEST_PUBLIC_KEY = "xyz789xyz789xyz789xyz789xyz789xyabc123abc123abc123abc123abc123ab"

    def test_move_node_tag_success(
        self, client_no_auth, api_db_session, sample_node, sample_node_tag
    ):
        """Test successfully moving a tag to another node."""
        from meshcore_hub.common.models import Node
        from datetime import datetime, timezone

        # Create a second node with 64-char public key
        second_node = Node(
            public_key=self.DEST_PUBLIC_KEY,
            name="Second Node",
            adv_type="CHAT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(second_node)
        api_db_session.commit()

        response = client_no_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}/move",
            json={"new_public_key": second_node.public_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == sample_node_tag.key
        assert data["value"] == sample_node_tag.value

        # Verify tag is no longer on original node
        response = client_no_auth.get(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}"
        )
        assert response.status_code == 404

        # Verify tag is now on new node
        response = client_no_auth.get(
            f"/api/v1/nodes/{second_node.public_key}/tags/{sample_node_tag.key}"
        )
        assert response.status_code == 200

    def test_move_node_tag_source_not_found(self, client_no_auth):
        """Test moving a tag from a non-existent node."""
        response = client_no_auth.put(
            "/api/v1/nodes/nonexistent123/tags/somekey/move",
            json={"new_public_key": self.DEST_PUBLIC_KEY},
        )
        assert response.status_code == 404
        assert "Source node not found" in response.json()["detail"]

    def test_move_node_tag_tag_not_found(self, client_no_auth, sample_node):
        """Test moving a non-existent tag."""
        response = client_no_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/nonexistent/move",
            json={"new_public_key": self.DEST_PUBLIC_KEY},
        )
        assert response.status_code == 404
        assert "Tag not found" in response.json()["detail"]

    def test_move_node_tag_dest_not_found(
        self, client_no_auth, sample_node, sample_node_tag
    ):
        """Test moving a tag to a non-existent destination node."""
        # 64-character nonexistent public key
        nonexistent_key = (
            "1111111111111111111111111111111122222222222222222222222222222222"
        )
        response = client_no_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}/move",
            json={"new_public_key": nonexistent_key},
        )
        assert response.status_code == 404
        assert "Destination node not found" in response.json()["detail"]

    def test_move_node_tag_conflict(
        self, client_no_auth, api_db_session, sample_node, sample_node_tag
    ):
        """Test moving a tag when destination already has that key."""
        from meshcore_hub.common.models import Node, NodeTag
        from datetime import datetime, timezone

        # Create second node with same tag key
        second_node = Node(
            public_key=self.DEST_PUBLIC_KEY,
            name="Second Node",
            adv_type="CHAT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(second_node)
        api_db_session.commit()

        # Add the same tag key to second node
        existing_tag = NodeTag(
            node_id=second_node.id,
            key=sample_node_tag.key,  # Same key
            value="different value",
        )
        api_db_session.add(existing_tag)
        api_db_session.commit()

        response = client_no_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}/move",
            json={"new_public_key": second_node.public_key},
        )
        assert response.status_code == 409
        assert "already exists on destination" in response.json()["detail"]

    def test_move_node_tag_requires_admin(
        self, client_with_auth, sample_node, sample_node_tag
    ):
        """Test that move operation requires admin auth."""
        # Without auth
        response = client_with_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}/move",
            json={"new_public_key": self.DEST_PUBLIC_KEY},
        )
        assert response.status_code == 401

        # With read key (not admin)
        response = client_with_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}/move",
            json={"new_public_key": self.DEST_PUBLIC_KEY},
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 403

    def test_move_node_tag_same_node(self, client_no_auth, api_db_session):
        """Test moving a tag to the same node returns 400."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node, NodeTag

        # Create node with 64-char public key
        full_key = "abc123def456abc123def456abc123deabc123def456abc123def456abc123de"
        node = Node(
            public_key=full_key,
            name="Test Node 64",
            adv_type="REPEATER",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(node)
        api_db_session.commit()

        # Create tag
        tag = NodeTag(
            node_id=node.id,
            key="test_tag",
            value="test_value",
        )
        api_db_session.add(tag)
        api_db_session.commit()

        response = client_no_auth.put(
            f"/api/v1/nodes/{full_key}/tags/test_tag/move",
            json={"new_public_key": full_key},
        )
        assert response.status_code == 400
        assert "same" in response.json()["detail"].lower()
