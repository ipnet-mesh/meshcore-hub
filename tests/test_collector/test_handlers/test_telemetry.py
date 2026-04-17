"""Tests for telemetry handler."""

from sqlalchemy import select

from meshcore_hub.common.models import EventObserver, Node, Telemetry
from meshcore_hub.collector.handlers.telemetry import handle_telemetry


class TestHandleTelemetry:
    """Tests for handle_telemetry."""

    def test_creates_telemetry_record(self, db_manager, db_session):
        """Test that telemetry records are stored."""
        payload = {
            "node_public_key": "b" * 64,
            "parsed_data": {
                "temperature": 22.5,
                "humidity": 65,
                "battery": 3.8,
            },
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)

        # Check telemetry was created
        telemetry = db_session.execute(select(Telemetry)).scalar_one_or_none()

        assert telemetry is not None
        assert telemetry.node_public_key == "b" * 64
        assert telemetry.parsed_data["temperature"] == 22.5
        assert telemetry.parsed_data["humidity"] == 65
        assert telemetry.parsed_data["battery"] == 3.8

    def test_creates_reporting_node(self, db_manager, db_session):
        """Test that reporting node is created if needed."""
        payload = {
            "node_public_key": "b" * 64,
            "parsed_data": {"temperature": 20.0},
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)

        # Check node was created
        node = db_session.execute(
            select(Node).where(Node.public_key == "b" * 64)
        ).scalar_one_or_none()

        assert node is not None

    def test_handles_missing_node_public_key(self, db_manager, db_session):
        """Test that missing node_public_key is handled gracefully."""
        payload = {
            "parsed_data": {"temperature": 20.0},
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)

        # No telemetry should be created
        records = db_session.execute(select(Telemetry)).scalars().all()
        assert len(records) == 0

    def test_duplicate_telemetry_adds_observer(self, db_manager, db_session):
        """Duplicate telemetry adds receiver to observers."""
        payload = {
            "node_public_key": "b" * 64,
            "parsed_data": {"temperature": 20.0},
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)
        handle_telemetry("c" * 64, "telemetry_response", payload, db_manager)

        records = db_session.execute(select(Telemetry)).scalars().all()
        assert len(records) == 1

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 2

    def test_lpp_data_as_hex_string(self, db_manager, db_session):
        """lpp_data as hex string is converted to bytes."""
        payload = {
            "node_public_key": "b" * 64,
            "parsed_data": {"battery": 85},
            "lpp_data": "deadbeef",
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)

        telemetry = db_session.execute(select(Telemetry)).scalar_one()
        assert telemetry.lpp_data == bytes.fromhex("deadbeef")

    def test_lpp_data_as_list(self, db_manager, db_session):
        """lpp_data as list of ints is converted to bytes."""
        payload = {
            "node_public_key": "b" * 64,
            "parsed_data": {"battery": 85},
            "lpp_data": [1, 2, 3],
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)

        telemetry = db_session.execute(select(Telemetry)).scalar_one()
        assert telemetry.lpp_data == b"\x01\x02\x03"

    def test_creates_receiver_node(self, db_manager, db_session):
        """Receiver node is created if it does not exist."""
        payload = {
            "node_public_key": "b" * 64,
            "parsed_data": {"temperature": 20.0},
        }

        receiver_pk = "e" * 64
        handle_telemetry(receiver_pk, "telemetry_response", payload, db_manager)

        receiver = db_session.execute(
            select(Node).where(Node.public_key == receiver_pk)
        ).scalar_one_or_none()
        assert receiver is not None

    def test_no_parsed_data_still_creates_record(self, db_manager, db_session):
        """Telemetry without parsed_data is still stored."""
        payload = {
            "node_public_key": "b" * 64,
        }

        handle_telemetry("a" * 64, "telemetry_response", payload, db_manager)

        telemetry = db_session.execute(select(Telemetry)).scalar_one()
        assert telemetry.node_public_key == "b" * 64
