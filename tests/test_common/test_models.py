"""Tests for database models."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meshcore_hub.common.models import (
    Base,
    Node,
    NodeTag,
    Message,
    Advertisement,
    TracePath,
    Telemetry,
    EventLog,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


class TestNodeModel:
    """Tests for Node model."""

    def test_create_node(self, db_session) -> None:
        """Test creating a node."""
        node = Node(
            public_key="a" * 64,
            name="Test Node",
            adv_type="chat",
            flags=218,
        )
        db_session.add(node)
        db_session.commit()

        assert node.id is not None
        assert node.public_key == "a" * 64
        assert node.name == "Test Node"
        assert node.adv_type == "chat"
        assert node.flags == 218

    def test_node_tags_relationship(self, db_session) -> None:
        """Test node-tag relationship."""
        node = Node(public_key="b" * 64, name="Tagged Node")
        tag = NodeTag(key="location", value="51.5,-0.1", value_type="coordinate")
        node.tags.append(tag)

        db_session.add(node)
        db_session.commit()

        assert len(node.tags) == 1
        assert node.tags[0].key == "location"


class TestMessageModel:
    """Tests for Message model."""

    def test_create_contact_message(self, db_session) -> None:
        """Test creating a contact message."""
        message = Message(
            message_type="contact",
            pubkey_prefix="01ab2186c4d5",
            text="Hello World!",
            path_len=3,
            snr=15.5,
        )
        db_session.add(message)
        db_session.commit()

        assert message.id is not None
        assert message.message_type == "contact"
        assert message.text == "Hello World!"

    def test_create_channel_message(self, db_session) -> None:
        """Test creating a channel message."""
        message = Message(
            message_type="channel",
            channel_idx=4,
            text="Channel broadcast",
            path_len=10,
        )
        db_session.add(message)
        db_session.commit()

        assert message.channel_idx == 4
        assert message.message_type == "channel"


class TestAdvertisementModel:
    """Tests for Advertisement model."""

    def test_create_advertisement(self, db_session) -> None:
        """Test creating an advertisement."""
        ad = Advertisement(
            public_key="c" * 64,
            name="Repeater-01",
            adv_type="repeater",
            flags=128,
        )
        db_session.add(ad)
        db_session.commit()

        assert ad.id is not None
        assert ad.public_key == "c" * 64
        assert ad.adv_type == "repeater"


class TestTracePathModel:
    """Tests for TracePath model."""

    def test_create_trace_path(self, db_session) -> None:
        """Test creating a trace path."""
        trace = TracePath(
            initiator_tag=123456789,
            path_len=3,
            path_hashes=["4a", "b3", "fa"],
            snr_values=[25.3, 18.7, 12.4],
            hop_count=3,
        )
        db_session.add(trace)
        db_session.commit()

        assert trace.id is not None
        assert trace.initiator_tag == 123456789
        assert trace.path_hashes == ["4a", "b3", "fa"]


class TestTelemetryModel:
    """Tests for Telemetry model."""

    def test_create_telemetry(self, db_session) -> None:
        """Test creating a telemetry record."""
        telemetry = Telemetry(
            node_public_key="d" * 64,
            parsed_data={
                "temperature": 22.5,
                "humidity": 65,
                "battery": 3.8,
            },
        )
        db_session.add(telemetry)
        db_session.commit()

        assert telemetry.id is not None
        assert telemetry.parsed_data["temperature"] == 22.5


class TestEventLogModel:
    """Tests for EventLog model."""

    def test_create_event_log(self, db_session) -> None:
        """Test creating an event log entry."""
        event = EventLog(
            event_type="BATTERY",
            payload={
                "battery_voltage": 3.8,
                "battery_percentage": 75,
            },
        )
        db_session.add(event)
        db_session.commit()

        assert event.id is not None
        assert event.event_type == "BATTERY"
        assert event.payload["battery_percentage"] == 75
