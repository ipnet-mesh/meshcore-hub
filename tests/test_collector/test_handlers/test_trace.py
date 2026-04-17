"""Tests for trace data handler."""

from sqlalchemy import select

from meshcore_hub.common.models import EventObserver, Node, TracePath
from meshcore_hub.collector.handlers.trace import handle_trace_data


class TestHandleTraceData:
    """Tests for handle_trace_data."""

    def test_creates_trace_path_record(self, db_manager, db_session):
        """Test that trace path records are stored."""
        payload = {
            "initiator_tag": 12345,
            "path_len": 3,
            "flags": 0,
            "path_hashes": ["AA", "BB", "CC"],
            "snr_values": [10.5, 8.0, 6.25],
            "hop_count": 3,
        }

        handle_trace_data("a" * 64, "trace_data", payload, db_manager)

        trace = db_session.execute(select(TracePath)).scalar_one_or_none()
        assert trace is not None
        assert trace.initiator_tag == 12345
        assert trace.hop_count == 3
        assert trace.path_hashes == ["AA", "BB", "CC"]
        assert trace.snr_values == [10.5, 8.0, 6.25]

    def test_handles_missing_initiator_tag(self, db_manager, db_session):
        """Test that missing initiator_tag is handled gracefully."""
        payload = {
            "path_hashes": ["AA"],
        }

        handle_trace_data("a" * 64, "trace_data", payload, db_manager)

        traces = db_session.execute(select(TracePath)).scalars().all()
        assert len(traces) == 0

    def test_duplicate_trace_adds_observer(self, db_manager, db_session):
        """Duplicate trace adds receiver to observers instead of new record."""
        payload = {
            "initiator_tag": 99999,
            "path_hashes": ["AA", "BB"],
            "hop_count": 2,
        }

        handle_trace_data("a" * 64, "trace_data", payload, db_manager)

        traces = db_session.execute(select(TracePath)).scalars().all()
        assert len(traces) == 1

        handle_trace_data("b" * 64, "trace_data", payload, db_manager)

        traces = db_session.execute(select(TracePath)).scalars().all()
        assert len(traces) == 1

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 2

    def test_creates_receiver_node(self, db_manager, db_session):
        """Receiver node is created if it does not exist."""
        payload = {
            "initiator_tag": 55555,
            "hop_count": 1,
        }

        receiver_pk = "e" * 64
        handle_trace_data(receiver_pk, "trace_data", payload, db_manager)

        receiver = db_session.execute(
            select(Node).where(Node.public_key == receiver_pk)
        ).scalar_one_or_none()
        assert receiver is not None

    def test_creates_first_observer(self, db_manager, db_session):
        """First trace event creates an observer entry."""
        payload = {
            "initiator_tag": 77777,
            "hop_count": 2,
        }

        handle_trace_data("a" * 64, "trace_data", payload, db_manager)

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 1
        assert observers[0].event_type == "trace"
