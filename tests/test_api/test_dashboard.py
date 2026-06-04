"""Tests for dashboard API routes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from meshcore_hub.common.models import Advertisement, Message, Node, Channel
from meshcore_hub.common.models import UserProfile


class TestDashboardStats:
    """Tests for GET /dashboard/stats endpoint."""

    def test_get_stats_empty(self, client_no_auth):
        """Test getting stats with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_nodes"] == 0
        assert data["active_nodes"] == 0
        assert data["total_messages"] == 0
        assert data["messages_today"] == 0
        assert data["total_advertisements"] == 0
        assert data["channel_message_counts"] == {}

    def test_get_stats_with_data(
        self, client_no_auth, sample_node, sample_message, sample_advertisement
    ):
        """Test getting stats with data in database."""
        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_nodes"] == 1
        assert data["active_nodes"] == 1  # Node was just created
        assert data["total_messages"] == 1
        assert data["total_advertisements"] == 1


class TestDashboardHtmlRemoved:
    """Tests that legacy HTML dashboard endpoint has been removed."""

    def test_dashboard_html_endpoint_removed(self, client_no_auth):
        """Test that GET /dashboard no longer returns HTML (legacy endpoint removed)."""
        response = client_no_auth.get("/api/v1/dashboard")
        assert response.status_code in (404, 405)

    def test_dashboard_html_endpoint_removed_trailing_slash(self, client_no_auth):
        """Test that GET /dashboard/ also returns 404/405."""
        response = client_no_auth.get("/api/v1/dashboard/")
        assert response.status_code in (404, 405)


