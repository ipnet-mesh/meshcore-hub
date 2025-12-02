"""Tests for message handlers."""

import pytest
from sqlalchemy import select

from meshcore_hub.common.models import Message, Node
from meshcore_hub.collector.handlers.message import (
    handle_contact_message,
    handle_channel_message,
)


class TestHandleContactMessage:
    """Tests for handle_contact_message."""

    def test_creates_contact_message(self, db_manager, db_session):
        """Test that contact messages are stored."""
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "text": "Hello World!",
            "path_len": 3,
            "SNR": 15.5,
        }

        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)

        # Check message was created
        msg = db_session.execute(select(Message)).scalar_one_or_none()

        assert msg is not None
        assert msg.message_type == "contact"
        assert msg.pubkey_prefix == "01ab2186c4d5"
        assert msg.text == "Hello World!"
        assert msg.path_len == 3
        assert msg.snr == 15.5

    def test_handles_missing_text(self, db_manager, db_session):
        """Test that missing text is handled gracefully."""
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "path_len": 3,
        }

        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)

        # No message should be created
        msgs = db_session.execute(select(Message)).scalars().all()
        assert len(msgs) == 0


class TestHandleChannelMessage:
    """Tests for handle_channel_message."""

    def test_creates_channel_message(self, db_manager, db_session):
        """Test that channel messages are stored."""
        payload = {
            "channel_idx": 4,
            "text": "Channel broadcast",
            "path_len": 10,
            "SNR": 8.5,
        }

        handle_channel_message("a" * 64, "channel_msg_recv", payload, db_manager)

        # Check message was created
        msg = db_session.execute(select(Message)).scalar_one_or_none()

        assert msg is not None
        assert msg.message_type == "channel"
        assert msg.channel_idx == 4
        assert msg.text == "Channel broadcast"
        assert msg.path_len == 10
        assert msg.snr == 8.5

    def test_creates_receiver_node_if_needed(self, db_manager, db_session):
        """Test that receiver node is created if it doesn't exist."""
        payload = {
            "channel_idx": 4,
            "text": "Test message",
        }

        handle_channel_message("a" * 64, "channel_msg_recv", payload, db_manager)

        # Check receiver node was created
        node = db_session.execute(
            select(Node).where(Node.public_key == "a" * 64)
        ).scalar_one_or_none()

        assert node is not None
