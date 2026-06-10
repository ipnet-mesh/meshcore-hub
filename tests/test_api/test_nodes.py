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
        assert data["items"][0]["adopted_by"] is None

    def test_list_nodes_with_adopted_node(
        self, client_no_auth, sample_node, sample_user_profile, sample_adopted_node
    ):
        """Test listing nodes includes adopted_by info."""
        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        adopted_by = data["items"][0]["adopted_by"]
        assert adopted_by is not None
        assert adopted_by["user_id"] == "oidc-user-123"
        assert adopted_by["name"] == "Test User"
        assert adopted_by["callsign"] == "W1TEST"

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


class TestListNodesFilters:
    """Tests for node list query filters."""

    def test_filter_by_search_public_key(self, client_no_auth, sample_node):
        """Test filtering nodes by public key search."""
        # Partial public key match
        response = client_no_auth.get("/api/v1/nodes?search=abc123")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # No match
        response = client_no_auth.get("/api/v1/nodes?search=zzz999")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_search_node_name(self, client_no_auth, sample_node):
        """Test filtering nodes by node name search."""
        response = client_no_auth.get("/api/v1/nodes?search=Test%20Node")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_filter_by_search_name_tag(self, client_no_auth, sample_node_with_name_tag):
        """Test filtering nodes by name tag search."""
        response = client_no_auth.get("/api/v1/nodes?search=Friendly%20Search")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_filter_by_adv_type(self, client_no_auth, sample_node):
        """Test filtering nodes by advertisement type."""
        # Match REPEATER
        response = client_no_auth.get("/api/v1/nodes?adv_type=REPEATER")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # No match
        response = client_no_auth.get("/api/v1/nodes?adv_type=CLIENT")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_adv_type_matches_legacy_labels(
        self, client_no_auth, api_db_session
    ):
        """Canonical adv_type filters match legacy LetsMesh adv_type values only."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node

        repeater_node = Node(
            public_key="ab" * 32,
            adv_type="PyMC-Repeater",
            first_seen=datetime.now(timezone.utc),
        )
        companion_node = Node(
            public_key="cd" * 32,
            adv_type="offline companion",
            first_seen=datetime.now(timezone.utc),
        )
        room_node = Node(
            public_key="ef" * 32,
            adv_type="room server",
            first_seen=datetime.now(timezone.utc),
        )
        name_only_room_node = Node(
            public_key="12" * 32,
            name="WAL-SE Room Server",
            adv_type="unknown",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(repeater_node)
        api_db_session.add(companion_node)
        api_db_session.add(room_node)
        api_db_session.add(name_only_room_node)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?adv_type=repeater")
        assert response.status_code == 200
        repeater_keys = {item["public_key"] for item in response.json()["items"]}
        assert repeater_node.public_key in repeater_keys

        response = client_no_auth.get("/api/v1/nodes?adv_type=companion")
        assert response.status_code == 200
        companion_keys = {item["public_key"] for item in response.json()["items"]}
        assert companion_node.public_key in companion_keys

        response = client_no_auth.get("/api/v1/nodes?adv_type=room")
        assert response.status_code == 200
        room_keys = {item["public_key"] for item in response.json()["items"]}
        assert room_node.public_key in room_keys
        assert name_only_room_node.public_key not in room_keys

    def test_filter_by_observer_true(
        self, client_no_auth, api_db_session, receiver_node
    ):
        """Test filtering nodes by the precomputed is_observer flag."""
        # The collector sets this flag when a node observes an event.
        receiver_node.is_observer = True
        api_db_session.add(receiver_node)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?observer=true")
        assert response.status_code == 200
        data = response.json()
        observer_keys = {item["public_key"] for item in data["items"]}
        assert receiver_node.public_key in observer_keys

        response = client_no_auth.get("/api/v1/nodes?observer=false")
        assert response.status_code == 200
        data = response.json()
        non_observer_keys = {item["public_key"] for item in data["items"]}
        assert receiver_node.public_key not in non_observer_keys


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
        assert data["adopted_by"] is None

    def test_get_node_with_adoption(
        self, client_no_auth, sample_node, sample_user_profile, sample_adopted_node
    ):
        """Test getting a node shows adopted_by info."""
        response = client_no_auth.get(f"/api/v1/nodes/{sample_node.public_key}")
        assert response.status_code == 200
        data = response.json()
        assert data["adopted_by"] is not None
        assert data["adopted_by"]["user_id"] == "oidc-user-123"
        assert data["adopted_by"]["name"] == "Test User"
        assert data["adopted_by"]["callsign"] == "W1TEST"

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

    def test_get_node_by_prefix(self, client_no_auth, sample_node):
        """Test getting a node by public key prefix."""
        prefix = sample_node.public_key[:8]  # First 8 chars
        response = client_no_auth.get(f"/api/v1/nodes/prefix/{prefix}")
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == sample_node.public_key

    def test_get_node_by_single_char_prefix(self, client_no_auth, sample_node):
        """Test getting a node by single character prefix."""
        prefix = sample_node.public_key[0]
        response = client_no_auth.get(f"/api/v1/nodes/prefix/{prefix}")
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == sample_node.public_key

    def test_get_node_prefix_returns_first_alphabetically(
        self, client_no_auth, api_db_session
    ):
        """Test that prefix match returns first node alphabetically."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node

        # Create two nodes with same prefix but different suffixes
        # abc... should come before abd...
        node_a = Node(
            public_key="abc0000000000000000000000000000000000000000000000000000000000000",
            name="Node A",
            adv_type="REPEATER",
            first_seen=datetime.now(timezone.utc),
        )
        node_b = Node(
            public_key="abc1111111111111111111111111111111111111111111111111111111111111",
            name="Node B",
            adv_type="REPEATER",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(node_a)
        api_db_session.add(node_b)
        api_db_session.commit()

        # Request with prefix should return first alphabetically
        response = client_no_auth.get("/api/v1/nodes/prefix/abc")
        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == node_a.public_key


class TestNodeTags:
    """Tests for node tag endpoints."""

    def test_tag_crud_requires_operator_or_admin(self, client_no_auth, sample_node):
        """Test that tag CRUD operations require OIDC auth (operator or admin)."""
        # No OIDC headers at all → 401
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "test", "value": "test"},
        )
        assert response.status_code == 401

        # Member role → 403
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "test", "value": "test"},
            headers={
                "X-User-Id": "member-789",
                "X-User-Roles": "member",
            },
        )
        assert response.status_code == 403

    def test_create_node_tag(self, client_no_auth, sample_node):
        """Test creating a node tag with admin OIDC headers."""
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "location", "value": "building-a"},
            headers={
                "X-User-Id": "admin-456",
                "X-User-Roles": "admin",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["key"] == "location"
        assert data["value"] == "building-a"

    def test_update_node_tag(self, client_no_auth, sample_node, sample_node_tag):
        """Test updating a node tag with admin OIDC headers."""
        response = client_no_auth.put(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}",
            json={"value": "staging"},
            headers={
                "X-User-Id": "admin-456",
                "X-User-Roles": "admin",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == "staging"

    def test_delete_node_tag(self, client_no_auth, sample_node, sample_node_tag):
        """Test deleting a node tag."""
        response = client_no_auth.delete(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}",
            headers={
                "X-User-Id": "admin-456",
                "X-User-Roles": "admin",
            },
        )
        assert response.status_code == 204

        # Verify deletion via list endpoint
        response = client_no_auth.get(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
        )
        assert response.status_code == 200
        tags = response.json()
        assert all(t["key"] != sample_node_tag.key for t in tags)

    def test_operator_can_edit_adopted_node_tags(
        self,
        client_no_auth,
        sample_node,
        sample_operator_profile,
        sample_operator_adoption,
    ):
        """Test operator can CRUD tags on their adopted node."""
        pk = sample_node.public_key
        headers = {
            "X-User-Id": "operator-123",
            "X-User-Roles": "operator",
        }

        # POST
        response = client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "owner-tag", "value": "mine"},
            headers=headers,
        )
        assert response.status_code == 201

        # PUT
        response = client_no_auth.put(
            f"/api/v1/nodes/{pk}/tags/owner-tag",
            json={"value": "updated"},
            headers=headers,
        )
        assert response.status_code == 200

        # DELETE
        response = client_no_auth.delete(
            f"/api/v1/nodes/{pk}/tags/owner-tag",
            headers=headers,
        )
        assert response.status_code == 204

    def test_operator_cannot_edit_non_adopted_node_tags(
        self, client_no_auth, sample_node
    ):
        """Test operator without adoption gets 403 on tag writes."""
        pk = sample_node.public_key
        headers = {
            "X-User-Id": "operator-123",
            "X-User-Roles": "operator",
        }

        # POST
        response = client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "test", "value": "test"},
            headers=headers,
        )
        assert response.status_code == 403
        assert "adopted" in response.json()["detail"].lower()

        # Create a tag first via admin so PUT/DELETE have something to target
        client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "existing", "value": "val"},
            headers={"X-User-Id": "admin-456", "X-User-Roles": "admin"},
        )

        # PUT
        response = client_no_auth.put(
            f"/api/v1/nodes/{pk}/tags/existing",
            json={"value": "new"},
            headers=headers,
        )
        assert response.status_code == 403

        # DELETE
        response = client_no_auth.delete(
            f"/api/v1/nodes/{pk}/tags/existing",
            headers=headers,
        )
        assert response.status_code == 403

    def test_admin_can_edit_any_node_tags(self, client_no_auth, sample_node):
        """Test admin can edit tags on any node without adoption."""
        pk = sample_node.public_key
        headers = {
            "X-User-Id": "admin-456",
            "X-User-Roles": "admin",
        }

        response = client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "admin-tag", "value": "admin-val"},
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["key"] == "admin-tag"
        assert data["value"] == "admin-val"


