"""Tests for channel API routes."""

from meshcore_hub.common.models import Channel

VALID_KEY_32 = "A" * 32
VALID_KEY_64 = "B" * 64
ALT_KEY_32 = "C" * 32


class TestListChannels:
    """Tests for GET /channels endpoint."""

    def test_list_channels_empty(self, client_no_auth):
        """Test listing channels when database is empty."""
        response = client_no_auth.get("/api/v1/channels")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_channels_with_data(self, client_no_auth, sample_channel):
        """Test listing channels with data in database."""
        response = client_no_auth.get("/api/v1/channels")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["name"] == "TestChannel"
        assert data["items"][0]["key_hex"] is not None
        assert data["items"][0]["masked_key"] is not None

    def test_list_channels_anonymous_only_community(
        self, client_no_auth, api_db_session
    ):
        """Anonymous users only see community channels."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        mem_key = "11223344556677889900AABBCCDDEEFF"

        for name, key, vis in [
            ("Community", pub_key, "community"),
            ("Secret", mem_key, "member"),
        ]:
            ch = Channel(
                name=name,
                key_hex=key,
                channel_hash=Channel.compute_channel_hash(key),
                visibility=vis,
                enabled=True,
            )
            api_db_session.add(ch)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/channels")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Community"

    def test_list_channels_admin_sees_all(self, client_no_auth, api_db_session):
        """Admin role header allows seeing all channels."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        mem_key = "11223344556677889900AABBCCDDEEFF"
        adm_key = "FFEEDDCCBBAA99887766554433221100"

        for name, key, vis in [
            ("Community", pub_key, "community"),
            ("Member", mem_key, "member"),
            ("Admin", adm_key, "admin"),
        ]:
            ch = Channel(
                name=name,
                key_hex=key,
                channel_hash=Channel.compute_channel_hash(key),
                visibility=vis,
                enabled=True,
            )
            api_db_session.add(ch)
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/channels",
            headers={"X-User-Roles": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_list_channels_member_sees_community_and_member(
        self, client_no_auth, api_db_session
    ):
        """Member role sees community and member channels, not admin."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        mem_key = "11223344556677889900AABBCCDDEEFF"
        adm_key = "FFEEDDCCBBAA99887766554433221100"

        for name, key, vis in [
            ("Community", pub_key, "community"),
            ("MemberCh", mem_key, "member"),
            ("AdminCh", adm_key, "admin"),
        ]:
            ch = Channel(
                name=name,
                key_hex=key,
                channel_hash=Channel.compute_channel_hash(key),
                visibility=vis,
                enabled=True,
            )
            api_db_session.add(ch)
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/channels",
            headers={"X-User-Roles": "member"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        names = {item["name"] for item in data["items"]}
        assert names == {"Community", "MemberCh"}

    def test_list_channels_operator_sees_community_member_operator(
        self, client_no_auth, api_db_session
    ):
        """Operator role sees community, member, and operator channels."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        mem_key = "11223344556677889900AABBCCDDEEFF"
        op_key = "0A0B0C0D0E0F10111213141516171819"
        adm_key = "FFEEDDCCBBAA99887766554433221100"

        for name, key, vis in [
            ("Community", pub_key, "community"),
            ("MemberCh", mem_key, "member"),
            ("OperatorCh", op_key, "operator"),
            ("AdminCh", adm_key, "admin"),
        ]:
            ch = Channel(
                name=name,
                key_hex=key,
                channel_hash=Channel.compute_channel_hash(key),
                visibility=vis,
                enabled=True,
            )
            api_db_session.add(ch)
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/channels",
            headers={"X-User-Roles": "operator"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        names = {item["name"] for item in data["items"]}
        assert names == {"Community", "MemberCh", "OperatorCh"}


class TestCreateChannel:
    """Tests for POST /channels endpoint."""

    def test_create_channel_success(self, client_no_auth):
        """Test creating a channel successfully."""
        response = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "NewChannel",
                "key_hex": VALID_KEY_32,
                "visibility": "community",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "NewChannel"
        assert data["visibility"] == "community"
        assert data["enabled"] is True
        assert data["key_hex"] == VALID_KEY_32
        assert data["masked_key"] == f"{VALID_KEY_32[:4]}...{VALID_KEY_32[-4:]}"
        assert data["channel_hash"] == Channel.compute_channel_hash(VALID_KEY_32)
        assert data["id"] is not None
        assert data["created_at"] is not None

    def test_create_channel_duplicate_name(self, client_no_auth, sample_channel):
        """Test creating channel with duplicate name returns 409."""
        response = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "TestChannel",
                "key_hex": ALT_KEY_32,
            },
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_channel_duplicate_key(self, client_no_auth, sample_channel):
        """Test creating channel with duplicate key returns 409."""
        response = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "DifferentName",
                "key_hex": sample_channel.key_hex,
            },
        )
        assert response.status_code == 409
        assert "Key already in use" in response.json()["detail"]

    def test_create_channel_invalid_key(self, client_no_auth):
        """Test creating channel with invalid key returns 422."""
        response = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "BadKey",
                "key_hex": "NOT-HEX",
            },
        )
        assert response.status_code == 422

    def test_create_channel_aes256_key(self, client_no_auth):
        """Test creating channel with AES-256 key (64 hex chars)."""
        response = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "AES256",
                "key_hex": VALID_KEY_64,
            },
        )
        assert response.status_code == 201
        assert response.json()["key_hex"] == VALID_KEY_64

    def test_create_channel_with_auth(self, client_with_auth):
        """Test creating channel requires admin key."""
        response = client_with_auth.post(
            "/api/v1/channels",
            json={
                "name": "AuthChannel",
                "key_hex": VALID_KEY_32,
            },
        )
        assert response.status_code == 401

        response = client_with_auth.post(
            "/api/v1/channels",
            headers={"Authorization": "Bearer test-admin-key"},
            json={
                "name": "AuthChannel",
                "key_hex": VALID_KEY_32,
            },
        )
        assert response.status_code == 201


