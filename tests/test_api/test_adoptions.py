"""Tests for node adoption API routes."""

from meshcore_hub.common.models import UserProfile, UserProfileNode

TEST_USER_ID = "oidc-user-123"
OTHER_USER_ID = "oidc-user-456"
OPERATOR_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "operator",
}
OPERATOR_HEADERS_WITH_NAME = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "operator",
    "X-User-Name": "Operator Name",
}
ADMIN_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "admin",
}
OTHER_OPERATOR_HEADERS = {
    "X-User-Id": OTHER_USER_ID,
    "X-User-Roles": "operator",
}
OTHER_ADMIN_HEADERS = {
    "X-User-Id": OTHER_USER_ID,
    "X-User-Roles": "admin",
}
MEMBER_ONLY_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "member",
}
NO_ROLES_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "",
}


class TestAdoptNode:
    """Tests for POST /v1/adoptions endpoint."""

    def test_adopt_node_success(self, client_no_auth, sample_node):
        """Test adopting a node."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["public_key"] == sample_node.public_key
        assert data["name"] == sample_node.name
        assert "adopted_at" in data

    def test_adopt_node_auto_creates_profile(self, client_no_auth, sample_node):
        """Test adopting a node auto-creates the user profile."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 201

    def test_adopt_node_auto_creates_profile_with_name(
        self, client_no_auth, sample_node, api_db_session
    ):
        """Test adopting a node auto-creates profile with IdP name."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=OPERATOR_HEADERS_WITH_NAME,
        )
        assert response.status_code == 201

        from meshcore_hub.common.models import UserProfile as UP

        profile = (
            api_db_session.query(UP).filter(UP.user_id == TEST_USER_ID).one_or_none()
        )
        assert profile is not None
        assert profile.name == "Operator Name"

    def test_adopt_node_by_admin(self, client_no_auth, sample_node):
        """Test an admin can adopt a node."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201

    def test_adopt_node_duplicate(self, client_no_auth, sample_adopted_node):
        """Test adopting an already-adopted node by the same user fails."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": "abc123def456abc123def456abc123de"},
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 409
        assert "already adopted" in response.json()["detail"].lower()

    def test_adopt_node_already_adopted_by_other(
        self, client_no_auth, api_db_session, sample_node
    ):
        """Test adopting a node adopted by another user fails."""
        other_profile = UserProfile(user_id=OTHER_USER_ID, name="Other")
        api_db_session.add(other_profile)
        api_db_session.commit()
        api_db_session.refresh(other_profile)

        assoc = UserProfileNode(
            user_profile_id=other_profile.id,
            node_id=sample_node.id,
        )
        api_db_session.add(assoc)
        api_db_session.commit()

        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 409
        assert "another user" in response.json()["detail"].lower()

    def test_adopt_node_not_found(self, client_no_auth):
        """Test adopting a non-existent node fails."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": "a" * 64},
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 404

    def test_adopt_node_requires_operator_or_admin_role(
        self, client_no_auth, sample_node
    ):
        """Test adopting requires operator or admin role."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=MEMBER_ONLY_HEADERS,
        )
        assert response.status_code == 403

    def test_adopt_node_requires_role_header(self, client_no_auth, sample_node):
        """Test adopting requires role in X-User-Roles."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers=NO_ROLES_HEADERS,
        )
        assert response.status_code == 403

    def test_adopt_node_rejects_missing_user_id(self, client_no_auth, sample_node):
        """Test adopting without X-User-Id header is rejected."""
        response = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
        )
        assert response.status_code == 401


class TestReleaseNode:
    """Tests for DELETE /v1/adoptions/{public_key} endpoint."""

    def test_release_own_node_success(
        self, client_no_auth, sample_node, sample_adopted_node
    ):
        """Test operator releasing their own adopted node."""
        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 204

    def test_release_node_not_adopted(self, client_no_auth, sample_node):
        """Test releasing a node that is not adopted."""
        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 404

    def test_release_node_not_found(self, client_no_auth):
        """Test releasing a non-existent node fails."""
        response = client_no_auth.delete(
            f"/api/v1/adoptions/{'z' * 64}",
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 404

    def test_release_node_requires_operator_or_admin(
        self, client_no_auth, sample_node, sample_adopted_node
    ):
        """Test releasing requires operator or admin role."""
        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers=MEMBER_ONLY_HEADERS,
        )
        assert response.status_code == 403

    def test_operator_cannot_release_others_node(
        self, client_no_auth, api_db_session, sample_node, sample_user_profile
    ):
        """Test operator cannot release a node adopted by another user."""
        other_profile = UserProfile(user_id=OTHER_USER_ID, name="Other")
        api_db_session.add(other_profile)
        api_db_session.commit()
        api_db_session.refresh(other_profile)

        assoc = UserProfileNode(
            user_profile_id=other_profile.id,
            node_id=sample_node.id,
        )
        api_db_session.add(assoc)
        api_db_session.commit()

        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers=OPERATOR_HEADERS,
        )
        assert response.status_code == 403

    def test_admin_can_release_others_node(
        self, client_no_auth, api_db_session, sample_node
    ):
        """Test admin can release a node adopted by another user."""
        other_profile = UserProfile(user_id=OTHER_USER_ID, name="Other")
        api_db_session.add(other_profile)
        api_db_session.commit()
        api_db_session.refresh(other_profile)

        assoc = UserProfileNode(
            user_profile_id=other_profile.id,
            node_id=sample_node.id,
        )
        api_db_session.add(assoc)
        api_db_session.commit()

        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 204

    def test_admin_can_release_own_node(
        self, client_no_auth, sample_node, api_db_session
    ):
        """Test admin can release their own adopted node."""
        profile = UserProfile(user_id=TEST_USER_ID, name="Admin User")
        api_db_session.add(profile)
        api_db_session.commit()
        api_db_session.refresh(profile)

        assoc = UserProfileNode(
            user_profile_id=profile.id,
            node_id=sample_node.id,
        )
        api_db_session.add(assoc)
        api_db_session.commit()

        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 204

    def test_release_node_rejects_missing_user_id(
        self, client_no_auth, sample_node, sample_adopted_node
    ):
        """Test releasing without X-User-Id header is rejected."""
        response = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
        )
        assert response.status_code == 401
