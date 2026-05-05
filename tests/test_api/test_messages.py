"""Tests for message API routes."""

from datetime import datetime, timedelta, timezone

from meshcore_hub.common.models import EventObserver, Message, Node, NodeTag


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
            channel_idx=1,
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
            channel_idx=1,
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
        response = client_no_auth.get("/api/v1/messages?channel_idx=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["channel_idx"] == 1

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
        msg1 = Message(
            message_type="channel",
            channel_idx=1,
            text="Msg from receiver A",
            received_at=datetime.now(timezone.utc),
            observer_node_id=receiver_node.id,
        )
        msg2 = Message(
            message_type="channel",
            channel_idx=2,
            text="Msg from receiver B",
            received_at=datetime.now(timezone.utc),
            observer_node_id=second_receiver.id,
        )
        api_db_session.add_all([msg1, msg2])
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
            channel_idx=1,
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
