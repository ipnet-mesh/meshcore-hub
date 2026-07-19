"""Tests for dashboard API routes."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from meshcore_hub.api.routes.dashboard import _date_bucket_key
from meshcore_hub.common.models import (
    Advertisement,
    EventObserver,
    Message,
    Node,
    NodeTag,
    Channel,
    RawPacket,
)
from meshcore_hub.common.models import UserProfile
from meshcore_hub.common.models import (
    PacketPathHop,
    Route,
    RouteNode,
)


class TestDateBucketKey:
    """Unit tests for the _date_bucket_key dialect-neutral normalization helper."""

    def test_str_passthrough(self) -> None:
        """SQLite returns str — pass through unchanged."""
        assert _date_bucket_key("2026-06-15") == "2026-06-15"

    def test_date_object_normalized(self) -> None:
        """Postgres returns datetime.date — coerce to %Y-%m-%d string."""
        assert _date_bucket_key(date(2026, 1, 5)) == "2026-01-05"

    def test_datetime_object_normalized(self) -> None:
        """Postgres may return datetime.datetime — coerce to %Y-%m-%d string."""
        dt = datetime(2026, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert _date_bucket_key(dt) == "2026-06-15"

    def test_none_passthrough(self) -> None:
        """None passes through unchanged (no collision with string lookups)."""
        assert _date_bucket_key(None) is None

    def test_zero_padded_date(self) -> None:
        """Single-digit months/days are zero-padded."""
        assert _date_bucket_key(date(2026, 1, 5)) == "2026-01-05"


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
        assert data["total_packets"] == 0
        assert data["packets_7d"] == 0
        assert data["channel_message_counts"] == {}
        # recent_advertisements / channel_messages moved to /recent-activity
        assert "recent_advertisements" not in data
        assert "channel_messages" not in data

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

    def test_stats_time_bucket_counts(self, client_no_auth, api_db_session):
        """Conditional-aggregation buckets (active/today/24h/7d) count the
        correct rows across recent and older records."""
        now = datetime.now(timezone.utc)

        # Nodes: one active (seen now), one stale (seen 2 days ago).
        api_db_session.add_all(
            [
                Node(public_key="a" * 64, name="Active", last_seen=now),
                Node(
                    public_key="b" * 64,
                    name="Stale",
                    last_seen=now - timedelta(days=2),
                ),
            ]
        )

        # Messages (contact type → always channel-visible): today, 3 days ago,
        # 10 days ago.
        api_db_session.add_all(
            [
                Message(message_type="contact", text="now", received_at=now),
                Message(
                    message_type="contact",
                    text="3d",
                    received_at=now - timedelta(days=3),
                ),
                Message(
                    message_type="contact",
                    text="10d",
                    received_at=now - timedelta(days=10),
                ),
            ]
        )

        # Flood advertisements: now (24h), 3 days ago (7d), 10 days ago (older).
        api_db_session.add_all(
            [
                Advertisement(public_key="c" * 64, route_type="flood", received_at=now),
                Advertisement(
                    public_key="d" * 64,
                    route_type="flood",
                    received_at=now - timedelta(days=3),
                ),
                Advertisement(
                    public_key="e" * 64,
                    route_type="flood",
                    received_at=now - timedelta(days=10),
                ),
            ]
        )

        # Raw packets: now (7d), 3 days ago (7d), 10 days ago (older).
        api_db_session.add_all(
            [
                RawPacket(event_type="message", received_at=now),
                RawPacket(event_type="message", received_at=now - timedelta(days=3)),
                RawPacket(event_type="message", received_at=now - timedelta(days=10)),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/stats").json()

        assert data["total_nodes"] == 2
        assert data["active_nodes"] == 1

        assert data["total_messages"] == 3
        assert data["messages_today"] == 1
        assert data["messages_7d"] == 2  # now + 3d (10d excluded)

        assert data["total_advertisements"] == 3
        assert data["advertisements_24h"] == 1
        assert data["advertisements_7d"] == 2  # now + 3d (10d excluded)

        assert data["total_packets"] == 3
        assert data["packets_7d"] == 2  # now + 3d (10d excluded)


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
        total_count = sum(point["count"] for point in data["data"])
        assert total_count >= 1
        # The seeded advertisement was yesterday — its bucket must be non-zero.
        # This catches the Postgres flatline bug where func.date() returns a
        # date object that never matches the string key.
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        yesterday_point = next(p for p in data["data"] if p["date"] == yesterday_str)
        assert yesterday_point["count"] >= 1


class TestPacketActivity:
    """Tests for GET /dashboard/packet-activity endpoint."""

    def test_get_packet_activity_empty(self, client_no_auth):
        """Test getting packet activity with empty database."""
        response = client_no_auth.get("/api/v1/dashboard/packet-activity")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30
        for point in data["data"]:
            assert point["count"] == 0
            assert "date" in point

    def test_get_packet_activity_custom_days(self, client_no_auth):
        """Test getting packet activity with custom days parameter."""
        response = client_no_auth.get("/api/v1/dashboard/packet-activity?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_get_packet_activity_max_days(self, client_no_auth):
        """Test that packet activity is capped at 90 days."""
        response = client_no_auth.get("/api/v1/dashboard/packet-activity?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90
        assert len(data["data"]) == 90

    def test_get_packet_activity_with_data(self, client_no_auth, api_db_session):
        """Test getting packet activity with packets across two days.

        Note: Activity endpoints exclude today's data to avoid showing
        incomplete stats early in the day.
        """
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)

        observer = Node(
            public_key="a" * 64,
            name="Observer",
            adv_type="REPEATER",
        )
        api_db_session.add(observer)
        api_db_session.flush()

        api_db_session.add_all(
            [
                RawPacket(
                    observer_node_id=observer.id,
                    event_type="message",
                    received_at=yesterday,
                ),
                RawPacket(
                    observer_node_id=observer.id,
                    event_type="message",
                    received_at=yesterday,
                ),
                RawPacket(
                    observer_node_id=observer.id,
                    event_type="message",
                    received_at=two_days_ago,
                ),
            ]
        )
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/packet-activity?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

        yesterday_str = yesterday.strftime("%Y-%m-%d")
        two_days_ago_str = two_days_ago.strftime("%Y-%m-%d")

        yesterday_point = next(p for p in data["data"] if p["date"] == yesterday_str)
        assert yesterday_point["count"] == 2

        two_days_ago_point = next(
            p for p in data["data"] if p["date"] == two_days_ago_str
        )
        assert two_days_ago_point["count"] == 1

        # All other days in the 7-day window should be zero-filled.
        other_days = [
            p
            for p in data["data"]
            if p["date"] not in (yesterday_str, two_days_ago_str)
        ]
        assert all(p["count"] == 0 for p in other_days)


class TestPacketBreakdown:
    """Tests for GET /dashboard/packet-breakdown endpoint."""

    def test_get_packet_breakdown_empty(self, client_no_auth):
        """Empty database returns empty bucket lists."""
        response = client_no_auth.get("/api/v1/dashboard/packet-breakdown")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 7
        assert data["by_event_type"] == []
        assert data["by_path_width"] == [
            {"label": "1b", "count": 0},
            {"label": "2b", "count": 0},
            {"label": "3b", "count": 0},
        ]

    def test_get_packet_breakdown_custom_days(self, client_no_auth):
        """Custom days parameter is honored."""
        response = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=14")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 14

    def test_get_packet_breakdown_max_days(self, client_no_auth):
        """Days parameter is capped at 90."""
        response = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90

    def test_breakdown_excludes_today(self, client_no_auth, api_db_session):
        """Today's packets are excluded from the breakdown window."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        api_db_session.add_all(
            [
                RawPacket(event_type="advert", received_at=now),
                RawPacket(event_type="advert", received_at=yesterday),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=7").json()
        event_total = sum(b["count"] for b in data["by_event_type"])
        assert event_total == 1  # only yesterday's packet

    def test_event_type_top_six_plus_other(self, client_no_auth, api_db_session):
        """Top 6 event types are shown verbatim; remainder rolls into 'other'."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        # 8 distinct event types with descending counts.
        types = [
            ("type_a", 10),
            ("type_b", 9),
            ("type_c", 8),
            ("type_d", 7),
            ("type_e", 6),
            ("type_f", 5),
            ("type_g", 3),
            ("type_h", 2),
        ]
        for event_type, n in types:
            for _ in range(n):
                api_db_session.add(
                    RawPacket(event_type=event_type, received_at=yesterday)
                )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=7").json()
        buckets = data["by_event_type"]
        assert len(buckets) == 7  # 6 verbatim + "other"
        assert [b["label"] for b in buckets[:6]] == [
            "type_a",
            "type_b",
            "type_c",
            "type_d",
            "type_e",
            "type_f",
        ]
        assert buckets[6]["label"] == "other"
        assert buckets[6]["count"] == 5  # type_g + type_h

    def test_event_type_no_other_when_le_six(self, client_no_auth, api_db_session):
        """No 'other' bucket is emitted when distinct types <= 6."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        for event_type, n in [("type_a", 3), ("type_b", 2), ("type_c", 1)]:
            for _ in range(n):
                api_db_session.add(
                    RawPacket(event_type=event_type, received_at=yesterday)
                )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=7").json()
        labels = [b["label"] for b in data["by_event_type"]]
        assert "other" not in labels
        assert len(labels) == 3

    def test_path_width_fixed_order_zero_fill(self, client_no_auth, api_db_session):
        """Path-width buckets are always 1b/2b/3b, zero-filled, NULL excluded."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        # Seed: two widths present, one missing, plus a NULL.
        for _ in range(4):
            api_db_session.add(RawPacket(path_hash_bytes=1, received_at=yesterday))
        for _ in range(2):
            api_db_session.add(RawPacket(path_hash_bytes=3, received_at=yesterday))
        api_db_session.add(RawPacket(path_hash_bytes=None, received_at=yesterday))
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=7").json()
        widths = data["by_path_width"]
        assert [w["label"] for w in widths] == ["1b", "2b", "3b"]
        assert widths[0]["count"] == 4
        assert widths[1]["count"] == 0  # zero-filled
        assert widths[2]["count"] == 2
        # NULL excluded from denominator.
        width_total = sum(w["count"] for w in widths)
        assert width_total == 6

    def test_path_width_excludes_null(self, client_no_auth, api_db_session):
        """Rows with NULL path_hash_bytes are excluded from all width buckets."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        api_db_session.add_all(
            [
                RawPacket(path_hash_bytes=2, received_at=yesterday),
                RawPacket(path_hash_bytes=None, received_at=yesterday),
                RawPacket(path_hash_bytes=None, received_at=yesterday),
            ]
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=7").json()
        widths = data["by_path_width"]
        assert widths[0]["count"] == 0  # 1b
        assert widths[1]["count"] == 1  # 2b
        assert widths[2]["count"] == 0  # 3b

    def test_breakdown_response_shape(self, client_no_auth, api_db_session):
        """Response conforms to PacketBreakdown schema."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        api_db_session.add(
            RawPacket(event_type="advert", path_hash_bytes=1, received_at=yesterday)
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-breakdown?days=7").json()
        assert "days" in data
        assert "by_event_type" in data
        assert "by_path_width" in data
        assert isinstance(data["by_event_type"], list)
        assert isinstance(data["by_path_width"], list)
        for bucket in data["by_event_type"] + data["by_path_width"]:
            assert "label" in bucket
            assert "count" in bucket
            assert isinstance(bucket["count"], int)


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
        total_count = sum(point["count"] for point in data["data"])
        assert total_count >= 1
        # The seeded message was yesterday — its bucket must be non-zero.
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        yesterday_point = next(p for p in data["data"] if p["date"] == yesterday_str)
        assert yesterday_point["count"] >= 1


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
        # The node was created yesterday — the cumulative count should step
        # up at yesterday's bucket and stay >= 1 for all subsequent days.
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        yesterday_idx = next(
            i for i, p in enumerate(data["data"]) if p["date"] == yesterday_str
        )
        assert data["data"][yesterday_idx]["count"] >= 1
        assert all(p["count"] >= 1 for p in data["data"][yesterday_idx:])

    def test_node_count_is_cumulative_with_baseline(
        self, client_no_auth, api_db_session
    ):
        """Cumulative series counts pre-window nodes from day 0 and steps up
        on the day a new in-window node is created."""
        now = datetime.now(timezone.utc)
        # Created well before a 30-day window: must be in the baseline, so
        # every day in the series includes it.
        api_db_session.add(
            Node(
                public_key="a" * 64,
                name="Old Node",
                created_at=now - timedelta(days=60),
            )
        )
        # Created inside the window, 5 days ago: bumps the running total on
        # its day and stays for the rest of the series.
        api_db_session.add(
            Node(
                public_key="b" * 64,
                name="Recent Node",
                created_at=now - timedelta(days=5),
            )
        )
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/node-count?days=30")
        assert response.status_code == 200
        counts = [point["count"] for point in response.json()["data"]]

        # Baseline node is present from the very first day.
        assert counts[0] == 1
        # Cumulative => never decreases.
        assert counts == sorted(counts)
        # Recent node lifts the total to 2 by the end, stepping up exactly once.
        assert counts[-1] == 2
        assert counts.count(2) >= 1 and 1 in counts


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

        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_advertisements"]) == 1
        assert data["recent_advertisements"][0]["name"] == "Flood"
        assert data["recent_advertisements"][0]["route_type"] == "flood"
        assert data["recent_advertisements"][0]["observers"] == []
        assert data["recent_advertisements"][0]["observed_by"] is None

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


@pytest.fixture
def channels_with_messages(api_db_session):
    """Create public and admin channels with messages.

    Module-level so both TestDashboardChannelVisibility (channel_message_counts
    on /dashboard/stats) and TestDashboardRecentActivity (channel_messages on
    /dashboard/recent-activity) can share the same setup.
    """
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


class TestDashboardChannelVisibility:
    """Tests for channel visibility filtering on dashboard stats."""

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

    def test_recent_advertisements_includes_tag_name(
        self, client_no_auth, api_db_session
    ):
        """Recent advertisements resolve tag_name from name tags."""
        now = datetime.now(timezone.utc)
        pub_key = "aa" * 16
        node = Node(
            public_key=pub_key,
            name="NodeName",
            adv_type="CLIENT",
            first_seen=now,
            last_seen=now,
        )
        api_db_session.add(node)
        api_db_session.commit()

        tag = NodeTag(node_id=node.id, key="name", value="TagName")
        api_db_session.add(tag)

        ad = Advertisement(
            public_key=pub_key,
            name=None,
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
        )
        api_db_session.add(ad)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_advertisements"]) == 1
        assert data["recent_advertisements"][0]["tag_name"] == "TagName"
        assert data["recent_advertisements"][0]["route_type"] == "flood"
        assert data["recent_advertisements"][0]["observers"] == []
        assert data["recent_advertisements"][0]["observed_by"] is None

    def test_recent_advertisements_includes_observers(
        self, client_no_auth, api_db_session
    ):
        """Recent advertisements include observer list via event_observers."""
        from hashlib import md5

        now = datetime.now(timezone.utc)
        observer_node = Node(
            public_key="cc" * 16,
            name="ObserverStation",
            first_seen=now,
            last_seen=now,
        )
        api_db_session.add(observer_node)
        api_db_session.commit()

        event_hash = md5(b"dashboard-ad-observers").hexdigest()
        ad = Advertisement(
            public_key="dd" * 16,
            name="HeardAd",
            adv_type="REPEATER",
            received_at=now,
            route_type="flood",
            event_hash=event_hash,
            observer_node_id=observer_node.id,
        )
        api_db_session.add(ad)

        observer = EventObserver(
            event_type="advertisement",
            event_hash=event_hash,
            observer_node_id=observer_node.id,
            observed_at=now,
        )
        api_db_session.add(observer)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_advertisements"]) == 1
        item = data["recent_advertisements"][0]
        assert item["route_type"] == "flood"
        assert len(item["observers"]) == 1
        assert item["observers"][0]["public_key"] == observer_node.public_key

    def test_recent_advertisements_includes_observed_by(
        self, client_no_auth, api_db_session
    ):
        """Recent advertisements resolve observed_by from observer_node_id."""
        now = datetime.now(timezone.utc)
        observer_node = Node(
            public_key="ee" * 16,
            name="InterfaceNode",
            first_seen=now,
            last_seen=now,
        )
        api_db_session.add(observer_node)
        api_db_session.commit()

        ad = Advertisement(
            public_key="ff" * 16,
            name="LegacyAd",
            adv_type="CLIENT",
            received_at=now,
            route_type="flood",
            observer_node_id=observer_node.id,
        )
        api_db_session.add(ad)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_advertisements"]) == 1
        item = data["recent_advertisements"][0]
        assert item["route_type"] == "flood"
        assert item["observers"] == []
        assert item["observed_by"] == observer_node.public_key

    def test_operator_sees_community_and_member_channel_counts(
        self, client_no_auth, api_db_session
    ):
        """Operator role sees community + member channels but not admin in stats."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        mem_key = "11223344556677889900AABBCCDDEEFF"
        adm_key = "FFEEDDCCBBAA99887766554433221100"
        pub_idx = int(Channel.compute_channel_hash(pub_key), 16)
        mem_idx = int(Channel.compute_channel_hash(mem_key), 16)
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)

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

        for idx, text in [
            (pub_idx, "Pub msg"),
            (mem_idx, "Mem msg"),
            (adm_idx, "Adm msg"),
        ]:
            msg = Message(
                message_type="channel",
                channel_idx=idx,
                text=text,
                received_at=datetime.now(timezone.utc),
            )
            api_db_session.add(msg)
        api_db_session.commit()

        response = client_no_auth.get(
            "/api/v1/dashboard/stats",
            headers={"X-User-Roles": "operator"},
        )
        assert response.status_code == 200
        data = response.json()
        assert str(pub_idx) in data["channel_message_counts"]
        assert str(mem_idx) in data["channel_message_counts"]
        assert str(adm_idx) not in data["channel_message_counts"]


