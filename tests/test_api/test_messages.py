"""Tests for message API routes."""

from datetime import datetime, timedelta, timezone

import pytest

from meshcore_hub.common.hash_utils import compute_message_hash
from meshcore_hub.common.models import EventObserver, Message, Node, NodeTag, Channel


class TestListMessages:
    """Tests for GET /messages endpoint."""

    def test_list_messages_empty(self, client_no_auth):
        """Test listing messages when database is empty."""
        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_messages_with_data(self, client_no_auth, sample_message):
        """Test listing messages with data in database."""
        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["text"] == sample_message.text
        assert data["items"][0]["message_type"] == sample_message.message_type

    def test_list_messages_filter_by_type(self, client_no_auth, sample_message):
        """Test filtering messages by type."""
        response = client_no_auth.get("/api/v1/messages?message_type=direct")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = client_no_auth.get("/api/v1/messages?message_type=channel")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_list_messages_pagination(self, client_no_auth):
        """Test message list pagination parameters."""
        response = client_no_auth.get("/api/v1/messages?limit=25&offset=10")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 25
        assert data["offset"] == 10

    def test_list_messages_sender_name_resolution(self, client_no_auth, api_db_session):
        """Messages resolve sender name from matching pubkey_prefix."""
        sender_node = Node(
            public_key="abc123def456abc123def456abc123de",
            name="SenderNode",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(sender_node)
        api_db_session.commit()

        msg = Message(
            message_type="contact",
            pubkey_prefix="abc123def456",
            text="Hello from sender",
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add(msg)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["sender_name"] == "SenderNode"

    def test_list_messages_resolves_multiple_distinct_senders(
        self, client_no_auth, api_db_session
    ):
        """Senders with different prefixes each resolve to their own name in a
        single batched lookup."""
        api_db_session.add_all(
            [
                Node(public_key="aa" + "0" * 62, name="Alice"),
                Node(public_key="bb" + "1" * 62, name="Bob"),
            ]
        )
        api_db_session.commit()

        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                Message(
                    message_type="contact",
                    pubkey_prefix="aa" + "0" * 10,
                    text="from alice",
                    received_at=now,
                ),
                Message(
                    message_type="contact",
                    pubkey_prefix="bb" + "1" * 10,
                    text="from bob",
                    received_at=now,
                ),
            ]
        )
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        names = {item["text"]: item["sender_name"] for item in response.json()["items"]}
        assert names["from alice"] == "Alice"
        assert names["from bob"] == "Bob"

    def test_list_messages_sender_tag_name_resolution(
        self, client_no_auth, api_db_session
    ):
        """Messages resolve sender tag name from name tags."""
        sender_node = Node(
            public_key="tag123tag123tag123tag123tag123ta",
            name="OriginalName",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(sender_node)
        api_db_session.commit()

        tag = NodeTag(
            node_id=sender_node.id,
            key="name",
            value="TagSenderName",
        )
        api_db_session.add(tag)
        api_db_session.commit()

        msg = Message(
            message_type="contact",
            pubkey_prefix="tag123tag123",
            text="Hello with tag",
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add(msg)
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["sender_tag_name"] == "TagSenderName"

    def test_list_messages_with_observers(
        self, client_no_auth, api_db_session, receiver_node
    ):
        """Messages include observers list in response."""
        msg = Message(
            message_type="channel",
            channel_idx=17,
            text="Msg with observer",
            received_at=datetime.now(timezone.utc),
            observer_node_id=receiver_node.id,
        )
        api_db_session.add(msg)
        api_db_session.commit()

        if msg.event_hash:
            observer = EventObserver(
                event_type="message",
                event_hash=msg.event_hash,
                observer_node_id=receiver_node.id,
                observed_at=datetime.now(timezone.utc),
            )
            api_db_session.add(observer)
            api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert "observers" in data["items"][0]


class TestGetMessage:
    """Tests for GET /messages/{id} endpoint."""

    def test_get_message_success(self, client_no_auth, sample_message):
        """Test getting a specific message."""
        response = client_no_auth.get(f"/api/v1/messages/{sample_message.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == sample_message.text

    def test_get_message_not_found(self, client_no_auth):
        """Test getting a non-existent message."""
        response = client_no_auth.get("/api/v1/messages/nonexistent-id")
        assert response.status_code == 404

    def test_get_message_with_observers(
        self, client_no_auth, api_db_session, receiver_node
    ):
        """Get message includes observers list."""
        msg = Message(
            message_type="channel",
            channel_idx=17,
            text="Msg for get observer test",
            received_at=datetime.now(timezone.utc),
            observer_node_id=receiver_node.id,
        )
        api_db_session.add(msg)
        api_db_session.commit()

        if msg.event_hash:
            observer = EventObserver(
                event_type="message",
                event_hash=msg.event_hash,
                observer_node_id=receiver_node.id,
                observed_at=datetime.now(timezone.utc),
            )
            api_db_session.add(observer)
            api_db_session.commit()

        response = client_no_auth.get(f"/api/v1/messages/{msg.id}")
        assert response.status_code == 200
        data = response.json()
        assert "observers" in data


class TestListMessagesFilters:
    """Tests for message list query filters."""

    def test_filter_by_pubkey_prefix(self, client_no_auth, sample_message):
        """Test filtering messages by pubkey_prefix."""
        # Match
        response = client_no_auth.get("/api/v1/messages?pubkey_prefix=abc123")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # No match
        response = client_no_auth.get("/api/v1/messages?pubkey_prefix=xyz999")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_channel_idx(
        self, client_no_auth, sample_message, sample_message_with_receiver
    ):
        """Test filtering messages by channel_idx."""
        # Channel 1 should match sample_message_with_receiver
        response = client_no_auth.get("/api/v1/messages?channel_idx=17")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["channel_idx"] == 17

        # Channel 0 should return no results
        response = client_no_auth.get("/api/v1/messages?channel_idx=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_observed_by_single(
        self,
        client_no_auth,
        sample_message,
        sample_message_with_receiver,
        receiver_node,
    ):
        """Test filtering messages by a single receiver node."""
        response = client_no_auth.get(
            f"/api/v1/messages?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["text"] == sample_message_with_receiver.text

    def test_filter_by_observed_by_multiple(
        self,
        client_no_auth,
        api_db_session,
        receiver_node,
    ):
        """Test filtering messages by multiple receiver nodes."""
        # Create second receiver node
        second_receiver = Node(
            public_key="2ndmsg2ndmsg2ndmsg2ndmsg2ndmsg2n",
            name="SecondMsgObserver",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add(second_receiver)
        api_db_session.commit()

        # Create two messages, each observed by a different receiver
        msg1_hash = compute_message_hash(text="Msg from receiver A", channel_idx=17)
        msg2_hash = compute_message_hash(text="Msg from receiver B", channel_idx=17)
        msg1 = Message(
            message_type="channel",
            channel_idx=17,
            text="Msg from receiver A",
            received_at=datetime.now(timezone.utc),
            observer_node_id=receiver_node.id,
            event_hash=msg1_hash,
        )
        msg2 = Message(
            message_type="channel",
            channel_idx=17,
            text="Msg from receiver B",
            received_at=datetime.now(timezone.utc),
            observer_node_id=second_receiver.id,
            event_hash=msg2_hash,
        )
        api_db_session.add_all([msg1, msg2])
        api_db_session.commit()

        api_db_session.add_all(
            [
                EventObserver(
                    event_type="message",
                    event_hash=msg1_hash,
                    observer_node_id=receiver_node.id,
                    observed_at=datetime.now(timezone.utc),
                ),
                EventObserver(
                    event_type="message",
                    event_hash=msg2_hash,
                    observer_node_id=second_receiver.id,
                    observed_at=datetime.now(timezone.utc),
                ),
            ]
        )
        api_db_session.commit()

        # Filter by both receivers
        response = client_no_auth.get(
            f"/api/v1/messages?observed_by={receiver_node.public_key}&observed_by={second_receiver.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        # Filter by just the first receiver
        response = client_no_auth.get(
            f"/api/v1/messages?observed_by={receiver_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["text"] == "Msg from receiver A"

    def test_filter_by_observed_by_secondary_observer(
        self,
        client_no_auth,
        api_db_session,
    ):
        """Secondary observer (only in event_observers) sees the message."""
        primary_node = Node(
            public_key="p1msgp1msgp1msgp1msgp1msgp1msgp",
            name="PrimaryObserver",
            first_seen=datetime.now(timezone.utc),
        )
        secondary_node = Node(
            public_key="s1msgs1msgs1msgs1msgs1msgs1msgs1",
            name="SecondaryObserver",
            first_seen=datetime.now(timezone.utc),
        )
        api_db_session.add_all([primary_node, secondary_node])
        api_db_session.commit()

        event_hash = compute_message_hash(
            text="Secondary observer test", channel_idx=17
        )
        msg = Message(
            message_type="channel",
            channel_idx=17,
            text="Secondary observer test",
            received_at=datetime.now(timezone.utc),
            observer_node_id=primary_node.id,
            event_hash=event_hash,
        )
        api_db_session.add(msg)
        api_db_session.commit()

        api_db_session.add(
            EventObserver(
                event_type="message",
                event_hash=event_hash,
                observer_node_id=secondary_node.id,
                observed_at=datetime.now(timezone.utc),
            )
        )
        api_db_session.commit()

        response = client_no_auth.get(
            f"/api/v1/messages?observed_by={secondary_node.public_key}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["text"] == "Secondary observer test"
        assert data["items"][0]["observed_by"] == primary_node.public_key

    def test_filter_by_since(self, client_no_auth, api_db_session):
        """Test filtering messages by since timestamp."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create an old message
        old_msg = Message(
            message_type="direct",
            pubkey_prefix="old123",
            text="Old message",
            received_at=old_time,
        )
        api_db_session.add(old_msg)
        api_db_session.commit()

        # Filter since yesterday - should not include old message
        since = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/messages?since={since}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_filter_by_until(self, client_no_auth, api_db_session):
        """Test filtering messages by until timestamp."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=7)

        # Create an old message
        old_msg = Message(
            message_type="direct",
            pubkey_prefix="old456",
            text="Old message for until",
            received_at=old_time,
        )
        api_db_session.add(old_msg)
        api_db_session.commit()

        # Filter until 5 days ago - should include old message
        until = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        response = client_no_auth.get(f"/api/v1/messages?until={until}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["text"] == "Old message for until"

    def test_filter_by_search(self, client_no_auth, sample_message):
        """Test filtering messages by text search."""
        # Match
        response = client_no_auth.get("/api/v1/messages?search=Hello")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # Case insensitive match
        response = client_no_auth.get("/api/v1/messages?search=hello")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # No match
        response = client_no_auth.get("/api/v1/messages?search=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0


class TestMessageSort:
    """Tests for message list sort parameters."""

    def test_sort_by_time_default(self, client_no_auth, api_db_session):
        """Default sort is received_at DESC."""
        now = datetime.now(timezone.utc)
        msg_old = Message(
            message_type="direct",
            pubkey_prefix="aa",
            text="Old msg",
            received_at=now - timedelta(hours=1),
        )
        msg_new = Message(
            message_type="direct",
            pubkey_prefix="bb",
            text="New msg",
            received_at=now,
        )
        api_db_session.add_all([msg_old, msg_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "New msg"
        assert items[1]["text"] == "Old msg"

    def test_sort_by_type(self, client_no_auth, api_db_session):
        """sort=type&order=asc sorts by message_type."""
        now = datetime.now(timezone.utc)
        msg_ch = Message(
            message_type="channel",
            channel_idx=17,
            text="Channel msg",
            received_at=now,
        )
        msg_ct = Message(
            message_type="contact",
            text="Contact msg",
            received_at=now,
        )
        api_db_session.add_all([msg_ch, msg_ct])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=type&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["message_type"] == "channel"
        assert items[1]["message_type"] == "contact"

    def test_sort_by_from(self, client_no_auth, api_db_session):
        """sort=from&order=asc sorts by pubkey_prefix."""
        now = datetime.now(timezone.utc)
        msg_b = Message(
            message_type="direct",
            pubkey_prefix="bb_prefix",
            text="From B",
            received_at=now,
        )
        msg_a = Message(
            message_type="direct",
            pubkey_prefix="aa_prefix",
            text="From A",
            received_at=now,
        )
        api_db_session.add_all([msg_b, msg_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=from&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "From A"
        assert items[1]["text"] == "From B"

    def test_sort_by_message(self, client_no_auth, api_db_session):
        """sort=message&order=asc sorts by text."""
        now = datetime.now(timezone.utc)
        msg_b = Message(
            message_type="direct",
            text="Zebra message",
            received_at=now,
        )
        msg_a = Message(
            message_type="direct",
            text="Alpha message",
            received_at=now,
        )
        api_db_session.add_all([msg_b, msg_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=message&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "Alpha message"
        assert items[1]["text"] == "Zebra message"

    def test_sort_by_type_desc(self, client_no_auth, api_db_session):
        """sort=type&order=desc sorts by message_type descending."""
        now = datetime.now(timezone.utc)
        msg_ch = Message(
            message_type="channel",
            channel_idx=17,
            text="Channel msg",
            received_at=now,
        )
        msg_ct = Message(
            message_type="contact",
            text="Contact msg",
            received_at=now,
        )
        api_db_session.add_all([msg_ch, msg_ct])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=type&order=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["message_type"] == "contact"
        assert items[1]["message_type"] == "channel"

    def test_sort_by_from_desc(self, client_no_auth, api_db_session):
        """sort=from&order=desc sorts by pubkey_prefix descending."""
        now = datetime.now(timezone.utc)
        msg_b = Message(
            message_type="direct",
            pubkey_prefix="bb_prefix",
            text="From B",
            received_at=now,
        )
        msg_a = Message(
            message_type="direct",
            pubkey_prefix="aa_prefix",
            text="From A",
            received_at=now,
        )
        api_db_session.add_all([msg_b, msg_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=from&order=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "From B"
        assert items[1]["text"] == "From A"

    def test_sort_by_message_desc(self, client_no_auth, api_db_session):
        """sort=message&order=desc sorts by text descending."""
        now = datetime.now(timezone.utc)
        msg_b = Message(
            message_type="direct",
            text="Zebra message",
            received_at=now,
        )
        msg_a = Message(
            message_type="direct",
            text="Alpha message",
            received_at=now,
        )
        api_db_session.add_all([msg_b, msg_a])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=message&order=desc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "Zebra message"
        assert items[1]["text"] == "Alpha message"

    def test_sort_by_time_asc(self, client_no_auth, api_db_session):
        """sort=time&order=asc sorts by received_at ascending."""
        now = datetime.now(timezone.utc)
        msg_old = Message(
            message_type="direct",
            pubkey_prefix="aa",
            text="Old msg",
            received_at=now - timedelta(hours=1),
        )
        msg_new = Message(
            message_type="direct",
            pubkey_prefix="bb",
            text="New msg",
            received_at=now,
        )
        api_db_session.add_all([msg_old, msg_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=time&order=asc")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "Old msg"
        assert items[1]["text"] == "New msg"

    def test_sort_invalid_ignored(self, client_no_auth, api_db_session):
        """Invalid sort value falls back to default (time desc)."""
        now = datetime.now(timezone.utc)
        msg_old = Message(
            message_type="direct",
            text="Old",
            received_at=now - timedelta(hours=1),
        )
        msg_new = Message(
            message_type="direct",
            text="New",
            received_at=now,
        )
        api_db_session.add_all([msg_old, msg_new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/messages?sort=invalid_column")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["text"] == "New"


class TestMessageChannelVisibility:
    """Tests for channel visibility filtering on messages."""

    @pytest.fixture
    def messages_with_visibility(self, api_db_session):
        """Create messages on public and admin channels."""
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
            text="Community channel message",
            received_at=datetime.now(timezone.utc),
        )
        adm_msg = Message(
            message_type="channel",
            channel_idx=adm_idx,
            text="Admin channel message",
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

        return pub_msg, adm_msg, direct_msg

    def test_anonymous_sees_only_community_channel_messages(
        self, client_no_auth, messages_with_visibility
    ):
        """Anonymous users see community channel and direct messages only."""
        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        texts = {item["text"] for item in data["items"]}
        assert "Community channel message" in texts
        assert "Direct message" in texts
        assert "Admin channel message" not in texts

    def test_admin_sees_all_channel_messages(
        self, client_no_auth, messages_with_visibility
    ):
        """Admin users see all channel messages."""
        response = client_no_auth.get(
            "/api/v1/messages",
            headers={"X-User-Roles": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        texts = {item["text"] for item in data["items"]}
        assert "Community channel message" in texts
        assert "Admin channel message" in texts
        assert "Direct message" in texts

    def test_get_message_hidden_channel_returns_404(
        self, client_no_auth, messages_with_visibility
    ):
        """Getting a message on a hidden channel returns 404."""
        pub_msg, adm_msg, direct_msg = messages_with_visibility

        response = client_no_auth.get(f"/api/v1/messages/{adm_msg.id}")
        assert response.status_code == 404

    def test_get_message_hidden_channel_visible_to_admin(
        self, client_no_auth, messages_with_visibility
    ):
        """Admin can get a message on an admin channel."""
        pub_msg, adm_msg, direct_msg = messages_with_visibility

        response = client_no_auth.get(
            f"/api/v1/messages/{adm_msg.id}",
            headers={"X-User-Roles": "admin"},
        )
        assert response.status_code == 200
        assert response.json()["text"] == "Admin channel message"

    def test_get_message_community_channel_visible(
        self, client_no_auth, messages_with_visibility
    ):
        """Anonymous can get a message on a community channel."""
        pub_msg, adm_msg, direct_msg = messages_with_visibility

        response = client_no_auth.get(f"/api/v1/messages/{pub_msg.id}")
        assert response.status_code == 200
        assert response.json()["text"] == "Community channel message"

    def test_direct_messages_always_visible(
        self, client_no_auth, messages_with_visibility
    ):
        """Direct messages are always visible regardless of channel visibility."""
        pub_msg, adm_msg, direct_msg = messages_with_visibility

        response = client_no_auth.get(f"/api/v1/messages/{direct_msg.id}")
        assert response.status_code == 200
        assert response.json()["text"] == "Direct message"

    def test_get_message_channel_null_idx_not_filtered(
        self, client_no_auth, api_db_session
    ):
        """Channel message with channel_idx=None bypasses visibility filter."""
        msg = Message(
            message_type="channel",
            channel_idx=None,
            text="Channel msg no idx",
            received_at=datetime.now(timezone.utc),
        )
        api_db_session.add(msg)
        api_db_session.commit()

        response = client_no_auth.get(f"/api/v1/messages/{msg.id}")
        assert response.status_code == 200
        assert response.json()["text"] == "Channel msg no idx"

    def test_get_message_no_observers_without_event_hash(
        self, client_no_auth, api_db_session
    ):
        """Message without event_hash returns empty observers list."""
        msg = Message(
            message_type="direct",
            pubkey_prefix="nohash1",
            text="No hash msg",
            received_at=datetime.now(timezone.utc),
            event_hash=None,
        )
        api_db_session.add(msg)
        api_db_session.commit()

        response = client_no_auth.get(f"/api/v1/messages/{msg.id}")
        assert response.status_code == 200
        assert response.json()["observers"] == []


class TestSpamFiltering:
    """Tests for spam-score hide/show behaviour (GET /messages)."""

    @staticmethod
    def _seed(api_db_session):
        """Two clean messages + one likely-spam message."""
        now = datetime.now(timezone.utc)
        api_db_session.add_all(
            [
                Message(
                    message_type="direct",
                    pubkey_prefix="clean1",
                    text="clean one",
                    received_at=now,
                    spam_score=0.0,
                ),
                Message(
                    message_type="direct",
                    pubkey_prefix="unscor1",
                    text="unscored",
                    received_at=now,
                    spam_score=None,
                ),
                Message(
                    message_type="direct",
                    pubkey_prefix="spam1",
                    text="buy now buy now",
                    received_at=now,
                    spam_score=0.95,
                ),
            ]
        )
        api_db_session.commit()

    def test_spam_hidden_by_default(self, client_spam, api_db_session):
        """With detection on, high-score rows are hidden by default."""
        self._seed(api_db_session)
        data = client_spam.get("/api/v1/messages").json()
        texts = {item["text"] for item in data["items"]}
        assert "buy now buy now" not in texts
        assert "clean one" in texts
        assert "unscored" in texts  # null score is never hidden
        assert data["total"] == 2

    def test_include_spam_shows_all(self, client_spam, api_db_session):
        """include_spam=true returns the flagged row with its score."""
        self._seed(api_db_session)
        data = client_spam.get("/api/v1/messages?include_spam=true").json()
        texts = {item["text"] for item in data["items"]}
        assert "buy now buy now" in texts
        assert data["total"] == 3
        spam_item = next(i for i in data["items"] if i["text"] == "buy now buy now")
        assert spam_item["spam_score"] == 0.95

    def test_master_switch_off_returns_all(self, client_no_auth, api_db_session):
        """With detection disabled, even high-score rows are returned."""
        self._seed(api_db_session)
        data = client_no_auth.get("/api/v1/messages").json()
        texts = {item["text"] for item in data["items"]}
        assert "buy now buy now" in texts
        assert data["total"] == 3

    def test_spam_score_in_response(self, client_no_auth, api_db_session):
        """spam_score is surfaced on the message payload."""
        self._seed(api_db_session)
        data = client_no_auth.get("/api/v1/messages").json()
        clean = next(i for i in data["items"] if i["text"] == "clean one")
        assert clean["spam_score"] == 0.0