class TestDashboardAuthenticatedJsonRoutes:
    """Tests that dashboard JSON sub-routes return valid JSON with authentication."""

    def test_stats_returns_json_when_authenticated(self, client_with_auth):
        """Test GET /dashboard/stats returns 200 with valid JSON when authenticated."""
        response = client_with_auth.get(
            "/api/v1/dashboard/stats",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_nodes" in data
        assert "active_nodes" in data
        assert "total_messages" in data
        assert "total_advertisements" in data

    def test_activity_returns_json_when_authenticated(self, client_with_auth):
        """Test GET /dashboard/activity returns 200 with valid JSON when authenticated."""
        response = client_with_auth.get(
            "/api/v1/dashboard/activity",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_message_activity_returns_json_when_authenticated(self, client_with_auth):
        """Test GET /dashboard/message-activity returns 200 with valid JSON when authenticated."""
        response = client_with_auth.get(
            "/api/v1/dashboard/message-activity",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_node_count_returns_json_when_authenticated(self, client_with_auth):
        """Test GET /dashboard/node-count returns 200 with valid JSON when authenticated."""
        response = client_with_auth.get(
            "/api/v1/dashboard/node-count",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert "data" in data
        assert isinstance(data["data"], list)


class TestDashboardActivity:
    """Tests for GET /dashboard/activity endpoint."""

    @pytest.fixture
    def past_advertisement(self, api_db_session):
        """Create an advertisement from yesterday (since today is excluded)."""
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        advert = Advertisement(
            public_key="abc123def456abc123def456abc123de",
            name="TestNode",
            adv_type="REPEATER",
            received_at=yesterday,
        )
        api_db_session.add(advert)
        api_db_session.commit()
        api_db_session.refresh(advert)
        return advert

    def test_get_activity_empty(self, client_no_auth):
        """Test getting activity with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/activity")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        # All counts should be 0
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_activity_custom_days(self, client_no_auth):
        """Test getting activity with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/activity?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_activity_max_days(self, client_no_auth):
        """Test that activity is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/activity?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_activity_with_data(self, client_no_auth, past_advertisement):
        """Test getting activity with advertisement in database.

        Note: Activity endpoints exclude today's data to avoid showing
        incomplete stats early in the day.
        """
        response = client_no_auth.get("/api/v1/dashboard/activity")
        assert response.status_code == 200
        data = response.json()
        # At least one day should have a count > 0
        total_count = sum(point["count"] for point in data["data"])
        assert total_count >= 1


class TestMessageActivity:
    """Tests for GET /dashboard/message-activity endpoint."""

    @pytest.fixture
    def past_message(self, api_db_session):
        """Create a message from yesterday (since today is excluded)."""
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        message = Message(
            message_type="direct",
            pubkey_prefix="abc123",
            text="Hello World",
            received_at=yesterday,
        )
        api_db_session.add(message)
        api_db_session.commit()
        api_db_session.refresh(message)
        return message

    def test_get_message_activity_empty(self, client_no_auth):
        """Test getting message activity with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        # All counts should be 0
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_message_activity_custom_days(self, client_no_auth):
        """Test getting message activity with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_message_activity_max_days(self, client_no_auth):
        """Test that message activity is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/message-activity?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_message_activity_with_data(self, client_no_auth, past_message):
        """Test getting message activity with message in database.

        Note: Activity endpoints exclude today's data to avoid showing
        incomplete stats early in the day.
        """
        response = client_no_auth.get("/api/v1/dashboard/message-activity")
        assert response.status_code == 200
        data = response.json()
        # At least one day should have a count > 0
        total_count = sum(point["count"] for point in data["data"])
        assert total_count >= 1


class TestNodeCountHistory:
    """Tests for GET /dashboard/node-count endpoint."""

    @pytest.fixture
    def past_node(self, api_db_session):
        """Create a node from yesterday (since today is excluded)."""
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        node = Node(
            public_key="abc123def456abc123def456abc123de",
            name="Test Node",
            adv_type="REPEATER",
            first_seen=yesterday,
            last_seen=yesterday,
            created_at=yesterday,
        )
        api_db_session.add(node)
        api_db_session.commit()
        api_db_session.refresh(node)
        return node

    def test_get_node_count_empty(self, client_no_auth):
        """Test getting node count with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/node-count")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        # All counts should be 0
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_node_count_custom_days(self, client_no_auth):
        """Test getting node count with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/node-count?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_node_count_max_days(self, client_no_auth):
        """Test that node count is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/node-count?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_node_count_with_data(self, client_no_auth, past_node):
        """Test getting node count with node in database.

        Note: Activity endpoints exclude today's data to avoid showing
        incomplete stats early in the day.
        """
        response = client_no_auth.get("/api/v1/dashboard/node-count")
        assert response.status_code == 200
        data = response.json()
        # At least one day should have a count > 0 (cumulative)
        # The last day should have count >= 1
        assert data["data"][-1]["count"] >= 1


class TestDashboardTestUserExclusion:
    """Tests for test user exclusion from dashboard stats."""

    @pytest.fixture
    def profiles_with_roles(self, api_db_session):
        """Create profiles with various role combinations."""
        profiles = []
        for user_id, name, roles in [
            ("op-1", "Operator One", "operator"),
            ("op-2", "Operator Two", "operator,member"),
            ("mem-1", "Member One", "member"),
            ("test-1", "Test Operator", "operator,test"),
            ("test-2", "Test Member", "member,test"),
            ("test-3", "Test Both", "operator,member,test"),
            ("none-1", "No Roles", ""),
        ]:
            p = UserProfile(user_id=user_id, name=name, roles=roles)
            api_db_session.add(p)
            profiles.append((user_id, roles))
        api_db_session.commit()
        return profiles

    def test_test_users_excluded_from_operator_count(
        self, client_no_auth, profiles_with_roles
    ):
        """Test that users with the test role are excluded from operator count."""
        with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.oidc_role_operator = "operator"
            settings.oidc_role_member = "member"
            settings.oidc_role_test = "test"

            response = client_no_auth.get("/api/v1/dashboard/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_operators"] == 2
            assert data["total_members"] == 2

    def test_empty_test_role_excludes_no_one(self, client_no_auth, profiles_with_roles):
        """Test that an empty test role does not filter any users."""
        with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.oidc_role_operator = "operator"
            settings.oidc_role_member = "member"
            settings.oidc_role_test = ""

            response = client_no_auth.get("/api/v1/dashboard/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_operators"] == 4
            assert data["total_members"] == 4

    def test_no_profiles(self, client_no_auth):
        """Test stats with no profiles returns zero counts."""
        with patch("meshcore_hub.common.config.get_web_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.oidc_role_operator = "operator"
            settings.oidc_role_member = "member"
            settings.oidc_role_test = "test"

            response = client_no_auth.get("/api/v1/dashboard/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_operators"] == 0
            assert data["total_members"] == 0


class TestDashboardFloodOnlyFilter:
    """Tests for flood-only advertisement filtering on dashboard."""

    def test_stats_excludes_direct_adverts(self, client_no_auth, api_db_session):
        """Dashboard stats exclude direct (zero-hop) advertisements."""
        now = datetime.now(timezone.utc)
        flood_ad = Advertisement(
            public_key="aa" * 16,
            name="Flood",
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
        )
        direct_ad = Advertisement(
            public_key="bb" * 16,
            name="Direct",
            adv_type="CLIENT",
            received_at=now,
            route_type="direct",
        )
        null_ad = Advertisement(
            public_key="cc" * 16,
            name="Historical",
            adv_type="CLIENT",
            received_at=now,
            route_type=None,
        )
        api_db_session.add_all([flood_ad, direct_ad, null_ad])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_advertisements"] == 2

    def test_recent_ads_excludes_direct(self, client_no_auth, api_db_session):
        """Recent advertisements list excludes direct adverts."""
        now = datetime.now(timezone.utc)
        direct_ad = Advertisement(
            public_key="aa" * 16,
            name="Direct",
            adv_type="CLIENT",
            received_at=now,
            route_type="direct",
        )
        flood_ad = Advertisement(
            public_key="bb" * 16,
            name="Flood",
            adv_type="CLIENT",
            received_at=now - timedelta(seconds=1),
            route_type="flood",
        )
        api_db_session.add_all([direct_ad, flood_ad])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_advertisements"]) == 1
        assert data["recent_advertisements"][0]["name"] == "Flood"

    def test_activity_excludes_direct(self, client_no_auth, api_db_session):
        """Activity endpoint excludes direct advertisements."""
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        direct_ad = Advertisement(
            public_key="aa" * 16,
            name="Direct",
            adv_type="CLIENT",
            received_at=yesterday,
            route_type="direct",
        )
        flood_ad = Advertisement(
            public_key="bb" * 16,
            name="Flood",
            adv_type="CLIENT",
            received_at=yesterday,
            route_type="flood",
        )
        api_db_session.add_all([direct_ad, flood_ad])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/activity")
        assert response.status_code == 200
        data = response.json()
        total_count = sum(point["count"] for point in data["data"])
        assert total_count == 1


class TestDashboardChannelVisibility:
    """Tests for channel visibility filtering on dashboard stats."""

    @pytest.fixture
    def channels_with_messages(self, api_db_session):
        """Create public and admin channels with messages."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        pub_idx = int(Channel.compute_channel_hash(pub_key), 16)
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)

        pub_ch = Channel(
            name="CommunityCh",
            key_hex=pub_key,
            channel_hash=Channel.compute_channel_hash(pub_key),
            visibility="community",
            enabled=True,
        )
        adm_ch = Channel(
            name="AdminCh",
            key_hex=adm_key,
            channel_hash=Channel.compute_channel_hash(adm_key),
            visibility="admin",
            enabled=True,
        )
        api_db_session.add_all([pub_ch, adm_ch])

        pub_msg = Message(
            message_type="channel",
            channel_idx=pub_idx,
            text="Public message",
            received_at=datetime.now(timezone.utc),
        )
        adm_msg = Message(
            message_type="channel",
            channel_idx=adm_idx,
            text="Admin message",
            received_at=datetime.now(timezone.utc),
        )
        direct_msg = Message(
            message_type="direct",
            pubkey_prefix="abc123",
            text="Direct message",
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add_all([pub_msg, adm_msg, direct_msg])
        api_db_session.commit()

        return pub_idx, adm_idx

    def test_anonymous_sees_only_community_messages(
        self, client_no_auth, channels_with_messages
    ):
        """Anonymous users only see community and direct messages in stats."""
        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 2

    def test_admin_sees_all_messages(self, client_no_auth, channels_with_messages):
        """Admin users see all messages in stats."""
        response = client_no_auth.get(
            "/api/v1/dashboard/stats",
            headers={"X-User-Roles": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 3

    def test_channel_message_counts_filtered(
        self, client_no_auth, channels_with_messages
    ):
        """Channel message counts exclude hidden channels."""
        pub_idx, adm_idx = channels_with_messages

        response = client_no_auth.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert str(pub_idx) in data["channel_message_counts"]
        assert str(adm_idx) not in data["channel_message_counts"]

    def test_admin_channel_message_counts_all(
        self, client_no_auth, channels_with_messages
    ):
        """Admin users see all channel message counts."""
        pub_idx, adm_idx = channels_with_messages

        response = client_no_auth.get(
            "/api/v1/dashboard/stats",
            headers={"X-User-Roles": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert str(pub_idx) in data["channel_message_counts"]
        assert str(adm_idx) in data["channel_message_counts"]

    def test_message_activity_respects_visibility(self, client_no_auth, api_db_session):
        """Message activity endpoint filters by channel visibility."""
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)

        adm_ch = Channel(
            name="AdminCh",
            key_hex=adm_key,
            channel_hash=Channel.compute_channel_hash(adm_key),
            visibility="admin",
            enabled=True,
        )
        api_db_session.add(adm_ch)

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        adm_msg = Message(
            message_type="channel",
            channel_idx=adm_idx,
            text="Admin msg",
            received_at=yesterday,
        )
        api_db_session.add(adm_msg)
        api_db_session.commit()

        response_anon = client_no_auth.get("/api/v1/dashboard/message-activity")
        assert response_anon.status_code == 200
        anon_data = response_anon.json()
        anon_total = sum(p["count"] for p in anon_data["data"])
        assert anon_total == 0

        response_admin = client_no_auth.get(
            "/api/v1/dashboard/message-activity",
            headers={"X-User-Roles": "admin"},
        )
        assert response_admin.status_code == 200
        admin_data = response_admin.json()
        admin_total = sum(p["count"] for p in admin_data["data"])
        assert admin_total >= 1
