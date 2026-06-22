"""Tests for the spam scoring module (collector/spam.py).

The DB-touching tests run against whichever backend the shared ``db_manager``
fixture is configured for (SQLite by default, Postgres when
``TEST_DATABASE_BACKEND=postgres``).
"""

from datetime import datetime, timedelta, timezone

import pytest

from meshcore_hub.collector.spam import (
    SpamConfig,
    compute_path_prefix,
    normalize_sender,
    rescore_recent,
    score_message,
)
from meshcore_hub.common.models import Message

CFG = SpamConfig(
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


# --------------------------------------------------------------------------- #
# Pure helpers (no DB)
# --------------------------------------------------------------------------- #


class TestNormalizeSender:
    def test_strips_trailing_digits(self):
        assert normalize_sender("bob17") == "bob"

    def test_strips_trailing_digit_and_space(self):
        assert normalize_sender("Bob 2") == "bob"

    def test_lowercases(self):
        assert normalize_sender("ALICE") == "alice"

    def test_none_for_empty(self):
        assert normalize_sender("") is None
        assert normalize_sender(None) is None

    def test_none_for_all_digits(self):
        assert normalize_sender("12345") is None

    def test_keeps_interior_digits(self):
        assert normalize_sender("c3po") == "c3po"


class TestComputePathPrefix:
    def test_joins_first_n_hops(self):
        assert compute_path_prefix(["AA", "BB", "CC", "DD"], 3) == "AA,BB,CC"

    def test_shorter_than_hops(self):
        assert compute_path_prefix(["AA"], 3) == "AA"

    def test_none_for_empty(self):
        assert compute_path_prefix(None, 3) is None
        assert compute_path_prefix([], 3) is None

    def test_none_for_zero_hops(self):
        assert compute_path_prefix(["AA", "BB"], 0) is None


# --------------------------------------------------------------------------- #
# DB-touching scorer
# --------------------------------------------------------------------------- #


def _make_message(received_at, *, path_prefix, sender_normalized, path_len=6):
    return Message(
        message_type="channel",
        channel_idx=0,
        text="test",
        path_len=path_len,
        path_prefix=path_prefix,
        sender_normalized=sender_normalized,
        received_at=received_at,
    )


class TestScoreMessage:
    def test_first_message_scores_zero(self, db_session):
        now = datetime.now(timezone.utc)
        result = score_message(
            db_session,
            path_prefix="AA,BB,CC",
            sender_normalized="bob",
            path_len=6,
            received_at=now,
            cfg=CFG,
        )
        assert result.score == 0.0
        assert result.path_count == 0
        assert result.name_count == 0

    def test_identical_burst_crosses_threshold(self, db_session):
        now = datetime.now(timezone.utc)
        # Seed a burst of identical path+sender priors within the window.
        for i in range(6):
            db_session.add(
                _make_message(
                    now - timedelta(seconds=10 + i),
                    path_prefix="AA,BB,CC",
                    sender_normalized="bob",
                )
            )
        db_session.commit()

        result = score_message(
            db_session,
            path_prefix="AA,BB,CC",
            sender_normalized="bob",
            path_len=6,
            received_at=now,
            cfg=CFG,
        )
        # path saturates (>=5) -> 0.7, name saturates -> 0.3 => 1.0
        assert result.score >= CFG.score_threshold
        assert result.path_count == 6
        assert result.name_count == 6

    def test_busy_path_diverse_senders_not_flagged(self, db_session):
        """Many different senders on the same path should not score high."""
        now = datetime.now(timezone.utc)
        for i in range(8):
            db_session.add(
                _make_message(
                    now - timedelta(seconds=5 + i),
                    path_prefix="AA,BB,CC",
                    sender_normalized=f"user{i}",  # already normalized, distinct
                )
            )
        db_session.commit()

        result = score_message(
            db_session,
            path_prefix="AA,BB,CC",
            sender_normalized="freshname",
            path_len=6,
            received_at=now,
            cfg=CFG,
        )
        # Joint (path, sender) count is 0 for this new sender; name count is 0.
        assert result.path_count == 0
        assert result.name_count == 0
        assert result.score == 0.0

    def test_outside_window_not_counted(self, db_session):
        now = datetime.now(timezone.utc)
        for i in range(6):
            db_session.add(
                _make_message(
                    now - timedelta(seconds=400 + i),  # older than 300s window
                    path_prefix="AA,BB,CC",
                    sender_normalized="bob",
                )
            )
        db_session.commit()

        result = score_message(
            db_session,
            path_prefix="AA,BB,CC",
            sender_normalized="bob",
            path_len=6,
            received_at=now,
            cfg=CFG,
        )
        assert result.score == 0.0

    def test_short_path_relies_on_name_only(self, db_session):
        """Below the min-path gate the path signal is off; name stands alone.

        Name-only must be able to cross the threshold, otherwise zero-hop / local
        spam (no usable path) could never be flagged.
        """
        now = datetime.now(timezone.utc)
        # Priors share the sender but were stored with null path_prefix (short).
        for i in range(6):
            db_session.add(
                _make_message(
                    now - timedelta(seconds=5 + i),
                    path_prefix=None,
                    sender_normalized="bob",
                    path_len=2,
                )
            )
        db_session.commit()

        result = score_message(
            db_session,
            path_prefix=None,  # gated to null by the handler for short paths
            sender_normalized="bob",
            path_len=2,
            received_at=now,
            cfg=CFG,
        )
        # path disabled -> name signal at full weight; saturated count -> 1.0
        assert result.path_count == 0
        assert result.name_count == 6
        assert result.score == pytest.approx(1.0)
        assert result.score >= CFG.score_threshold

    def test_short_path_name_scales_below_saturation(self, db_session):
        """Name-only score scales with count and crosses threshold at name_thr."""
        now = datetime.now(timezone.utc)
        # 3 priors against name_threshold=5 -> 0.6 (== threshold).
        for i in range(3):
            db_session.add(
                _make_message(
                    now - timedelta(seconds=5 + i),
                    path_prefix=None,
                    sender_normalized="bob",
                    path_len=2,
                )
            )
        db_session.commit()

        result = score_message(
            db_session,
            path_prefix=None,
            sender_normalized="bob",
            path_len=2,
            received_at=now,
            cfg=CFG,
        )
        assert result.name_count == 3
        assert result.score == pytest.approx(0.6)

    def test_no_sender_scores_zero(self, db_session):
        now = datetime.now(timezone.utc)
        result = score_message(
            db_session,
            path_prefix="AA,BB,CC",
            sender_normalized=None,
            path_len=6,
            received_at=now,
            cfg=CFG,
        )
        assert result.score == 0.0


class TestRescoreRecent:
    def test_leading_edge_rescored_with_hindsight(self, db_session):
        """Rows that scored low online get raised once peers arrive."""
        now = datetime.now(timezone.utc)
        # Insert a burst, all with spam_score=0.0 (as the online path would set
        # for the leading edge), out of natural order.
        msgs = []
        for i in range(6):
            m = _make_message(
                now - timedelta(seconds=5 * i),
                path_prefix="AA,BB,CC",
                sender_normalized="bob",
            )
            m.spam_score = 0.0
            msgs.append(m)
            db_session.add(m)
        db_session.commit()

        updated = rescore_recent(db_session, CFG, now=now)
        db_session.commit()

        assert updated >= 1
        # The earliest row now sees its later peers symmetrically -> flagged.
        earliest = min(msgs, key=lambda m: m.received_at)
        db_session.refresh(earliest)
        assert earliest.spam_score >= CFG.score_threshold

    def test_idempotent(self, db_session):
        now = datetime.now(timezone.utc)
        for i in range(6):
            m = _make_message(
                now - timedelta(seconds=5 * i),
                path_prefix="AA,BB,CC",
                sender_normalized="bob",
            )
            db_session.add(m)
        db_session.commit()

        first = rescore_recent(db_session, CFG, now=now)
        db_session.commit()
        second = rescore_recent(db_session, CFG, now=now)
        db_session.commit()

        assert first >= 1
        assert second == 0  # nothing changes on a second pass
