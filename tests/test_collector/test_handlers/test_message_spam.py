"""Tests for spam scoring wired into the message handler."""

from sqlalchemy import select

import meshcore_hub.collector.handlers.message as handler_module
from meshcore_hub.collector.handlers.message import (
    handle_channel_message,
    handle_contact_message,
)
from meshcore_hub.collector.spam import SpamConfig
from meshcore_hub.common.models import Message

ENABLED_CFG = SpamConfig(
    enabled=True,
    window_seconds=300,
    path_hops=3,
    min_path_hops=5,
    path_threshold=5,
    name_threshold=5,
    weight_path=0.7,
    weight_name=0.3,
    score_threshold=0.6,
    rescore_interval_seconds=120,
)


def _channel_payload(i, sender, *, path_len=6, path=None):
    return {
        "channel_idx": 0,
        "text": "buy now",
        "sender_name": sender,
        "path_len": path_len,
        "path_hashes": (
            path if path is not None else ["AA", "BB", "CC", "DD", "EE", "FF"]
        ),
        # Vary sender_timestamp so the event-hash dedup does not collapse the
        # burst into a single row (text/channel/timestamp drive the hash).
        "sender_timestamp": 1732820000 + i,
    }


def _enable_spam(monkeypatch, cfg=ENABLED_CFG):
    monkeypatch.setattr(handler_module, "get_spam_config", lambda: cfg)


class TestHandlerSpamDisabled:
    def test_score_columns_null_when_disabled(self, db_manager, db_session):
        """Default (feature off) leaves the spam columns null, as before."""
        handle_channel_message(
            "a" * 64, "channel_msg_recv", _channel_payload(0, "bob1"), db_manager
        )
        msg = db_session.execute(select(Message)).scalar_one()
        assert msg.spam_score is None
        assert msg.path_prefix is None
        assert msg.sender_normalized is None


class TestHandlerSpamEnabled:
    def test_populates_signals_and_score(self, db_manager, db_session, monkeypatch):
        _enable_spam(monkeypatch)
        handle_channel_message(
            "a" * 64, "channel_msg_recv", _channel_payload(0, "bob1"), db_manager
        )
        msg = db_session.execute(select(Message)).scalar_one()
        assert msg.path_prefix == "AA,BB,CC"
        assert msg.sender_normalized == "bob"
        # First-ever message: no priors -> score 0.0 (not null).
        assert msg.spam_score == 0.0

    def test_burst_later_rows_flagged(self, db_manager, db_session, monkeypatch):
        _enable_spam(monkeypatch)
        # Rotating bob1..bob6 all normalize to "bob" on the same path.
        for i in range(6):
            handle_channel_message(
                "a" * 64,
                "channel_msg_recv",
                _channel_payload(i, f"bob{i + 1}"),
                db_manager,
            )

        msgs = db_session.execute(select(Message)).scalars().all()
        assert len(msgs) == 6
        assert all(m.sender_normalized == "bob" for m in msgs)
        # The last-inserted row saw 5 priors -> path+name saturate near threshold.
        latest = max(msgs, key=lambda m: m.sender_timestamp)
        assert latest.spam_score >= ENABLED_CFG.score_threshold

    def test_contact_message_scored_and_logged(
        self, db_manager, db_session, monkeypatch
    ):
        """Contact messages are scored too (covers the contact log branch)."""
        _enable_spam(monkeypatch)
        payload = {
            "pubkey_prefix": "01ab2186c4d5",
            "text": "buy now",
            "sender_name": "bob1",
            "path_len": 6,
            "path_hashes": ["AA", "BB", "CC", "DD", "EE", "FF"],
        }
        handle_contact_message("a" * 64, "contact_msg_recv", payload, db_manager)

        msg = db_session.execute(select(Message)).scalar_one()
        assert msg.message_type == "contact"
        assert msg.sender_normalized == "bob"
        assert msg.path_prefix == "AA,BB,CC"
        assert msg.spam_score == 0.0

    def test_short_path_stores_null_prefix(self, db_manager, db_session, monkeypatch):
        _enable_spam(monkeypatch)
        handle_channel_message(
            "a" * 64,
            "channel_msg_recv",
            _channel_payload(0, "bob1", path_len=2, path=["AA", "BB"]),
            db_manager,
        )
        msg = db_session.execute(select(Message)).scalar_one()
        # Below the gate: path_prefix null, but sender still normalized.
        assert msg.path_prefix is None
        assert msg.sender_normalized == "bob"
        assert msg.spam_score == 0.0
