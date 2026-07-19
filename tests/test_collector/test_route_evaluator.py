"""Tests for the route evaluator."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from meshcore_hub.collector.route_evaluator import (
    run_evaluation,
    run_history_backfill,
)
from meshcore_hub.collector.routes import derive_expected_hash
from meshcore_hub.common.models import (
    Node,
    PacketPathHop,
    RawPacket,
    Route,
    RouteNode,
    RouteRecentMatch,
    RouteResult,
    RouteResultHistory,
    RouteQuality,
    RouteState,
)

_NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _make_node(session, pk: str) -> Node:
    node = Node(public_key=pk)
    session.add(node)
    session.flush()
    return node


def _make_reception(session, packet_hash: str, path: list[str], ts=None):
    ts = ts or _NOW
    rp_id = str(uuid4())
    session.add(RawPacket(id=rp_id, packet_hash=packet_hash, received_at=ts))
    session.flush()
    for pos, nh in enumerate(path):
        session.add(
            PacketPathHop(
                raw_packet_id=rp_id,
                position=pos,
                node_hash=nh,
                packet_hash=packet_hash,
                received_at=ts,
            )
        )
    session.flush()


def _make_route(session, name, nodes, **kwargs):
    route = Route(from_label=name, to_label=name, **kwargs)
    session.add(route)
    session.flush()
    for pos, n in enumerate(nodes):
        session.add(
            RouteNode(
                route_id=route.id,
                node_id=n.id,
                position=pos,
                expected_hash=derive_expected_hash(n.public_key, 1),
            )
        )
    session.flush()
    return route


class TestRunEvaluation:
    def test_upsert_idempotent(self, db_manager, db_session):
        """Re-evaluating the same route overwrites its single result row."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b], packet_count_threshold=1)
        for i in range(3):
            _make_reception(db_session, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        count1 = run_evaluation(db_manager, now=_NOW)
        assert count1 == 1
        results = db_session.execute(select(RouteResult)).scalars().all()
        assert len(results) == 1

        count2 = run_evaluation(db_manager, now=_NOW)
        assert count2 == 1
        results = db_session.execute(select(RouteResult)).scalars().all()
        assert len(results) == 1  # still one row (overwritten)

    def test_disabled_routes_skipped(self, db_manager, db_session):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "enabled", [node_a, node_b], enabled=True)
        _make_route(db_session, "disabled", [node_a, node_b], enabled=False)
        db_session.commit()

        count = run_evaluation(db_manager, now=_NOW)
        assert count == 1  # only the enabled route

    def test_writes_correct_result(self, db_manager, db_session):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], packet_count_threshold=3
        )
        for i in range(7):
            _make_reception(db_session, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        run_evaluation(db_manager, now=_NOW)
        db_session.expire_all()

        result = db_session.execute(
            select(RouteResult).where(RouteResult.route_id == route.id)
        ).scalar_one()
        assert result.state == RouteState.HEALTHY.value
        assert result.quality == RouteQuality.CLEAR.value
        assert result.threshold == 3
        assert result.effective_clear == 6

    def test_evaluation_error_logged(self, db_manager, db_session, monkeypatch):
        """An exception evaluating one route is caught; count stays 0."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b])
        db_session.commit()

        def _boom(*_args, **_kwargs):
            raise RuntimeError("eval failed")

        # Patch both the source module and the evaluator's bound import so
        # the boom is effective regardless of how ``_evaluate_one`` resolves
        # ``evaluate_route``.
        monkeypatch.setattr("meshcore_hub.collector.routes.evaluate_route", _boom)
        monkeypatch.setattr(
            "meshcore_hub.collector.route_evaluator.evaluate_route", _boom
        )
        count = run_evaluation(db_manager, now=_NOW)
        assert count == 0


class TestPrecomputedRecentMatches:
    """The 60s sweep populates ``route_recent_matches`` (normalized table)."""

    def test_populates_matches_with_positions(self, db_manager, db_session):
        """The sweep writes one ``RouteRecentMatch`` per matching reception
        with the matched subpath's position bounds."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], packet_count_threshold=1
        )
        # Bracketed path: noise before AA and after BB.
        _make_reception(db_session, "pkt0", ["XX", "AA", "BB", "ZZ"])
        db_session.commit()

        run_evaluation(db_manager, now=_NOW)

        rows = (
            db_session.execute(
                select(RouteRecentMatch).where(RouteRecentMatch.route_id == route.id)
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].first_position == 1
        assert rows[0].last_position == 2

    def test_capped_at_three_per_route(self, db_manager, db_session):
        """More than 3 matches in the window only retain the top 3 (the
        cap enforced at write time)."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b], packet_count_threshold=1)
        for i in range(5):
            _make_reception(
                db_session,
                f"pkt{i}",
                ["AA", "BB"],
                ts=_NOW - timedelta(hours=i),
            )
        db_session.commit()

        run_evaluation(db_manager, now=_NOW)

        rows = db_session.execute(select(RouteRecentMatch)).scalars().all()
        assert len(rows) == 3

    def test_idempotent_replacement(self, db_manager, db_session):
        """A second sweep replaces stale matches instead of accumulating."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b], packet_count_threshold=1)
        _make_reception(db_session, "pkt0", ["AA", "BB"], ts=_NOW)
        db_session.commit()

        run_evaluation(db_manager, now=_NOW)
        first = db_session.execute(select(RouteRecentMatch)).scalars().all()
        assert len(first) == 1
        first_id = first[0].raw_packet_id

        # Run again — should overwrite, not insert a second row.
        run_evaluation(db_manager, now=_NOW)
        second = db_session.execute(select(RouteRecentMatch)).scalars().all()
        assert len(second) == 1
        assert second[0].raw_packet_id == first_id


class TestPrecomputedQualityAvg:
    """The 60s sweep computes ``quality_avg`` from persisted history."""

    def test_quality_avg_none_when_no_history(self, db_manager, db_session):
        """A brand-new route with no historical buckets gets ``quality_avg=None``.

        The frontend falls back to ``route_result.quality`` via the
        ``q = quality_avg || route_result?.quality`` chain.
        """
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b])
        db_session.commit()

        run_evaluation(db_manager, now=_NOW)
        db_session.expire_all()

        result = db_session.execute(
            select(RouteResult).where(RouteResult.route_id == route.id)
        ).scalar_one()
        assert result.quality_avg is None

    def test_quality_avg_from_seeded_history(self, db_manager, db_session):
        """With persisted history rows, the sweep computes the rolling average."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b])
        today = _NOW.date()
        # Seed 7 days of failing history.
        for i in range(1, 8):
            db_session.add(
                RouteResultHistory(
                    route_id=route.id,
                    date=today - timedelta(days=i),
                    quality=RouteQuality.FAILING.value,
                    state=RouteState.UNHEALTHY.value,
                    matched_count=0,
                )
            )
        db_session.commit()

        run_evaluation(db_manager, now=_NOW)
        db_session.expire_all()

        result = db_session.execute(
            select(RouteResult).where(RouteResult.route_id == route.id)
        ).scalar_one()
        assert result.quality_avg == RouteQuality.FAILING.value


class TestRunHistoryBackfill:
    """The hourly sweep populates ``route_result_history`` for completed days."""

    def test_writes_history_rows_for_completed_days(self, db_manager, db_session):
        """The backfill populates one row per completed UTC day in the window."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], packet_count_threshold=1
        )
        # Place matching packets across 3 different completed days.
        for days_ago in range(1, 4):
            _make_reception(
                db_session,
                f"pkt-{days_ago}",
                ["AA", "BB"],
                ts=_NOW - timedelta(days=days_ago, hours=2),
            )
        db_session.commit()

        # Backfill exactly 3 days (one row per day in the window).
        run_history_backfill(db_manager, days=3, now=_NOW)

        rows = (
            db_session.execute(
                select(RouteResultHistory)
                .where(RouteResultHistory.route_id == route.id)
                .order_by(RouteResultHistory.date)
            )
            .scalars()
            .all()
        )
        # Three completed days each get a row.
        assert len(rows) == 3
        # 1 match / threshold 1 ⇒ healthy. eff_clear=2 ⇒ marginal (1 < 2).
        for row in rows:
            assert row.state == RouteState.HEALTHY.value
            assert row.quality == RouteQuality.MARGINAL.value
            assert row.matched_count == 1

    def test_does_not_write_today_bucket(self, db_manager, db_session):
        """The backfill skips today's calendar day (the rolling snapshot
        in ``route_results`` covers today)."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b], packet_count_threshold=1)
        _make_reception(db_session, "today-pkt", ["AA", "BB"], ts=_NOW)
        db_session.commit()

        run_history_backfill(db_manager, days=3, now=_NOW)

        rows = db_session.execute(select(RouteResultHistory)).scalars().all()
        # No row for today's date.
        today = _NOW.date()
        assert all(r.date < today for r in rows)

    def test_skips_when_days_zero(self, db_manager, db_session):
        """``days=0`` is a no-op (returns 0 routes backfilled)."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b])
        db_session.commit()

        count = run_history_backfill(db_manager, days=0, now=_NOW)
        assert count == 0

    def test_idempotent_re_evaluation(self, db_manager, db_session):
        """Re-running the backfill overwrites existing history rows in place
        (UNIQUE(route_id, date))."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "R1", [node_a, node_b], packet_count_threshold=1)
        _make_reception(
            db_session,
            "pkt",
            ["AA", "BB"],
            ts=_NOW - timedelta(days=1, hours=2),
        )
        db_session.commit()

        run_history_backfill(db_manager, days=3, now=_NOW)
        rows_after_first = (
            db_session.execute(
                select(RouteResultHistory).where(
                    RouteResultHistory.date == _NOW.date() - timedelta(days=1)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows_after_first) == 1

        # Re-run — should overwrite, not duplicate.
        run_history_backfill(db_manager, days=3, now=_NOW)
        rows_after_second = (
            db_session.execute(
                select(RouteResultHistory).where(
                    RouteResultHistory.date == _NOW.date() - timedelta(days=1)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows_after_second) == 1