class TestUpdateChannel:
    """Tests for PUT /channels/{channel_id} endpoint."""

    def test_update_channel_visibility(self, client_no_auth, sample_channel):
        """Test updating channel visibility."""
        response = client_no_auth.put(
            f"/api/v1/channels/{sample_channel.id}",
            json={"visibility": "member"},
        )
        assert response.status_code == 200
        assert response.json()["visibility"] == "member"

    def test_update_channel_key(self, client_no_auth, sample_channel):
        """Test updating channel key regenerates hash."""
        response = client_no_auth.put(
            f"/api/v1/channels/{sample_channel.id}",
            json={"key_hex": ALT_KEY_32},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key_hex"] == ALT_KEY_32
        assert data["channel_hash"] == Channel.compute_channel_hash(ALT_KEY_32)

    def test_update_channel_enabled(self, client_no_auth, sample_channel):
        """Test disabling a channel."""
        response = client_no_auth.put(
            f"/api/v1/channels/{sample_channel.id}",
            json={"enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_update_channel_not_found(self, client_no_auth):
        """Test updating non-existent channel returns 404."""
        response = client_no_auth.put(
            "/api/v1/channels/nonexistent-id",
            json={"visibility": "admin"},
        )
        assert response.status_code == 404

    def test_update_channel_duplicate_key(self, client_no_auth, api_db_session):
        """Test updating key to one already in use returns 409."""
        key1 = "AABBCCDDEEFF00112233445566778899"
        key2 = "11223344556677889900AABBCCDDEEFF"
        ch1 = Channel(
            name="Ch1",
            key_hex=key1,
            channel_hash=Channel.compute_channel_hash(key1),
        )
        ch2 = Channel(
            name="Ch2",
            key_hex=key2,
            channel_hash=Channel.compute_channel_hash(key2),
        )
        api_db_session.add_all([ch1, ch2])
        api_db_session.commit()

        response = client_no_auth.put(
            f"/api/v1/channels/{ch1.id}",
            json={"key_hex": key2},
        )
        assert response.status_code == 409

    def test_update_channel_same_key_allowed(self, client_no_auth, sample_channel):
        """Test updating channel with its own key is allowed."""
        response = client_no_auth.put(
            f"/api/v1/channels/{sample_channel.id}",
            json={"key_hex": sample_channel.key_hex},
        )
        assert response.status_code == 200


class TestDeleteChannel:
    """Tests for DELETE /channels/{channel_id} endpoint."""

    def test_delete_channel_success(self, client_no_auth, sample_channel):
        """Test deleting a channel."""
        response = client_no_auth.delete(f"/api/v1/channels/{sample_channel.id}")
        assert response.status_code == 204

        response = client_no_auth.get("/api/v1/channels")
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_delete_channel_not_found(self, client_no_auth):
        """Test deleting non-existent channel returns 404."""
        response = client_no_auth.delete("/api/v1/channels/nonexistent-id")
        assert response.status_code == 404

    def test_delete_channel_with_auth(self, client_with_auth, api_db_session):
        """Test deleting channel requires admin key."""
        key = "AABBCCDDEEFF00112233445566778899"
        ch = Channel(
            name="ToDelete",
            key_hex=key,
            channel_hash=Channel.compute_channel_hash(key),
        )
        api_db_session.add(ch)
        api_db_session.commit()

        response = client_with_auth.delete(f"/api/v1/channels/{ch.id}")
        assert response.status_code == 401

        response = client_with_auth.delete(
            f"/api/v1/channels/{ch.id}",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert response.status_code == 204
