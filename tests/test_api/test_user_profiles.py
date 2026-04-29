"""Tests for user profile API routes."""

TEST_USER_ID = "oidc-user-123"
OTHER_USER_ID = "oidc-user-456"
USER_HEADERS = {"X-User-Id": TEST_USER_ID, "X-User-Roles": "operator"}
USER_HEADERS_WITH_NAME = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "operator",
    "X-User-Name": "IdP Display Name",
}
OTHER_USER_HEADERS = {"X-User-Id": OTHER_USER_ID, "X-User-Roles": "operator"}
OPERATOR_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "operator",
}
MEMBER_ONLY_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "member",
}
NO_ROLES_HEADERS = {
    "X-User-Id": TEST_USER_ID,
    "X-User-Roles": "",
}


class TestGetProfile:
    """Tests for GET /user/profile/{user_id} endpoint."""

    def test_get_profile_auto_creates(self, client_no_auth):
        """Test getting a non-existent profile auto-creates it."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["name"] is None
        assert data["callsign"] is None
        assert "id" in data
        assert "created_at" in data
        assert data["nodes"] == []

    def test_get_profile_auto_creates_with_name(self, client_no_auth):
        """Test auto-created profile is populated with name from IdP."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            headers=USER_HEADERS_WITH_NAME,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["name"] == "IdP Display Name"
        assert data["callsign"] is None

    def test_get_profile_does_not_overwrite_existing_name(
        self, client_no_auth, sample_user_profile
    ):
        """Test that IdP name does not overwrite an existing profile name."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.user_id}",
            headers=USER_HEADERS_WITH_NAME,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_user_profile.name

    def test_get_existing_profile(self, client_no_auth, sample_user_profile):
        """Test getting an existing profile."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.user_id}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == sample_user_profile.user_id
        assert data["name"] == sample_user_profile.name
        assert data["callsign"] == sample_user_profile.callsign

    def test_get_profile_with_adopted_nodes(
        self, client_no_auth, sample_user_profile, sample_adopted_node
    ):
        """Test profile includes adopted nodes."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.user_id}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["public_key"] == "abc123def456abc123def456abc123de"
        assert "adopted_at" in data["nodes"][0]

    def test_get_profile_rejects_wrong_user(self, client_no_auth):
        """Test that a user cannot access another user's profile."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            headers=OTHER_USER_HEADERS,
        )
        assert response.status_code == 403
        assert "access denied" in response.json()["detail"].lower()

    def test_get_profile_rejects_missing_user_id(self, client_no_auth):
        """Test that missing X-User-Id header is rejected."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{TEST_USER_ID}",
        )
        assert response.status_code == 401

    def test_get_profile_requires_auth(self, client_with_auth):
        """Test getting profile requires auth when keys configured."""
        response = client_with_auth.get(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 401

        response = client_with_auth.get(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            headers={
                **USER_HEADERS,
                "Authorization": "Bearer test-read-key",
            },
        )
        assert response.status_code == 200


class TestUpdateProfile:
    """Tests for PUT /user/profile/{user_id} endpoint."""

    def test_update_profile_name(self, client_no_auth, sample_user_profile):
        """Test updating profile name."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{sample_user_profile.user_id}",
            json={"name": "New Name"},
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["callsign"] == sample_user_profile.callsign

    def test_update_profile_callsign(self, client_no_auth, sample_user_profile):
        """Test updating profile callsign."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{sample_user_profile.user_id}",
            json={"callsign": "G1NEW"},
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["callsign"] == "G1NEW"
        assert data["name"] == sample_user_profile.name

    def test_update_profile_auto_creates_with_name(self, client_no_auth):
        """Test updating a non-existent profile auto-creates it with IdP name."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            json={"callsign": "W1AUTO"},
            headers=USER_HEADERS_WITH_NAME,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["name"] == "IdP Display Name"
        assert data["callsign"] == "W1AUTO"

    def test_update_profile_rejects_wrong_user(self, client_no_auth):
        """Test that a user cannot update another user's profile."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            json={"name": "Hacked"},
            headers=OTHER_USER_HEADERS,
        )
        assert response.status_code == 403

    def test_update_profile_rejects_missing_user_id(self, client_no_auth):
        """Test that missing X-User-Id header is rejected."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{TEST_USER_ID}",
            json={"name": "No Auth"},
        )
        assert response.status_code == 401