class TestNodeSort:
    """Tests for node list sort parameters."""

    def test_sort_by_last_seen_default(self, client_no_auth, api_db_session):
        """Default sort (no params) returns nodes by last_seen descending."""
        from datetime import datetime, timezone, timedelta

        from meshcore_hub.common.models import Node

        now = datetime.now(timezone.utc)
        node_a = Node(
            public_key="aa" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=now,
            last_seen=now,
        )
        node_b = Node(
            public_key="bb" * 32,
            name="Bravo",
            adv_type="CLIENT",
            first_seen=now,
            last_seen=now + timedelta(hours=1),
        )
        api_db_session.add_all([node_a, node_b])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        assert items[0]["name"] == "Bravo"
        assert items[1]["name"] == "Alpha"

    def test_sort_by_name_asc(self, client_no_auth, api_db_session):
        """Explicit sort=name&order=asc."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node

        node_b = Node(
            public_key="bb" * 32,
            name="Bravo",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        node_a = Node(
            public_key="aa" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([node_b, node_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=name&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Alpha"

    def test_sort_by_name_desc(self, client_no_auth, api_db_session):
        """sort=name&order=desc returns Z-to-A."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node

        node_a = Node(
            public_key="aa" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        node_b = Node(
            public_key="bb" * 32,
            name="Bravo",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([node_a, node_b])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=name&order=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Bravo"
        assert items[1]["name"] == "Alpha"

    def test_sort_by_public_key(self, client_no_auth, api_db_session):
        """sort=public_key orders by public_key."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node

        node_b = Node(
            public_key="bb" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        node_a = Node(
            public_key="aa" * 32,
            name="Bravo",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([node_b, node_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=public_key&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["public_key"] == "aa" * 32

    def test_sort_by_last_seen(self, client_no_auth, api_db_session):
        """sort=last_seen&order=asc returns oldest first."""
        from datetime import datetime, timedelta, timezone

        from meshcore_hub.common.models import Node

        now = datetime.now(timezone.utc)
        node_old = Node(
            public_key="aa" * 32,
            name="Old",
            adv_type="CLIENT",
            first_seen=now - timedelta(days=2),
            last_seen=now - timedelta(days=1),
        )
        node_new = Node(
            public_key="bb" * 32,
            name="New",
            adv_type="CLIENT",
            first_seen=now,
            last_seen=now,
        )
        api_db_session.add_all([node_old, node_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=last_seen&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Old"
        assert items[1]["name"] == "New"

    def test_sort_name_tag_priority(self, client_no_auth, api_db_session):
        """Name tag takes priority over node.name in sort."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node, NodeTag

        node_b = Node(
            public_key="bb" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        node_a = Node(
            public_key="aa" * 32,
            name="Bravo",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([node_b, node_a])
        api_db_session.commit()

        tag_b = NodeTag(node_id=node_b.id, key="name", value="Zebra")
        tag_a = NodeTag(node_id=node_a.id, key="name", value="Aardvark")
        api_db_session.add_all([tag_b, tag_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=name&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Bravo"
        assert items[1]["name"] == "Alpha"

    def test_sort_invalid_ignored(self, client_no_auth, api_db_session):
        """Invalid sort value falls back to default (last_seen desc)."""
        from datetime import datetime, timezone, timedelta

        from meshcore_hub.common.models import Node

        now = datetime.now(timezone.utc)
        node_a = Node(
            public_key="aa" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=now,
            last_seen=now,
        )
        node_b = Node(
            public_key="bb" * 32,
            name="Bravo",
            adv_type="CLIENT",
            first_seen=now,
            last_seen=now + timedelta(hours=1),
        )
        api_db_session.add_all([node_a, node_b])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=invalid_column")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Bravo"
        assert items[1]["name"] == "Alpha"

    def test_sort_nodes_with_null_name(self, client_no_auth, api_db_session):
        """Nodes with name=NULL sort by public_key via COALESCE fallback."""
        from datetime import datetime, timezone

        from meshcore_hub.common.models import Node

        node_no_name = Node(
            public_key="bb" * 32,
            name=None,
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        node_named = Node(
            public_key="aa" * 32,
            name="Alpha",
            adv_type="CLIENT",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([node_no_name, node_named])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/nodes?sort=name&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["name"] == "Alpha"
        assert items[1]["name"] is None


class TestTagValidation:
    """Unit tests for validate_and_coerce_tag_value."""

    def test_string_passes_through(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("hello", "string") == "hello"

    def test_none_returns_none(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value(None, "string") is None

    def test_empty_string_passes(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("", "number") == ""

    def test_number_valid_integer(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("42", "number") == "42"

    def test_number_valid_float(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("3.14", "number") == "3.14"

    def test_number_valid_negative(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("-7", "number") == "-7"

    def test_number_invalid(self):
        import pytest
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        with pytest.raises(ValueError):
            validate_and_coerce_tag_value("abc", "number")

    def test_boolean_true_variants(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("true", "boolean") == "true"
        assert validate_and_coerce_tag_value("True", "boolean") == "true"
        assert validate_and_coerce_tag_value("yes", "boolean") == "true"
        assert validate_and_coerce_tag_value("1", "boolean") == "true"

    def test_boolean_false_variants(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value("false", "boolean") == "false"
        assert validate_and_coerce_tag_value("False", "boolean") == "false"
        assert validate_and_coerce_tag_value("no", "boolean") == "false"
        assert validate_and_coerce_tag_value("0", "boolean") == "false"

    def test_boolean_invalid(self):
        import pytest
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        with pytest.raises(ValueError):
            validate_and_coerce_tag_value("maybe", "boolean")

    def test_boolean_whitespace(self):
        from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value

        assert validate_and_coerce_tag_value(" true ", "boolean") == "true"


class TestTagValidationAPI:
    """Integration tests for tag value validation through the API."""

    def _admin_headers(self):
        return {"X-User-Id": "admin-456", "X-User-Roles": "admin"}

    def test_create_tag_invalid_number(self, client_no_auth, sample_node):
        """POST with value 'abc' type 'number' → 422."""
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "bad-num", "value": "abc", "value_type": "number"},
            headers=self._admin_headers(),
        )
        assert response.status_code == 422

    def test_create_tag_invalid_boolean(self, client_no_auth, sample_node):
        """POST with value 'maybe' type 'boolean' → 422."""
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "bad-bool", "value": "maybe", "value_type": "boolean"},
            headers=self._admin_headers(),
        )
        assert response.status_code == 422

    def test_create_tag_valid_number(self, client_no_auth, sample_node):
        """POST with value '42' type 'number' → 201."""
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "good-num", "value": "42", "value_type": "number"},
            headers=self._admin_headers(),
        )
        assert response.status_code == 201
        assert response.json()["value"] == "42"

    def test_create_tag_coerces_boolean(self, client_no_auth, sample_node):
        """POST with value 'yes' type 'boolean' → 201, value 'true'."""
        response = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "coerced", "value": "yes", "value_type": "boolean"},
            headers=self._admin_headers(),
        )
        assert response.status_code == 201
        assert response.json()["value"] == "true"

    def test_update_tag_validates_new_value_against_existing_type(
        self, client_no_auth, sample_node
    ):
        """Create number tag, then PUT invalid value → 422."""
        pk = sample_node.public_key
        h = self._admin_headers()

        client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "num-tag", "value": "10", "value_type": "number"},
            headers=h,
        )

        response = client_no_auth.put(
            f"/api/v1/nodes/{pk}/tags/num-tag",
            json={"value": "not-a-number"},
            headers=h,
        )
        assert response.status_code == 422

    def test_update_tag_validates_existing_value_against_new_type(
        self, client_no_auth, sample_node
    ):
        """Create tag with 'hello', then PUT type='number' → 422."""
        pk = sample_node.public_key
        h = self._admin_headers()

        client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "str-tag", "value": "hello", "value_type": "string"},
            headers=h,
        )

        response = client_no_auth.put(
            f"/api/v1/nodes/{pk}/tags/str-tag",
            json={"value_type": "number"},
            headers=h,
        )
        assert response.status_code == 422

    def test_update_tag_validates_new_value_against_new_type_with_coercion(
        self, client_no_auth, sample_node
    ):
        """PUT with value 'yes' and type 'boolean' → 200, value 'true'."""
        pk = sample_node.public_key
        h = self._admin_headers()

        client_no_auth.post(
            f"/api/v1/nodes/{pk}/tags",
            json={"key": "mix-tag", "value": "hello", "value_type": "string"},
            headers=h,
        )

        response = client_no_auth.put(
            f"/api/v1/nodes/{pk}/tags/mix-tag",
            json={"value": "yes", "value_type": "boolean"},
            headers=h,
        )
        assert response.status_code == 200
        assert response.json()["value"] == "true"