class TestDashboardRecentActivity:
    """Tests for GET /dashboard/recent-activity (split from /dashboard/stats)."""

    def test_recent_activity_empty(self, client_no_auth):
        """Recent activity endpoint with empty database returns empty shapes."""
        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert data["recent_advertisements"] == []
        assert data["channel_messages"] == {}

    def test_recent_activity_does_not_return_counts(
        self, client_no_auth, channels_with_messages
    ):
        """The recent-activity endpoint drops channel_message_counts (those
        stay on /dashboard/stats as aggregate counts)."""
        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert "channel_message_counts" not in data

    def test_recent_activity_channel_messages_visibility(
        self, client_no_auth, channels_with_messages
    ):
        """Anonymous viewers only see community-channel messages."""
        pub_idx, adm_idx = channels_with_messages
        response = client_no_auth.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.json()
        assert str(pub_idx) in data["channel_messages"]
        assert str(adm_idx) not in data["channel_messages"]

    def test_recent_activity_admin_sees_all_channels(
        self, client_no_auth, channels_with_messages
    ):
        """Admin role sees messages on every channel."""
        pub_idx, adm_idx = channels_with_messages
        response = client_no_auth.get(
            "/api/v1/dashboard/recent-activity",
            headers={"X-User-Roles": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert str(pub_idx) in data["channel_messages"]
        assert str(adm_idx) in data["channel_messages"]

    def test_recent_activity_caches_at_default_ttl_not_dashboard(
        self, client_no_auth, api_db_session
    ):
        """The recent-activity endpoint uses the default redis_cache_ttl
        (not redis_cache_ttl_dashboard), so the Recent Adverts / Recent
        Channel Messages widgets stay fresh at the 30 s default while the
        aggregate counts on /dashboard/stats cache for an hour."""
        from unittest.mock import MagicMock

        client_no_auth.app.state.redis_cache = MagicMock()
        client_no_auth.app.state.redis_cache.get.return_value = None
        client_no_auth.app.state.redis_cache_ttl = 30
        client_no_auth.app.state.redis_cache_ttl_dashboard = 3600

        client_no_auth.get("/api/v1/dashboard/recent-activity")

        # First MISS stores the response at the default TTL (30 s), not
        # the dashboard TTL (3600 s) — that's the whole point of the split.
        # cache.set is invoked positionally as set(key, envelope, ttl).
        client_no_auth.app.state.redis_cache.set.assert_called_once()
        args, _ = client_no_auth.app.state.redis_cache.set.call_args
        assert args[2] == 30


class TestDashboardDateBucketRegression:
    """Regression tests for the Postgres date-bucket flatline bug.

    These tests seed data at deterministic UTC timestamps and assert the
    specific date buckets have non-zero counts. On SQLite (where
    func.date() returns str) these always passed. On Postgres (where
    func.date() returns date) these would have failed before the
    _date_bucket_key fix, because the dict lookup by string key would
    miss the date-object key.

    Run against Postgres with::

        TEST_DATABASE_BACKEND=postgres \\
        TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost:55432/test \\
        pytest tests/test_api/test_dashboard.py -k Regression
    """

    def test_activity_nonzero_on_seeded_day(self, client_no_auth, api_db_session):
        """Activity chart shows non-zero count for the seeded day."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        api_db_session.add(
            Advertisement(
                public_key="a" * 64,
                name="RegressionNode",
                adv_type="REPEATER",
                route_type="flood",
                received_at=two_days_ago,
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/activity").json()
        seeded_str = two_days_ago.strftime("%Y-%m-%d")
        seeded_point = next(p for p in data["data"] if p["date"] == seeded_str)
        assert seeded_point["count"] == 1

    def test_message_activity_nonzero_on_seeded_day(
        self, client_no_auth, api_db_session
    ):
        """Message activity chart shows non-zero count for the seeded day."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        api_db_session.add(
            Message(
                message_type="direct",
                pubkey_prefix="abc123",
                text="regression test",
                received_at=two_days_ago,
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/message-activity").json()
        seeded_str = two_days_ago.strftime("%Y-%m-%d")
        seeded_point = next(p for p in data["data"] if p["date"] == seeded_str)
        assert seeded_point["count"] == 1

    def test_packet_activity_nonzero_on_seeded_day(
        self, client_no_auth, api_db_session
    ):
        """Packet activity chart shows non-zero count for the seeded day."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        api_db_session.add(
            RawPacket(
                event_type="message",
                received_at=two_days_ago,
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/packet-activity").json()
        seeded_str = two_days_ago.strftime("%Y-%m-%d")
        seeded_point = next(p for p in data["data"] if p["date"] == seeded_str)
        assert seeded_point["count"] == 1

    def test_node_count_steps_up_on_seeded_day(self, client_no_auth, api_db_session):
        """Node count chart steps up on the seeded creation day."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        api_db_session.add(
            Node(
                public_key="b" * 64,
                name="RegressionNode",
                created_at=two_days_ago,
            )
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/node-count").json()
        seeded_str = two_days_ago.strftime("%Y-%m-%d")
        seeded_idx = next(
            i for i, p in enumerate(data["data"]) if p["date"] == seeded_str
        )
        # Before the seeded day: 0 nodes. On/after: 1.
        assert data["data"][seeded_idx]["count"] == 1
        if seeded_idx > 0:
            assert data["data"][seeded_idx - 1]["count"] == 0


# ---------------------------------------------------------------------------
# GET /dashboard/routes-overview
# ---------------------------------------------------------------------------


def _make_node_with_pk(session, public_key: str, name: str | None = None) -> Node:
    node = Node(public_key=public_key, name=name)
    session.add(node)
    session.flush()
    return node


def _make_route_with_nodes(
    session,
    from_label: str,
    to_label: str,
    pubkeys: list[str],
    visibility: str = "community",
    enabled: bool = True,
    threshold: int = 3,
    clear_bar: int | None = None,
    match_width: int = 1,
) -> Route:
    nodes = [_make_node_with_pk(session, pk) for pk in pubkeys]
    route = Route(
        from_label=from_label,
        to_label=to_label,
        visibility=visibility,
        enabled=enabled,
        match_width=match_width,
        packet_count_threshold=threshold,
        clear_threshold=clear_bar,
    )
    session.add(route)
    session.flush()
    for pos, n in enumerate(nodes):
        session.add(
            RouteNode(
                route_id=route.id,
                node_id=n.id,
                position=pos,
                expected_hash=n.public_key[: 2 * match_width].upper(),
            )
        )
    session.flush()
    return route


def _make_reception_for_route(
    session,
    packet_hash: str,
    path_hashes: list[str],
    received_at: datetime,
) -> None:
    """Insert a RawPacket + PacketPathHop rows for a test reception."""
    from uuid import uuid4

    rp_id = str(uuid4())
    session.add(
        RawPacket(
            id=rp_id,
            packet_hash=packet_hash,
            received_at=received_at,
        )
    )
    session.flush()
    for pos, nh in enumerate(path_hashes):
        session.add(
            PacketPathHop(
                raw_packet_id=rp_id,
                position=pos,
                node_hash=nh,
                packet_hash=packet_hash,
                received_at=received_at,
            )
        )
    session.flush()


class TestRoutesOverview:
    """Tests for GET /dashboard/routes-overview."""

    def test_empty(self, client_no_auth):
        """No routes seeded → empty routes array and by_state."""
        resp = client_no_auth.get("/api/v1/dashboard/routes-overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["routes"] == []
        assert data["by_state"] == []
        assert data["days"] == 7

    def test_default_days_is_7(self, client_no_auth, api_db_session):
        resp = client_no_auth.get("/api/v1/dashboard/routes-overview")
        assert resp.json()["days"] == 7

    def test_custom_days(self, client_no_auth, api_db_session):
        resp = client_no_auth.get("/api/v1/dashboard/routes-overview?days=3")
        assert resp.json()["days"] == 3

    def test_days_clamped_to_retention(self, client_no_auth, api_db_session):
        from meshcore_hub.common.config import get_collector_settings

        retention = get_collector_settings().effective_raw_packet_retention_days
        resp = client_no_auth.get(
            f"/api/v1/dashboard/routes-overview?days={retention + 30}"
        )
        assert resp.json()["days"] == retention

    def test_history_includes_today_segment(self, client_no_auth, api_db_session):
        """Each route's history has ``days + 1`` entries (include_today)."""
        _make_route_with_nodes(api_db_session, "A", "B", ["a" * 64, "b" * 64])
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/routes-overview?days=7").json()
        assert len(data["routes"]) == 1
        history = data["routes"][0]["history"]
        # 7 calendar days + today segment = 8 entries.
        assert len(history) == 8
        # Today's entry has the rolling-window state semantics.
        today_entry = history[-1]
        assert today_entry["quality"] in {
            "clear",
            "marginal",
            "failing",
            "unknown",
        }
        assert today_entry["state"] in {
            "healthy",
            "unhealthy",
            "no_coverage",
        }

    def test_visibility_filter_hides_admin_routes(self, client_no_auth, api_db_session):
        """Anonymous users must not see admin-only routes in the overview."""
        _make_route_with_nodes(
            api_db_session,
            "Public",
            "Endpoint",
            ["a" * 64, "b" * 64],
            visibility="community",
        )
        _make_route_with_nodes(
            api_db_session,
            "Secret",
            "Endpoint",
            ["c" * 64, "d" * 64],
            visibility="admin",
        )
        api_db_session.commit()

        # Anonymous: only the community route.
        anon = client_no_auth.get("/api/v1/dashboard/routes-overview").json()
        labels = [r["from_label"] for r in anon["routes"]]
        assert labels == ["Public"]

        # Admin sees both.
        admin = client_no_auth.get(
            "/api/v1/dashboard/routes-overview",
            headers={"X-User-Roles": "admin"},
        ).json()
        admin_labels = sorted(r["from_label"] for r in admin["routes"])
        assert admin_labels == ["Public", "Secret"]

    def test_by_state_buckets_current_state(self, client_no_auth, api_db_session):
        """``by_state`` counts route current state across the fleet."""
        from meshcore_hub.collector.routes import (
            evaluate_route,
            upsert_route_result,
        )

        # Healthy route (3 packets in window, low clear bar) → healthy.
        healthy = _make_route_with_nodes(
            api_db_session,
            "Healthy",
            "End",
            ["a" * 64, "b" * 64],
            threshold=3,
            clear_bar=3,
        )
        now = datetime.now(timezone.utc)
        for i in range(3):
            _make_reception_for_route(
                api_db_session,
                f"pk{i}",
                ["AA", "BB"],
                now - timedelta(hours=1, seconds=i),
            )
        # Disabled route → state=disabled regardless of packets.
        _make_route_with_nodes(
            api_db_session,
            "Disabled",
            "End",
            ["c" * 64, "e" * 64],
            enabled=False,
        )
        # Fresh route (no result yet, no packets) → no_coverage fallback.
        _make_route_with_nodes(
            api_db_session,
            "Fresh",
            "End",
            ["f" * 64, "9" * 64],
        )
        # Populate route_result for the healthy route like the evaluator does.
        since = now - timedelta(hours=healthy.window_hours)
        state, quality, matched = evaluate_route(api_db_session, healthy, since)
        upsert_route_result(api_db_session, healthy, state, quality, matched)
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/routes-overview").json()
        state_map = {b["label"]: b["count"] for b in data["by_state"]}
        # Healthy route picks up `healthy`; disabled picks up `disabled`;
        # fresh route with no route_result falls back to `no_coverage`.
        assert state_map.get("healthy", 0) >= 1
        assert state_map.get("disabled", 0) >= 1
        assert state_map.get("no_coverage", 0) >= 1

        # The healthy route's per-route entry carries the matching state.
        healthy_entry = next(r for r in data["routes"] if r["from_label"] == "Healthy")
        assert healthy_entry["state"] == "healthy"
        assert healthy_entry["quality"] == "clear"
        assert healthy_entry["matched_count"] == 3

    def test_disabled_route_matched_count_is_none(self, client_no_auth, api_db_session):
        _make_route_with_nodes(
            api_db_session,
            "Off",
            "End",
            ["a" * 64, "b" * 64],
            enabled=False,
        )
        api_db_session.commit()

        data = client_no_auth.get("/api/v1/dashboard/routes-overview").json()
        route = data["routes"][0]
        assert route["state"] == "disabled"
        assert route["matched_count"] is None

    def test_cache_key_is_role_scoped(self, client_no_auth, api_db_session):
        """Different roles get independent cache entries (sanity: both
        return 200, response differs when visibility-filtered)."""
        from unittest.mock import MagicMock

        _make_route_with_nodes(
            api_db_session,
            "AdminOnly",
            "End",
            ["a" * 64, "b" * 64],
            visibility="admin",
        )
        api_db_session.commit()

        # Mock cache that records every set() call's key.
        keys_seen: list[str] = []
        mock = MagicMock()
        mock.get.return_value = None

        def _set(key, value, ttl):
            keys_seen.append(key)

        mock.set.side_effect = _set
        client_no_auth.app.state.redis_cache = mock
        client_no_auth.app.state.redis_cache_ttl = 30

        client_no_auth.get("/api/v1/dashboard/routes-overview")
        client_no_auth.get(
            "/api/v1/dashboard/routes-overview",
            headers={"X-User-Roles": "admin"},
        )

        # Two cache fills, role differs between them.
        assert len(keys_seen) == 2
        assert any("anonymous" in k for k in keys_seen)
        assert any("admin" in k for k in keys_seen)
