"""Tests for telemetry handler."""

import pytest
from sqlalchemy import select

from meshcore_hub.common.models import Node, Telemetry
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
