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


class TestListProfiles:
    """Tests for GET /user/profiles endpoint."""

    def test_list_profiles_returns_list(self, client_no_auth, sample_user_profile):
        """Test listing profiles returns a paginated list."""
        response = client_no_auth.get(
            "/api/v1/user/profiles",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_list_profiles_no_user_id(self, client_no_auth, sample_user_profile):
        """Test that list profiles does not expose user_id."""
        response = client_no_auth.get(
            "/api/v1/user/profiles",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "user_id" not in item

    def test_list_profiles_includes_roles(self, client_no_auth, sample_user_profile):
        """Test that list profiles includes roles."""
        response = client_no_auth.get(
            "/api/v1/user/profiles",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert "roles" in data["items"][0]

    def test_list_profiles_includes_node_count(
        self, client_no_auth, sample_user_profile, sample_adopted_node, sample_node
    ):
        """Test that list profiles includes node_count and adopted_nodes."""
        response = client_no_auth.get(
            "/api/v1/user/profiles",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        profile = next(p for p in data["items"] if p["id"] == sample_user_profile.id)
        assert profile["node_count"] == 1
        assert len(profile["adopted_nodes"]) == 1
        assert profile["adopted_nodes"][0]["name"] == sample_node.name


class TestGetMyProfile:
    """Tests for GET /user/profile/me endpoint."""

    def test_get_my_profile_returns_full_profile(
        self, client_no_auth, sample_user_profile
    ):
        """Test /me returns the full profile with user_id for authenticated user."""
        response = client_no_auth.get(
            "/api/v1/user/profile/me",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["name"] == sample_user_profile.name

    def test_get_my_profile_auto_creates(self, client_no_auth):
        """Test /me auto-creates profile for new user."""
        new_headers = {
            "X-User-Id": "brand-new-user",
            "X-User-Roles": "member",
            "X-User-Name": "New User",
        }
        response = client_no_auth.get(
            "/api/v1/user/profile/me",
            headers=new_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "brand-new-user"
        assert data["name"] == "New User"

    def test_get_my_profile_requires_user_id(self, client_no_auth):
        """Test /me returns 401 without X-User-Id header."""
        response = client_no_auth.get("/api/v1/user/profile/me")
        assert response.status_code == 401


class TestGetProfile:
    """Tests for GET /user/profile/{profile_id} endpoint."""

    def test_get_profile_auto_creates_for_owner(self, client_no_auth):
        """Test getting a non-existent profile auto-creates it for the owner."""
        response = client_no_auth.get(
            "/api/v1/user/profile/nonexistent-uuid",
            headers=USER_HEADERS,
        )
        assert response.status_code == 404

    def test_get_existing_profile_by_uuid(self, client_no_auth, sample_user_profile):
        """Test getting an existing profile by UUID."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_user_profile.name
        assert data["callsign"] == sample_user_profile.callsign

    def test_get_profile_public_no_auth(self, client_no_auth, sample_user_profile):
        """Test that profile can be viewed without authentication."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.id}",
        )
        assert response.status_code == 200
        data = response.json()
        assert "user_id" not in data
        assert data["name"] == sample_user_profile.name

    def test_get_profile_owner_sees_user_id(self, client_no_auth, sample_user_profile):
        """Test that owner sees user_id in their own profile."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("user_id") == sample_user_profile.user_id

    def test_get_profile_with_adopted_nodes(
        self, client_no_auth, sample_user_profile, sample_adopted_node
    ):
        """Test profile includes adopted nodes."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["public_key"] == "abc123def456abc123def456abc123de"
        assert "adopted_at" in data["nodes"][0]

    def test_get_profile_returns_roles(self, client_no_auth, sample_user_profile):
        """Test that profile includes roles."""
        response = client_no_auth.get(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        assert "operator" in data["roles"]

    def test_get_profile_not_found(self, client_no_auth):
        """Test 404 for non-existent profile UUID."""
        response = client_no_auth.get(
            "/api/v1/user/profile/00000000-0000-0000-0000-000000000000",
        )
        assert response.status_code == 404


class TestUpdateProfile:
    """Tests for PUT /user/profile/{profile_id} endpoint."""

    def test_update_profile_name(self, client_no_auth, sample_user_profile):
        """Test updating profile name."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{sample_user_profile.id}",
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
            f"/api/v1/user/profile/{sample_user_profile.id}",
            json={"callsign": "G1NEW"},
            headers=USER_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["callsign"] == "G1NEW"
        assert data["name"] == sample_user_profile.name

    def test_update_profile_rejects_wrong_user(
        self, client_no_auth, sample_user_profile
    ):
        """Test that a user cannot update another user's profile."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            json={"name": "Hacked"},
            headers=OTHER_USER_HEADERS,
        )
        assert response.status_code == 403

    def test_update_profile_rejects_missing_user_id(
        self, client_no_auth, sample_user_profile
    ):
        """Test that missing X-User-Id header is rejected."""
        response = client_no_auth.put(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            json={"name": "No Auth"},
        )
        assert response.status_code == 401

    def test_update_profile_not_found(self, client_no_auth):
        """Test 404 for updating non-existent profile."""
        response = client_no_auth.put(
            "/api/v1/user/profile/00000000-0000-0000-0000-000000000000",
            json={"name": "Ghost"},
            headers=USER_HEADERS,
        )
        assert response.status_code == 404
