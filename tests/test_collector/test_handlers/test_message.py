"""Tests for message handlers."""

from sqlalchemy import select

from meshcore_hub.common.models import EventObserver, Message, Node
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
            "snr": 15.5,
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

    def test_duplicate_contact_message_adds_observer(self, db_manager, db_session):
        """Duplicate contact message adds receiver to observers."""
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "text": "Hello!",
        }

        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)
        handle_contact_message("b" * 64, "contact_msg_recv", payload, db_manager)

        msgs = db_session.execute(select(Message)).scalars().all()
        assert len(msgs) == 1

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 2

    def test_contact_message_sender_timestamp(self, db_manager, db_session):
        """Sender timestamp is parsed and stored."""
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "text": "Hello!",
            "sender_timestamp": 1771695860,
        }

        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)

        msg = db_session.execute(select(Message)).scalar_one()
        assert msg.sender_timestamp is not None
        assert msg.sender_timestamp.year == 2026

    def test_contact_message_snr_lowercase_key(self, db_manager, db_session):
        """SNR is read from lowercase 'snr' key when uppercase is absent."""
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "text": "Hello!",
            "snr": 7.5,
        }

        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)

        msg = db_session.execute(select(Message)).scalar_one()
        assert msg.snr == 7.5


class TestHandleChannelMessage:
    """Tests for handle_channel_message."""

    def test_creates_channel_message(self, db_manager, db_session):
        """Test that channel messages are stored."""
        payload = {
            "channel_idx": 4,
            "text": "Channel broadcast",
            "path_len": 10,
            "snr": 8.5,
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

    def test_duplicate_channel_message_adds_observer(self, db_manager, db_session):
        """Duplicate channel message adds receiver to observers."""
        payload = {
            "channel_idx": 4,
            "text": "Channel msg",
        }

        handle_channel_message("a" * 64, "channel_msg_recv", payload, db_manager)
        handle_channel_message("b" * 64, "channel_msg_recv", payload, db_manager)

        msgs = db_session.execute(select(Message)).scalars().all()
        assert len(msgs) == 1

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 2

    def test_channel_message_signature_stored(self, db_manager, db_session):
        """Signature field is stored when provided."""
        payload = {
            "channel_idx": 4,
            "text": "Signed msg",
            "signature": "abcdef1234567890",
        }

        handle_channel_message("a" * 64, "channel_msg_recv", payload, db_manager)

        msg = db_session.execute(select(Message)).scalar_one()
        assert msg.signature == "abcdef1234567890"

    def test_message_handler_passes_path_len_to_observer(self, db_manager, db_session):
        """Message handler passes path_len to add_event_observer."""
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "text": "Path test",
            "path_len": 5,
            "snr": 10.0,
        }

        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)

        observer = db_session.execute(select(EventObserver)).scalar_one_or_none()
        assert observer is not None
        assert observer.path_len == 5
        assert observer.snr == 10.0
