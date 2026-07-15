"""Tests for the route health matching engine."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from meshcore_hub.collector.routes import (
    derive_expected_hash,
    derive_quality,
    detect_observed_widths,
    effective_clear_threshold,
    evaluate_all_routes,
    evaluate_route,
    evaluate_route_day,
    evaluate_route_history,
    is_subsequence,
    preview_route,
    prefix_collision_counts,
    recent_matches,
    upsert_route_result,
)
from meshcore_hub.common.models import (
    Node,
    PacketPathHop,
    RawPacket,
    Route,
    RouteNode,
    RouteObserver,
    RouteQuality,
    RouteResult,
    RouteState,
)

_NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _make_node(db_session, public_key: str, name: str | None = None) -> Node:
    node = Node(public_key=public_key, name=name)
    db_session.add(node)
    db_session.flush()
    return node


def _make_reception(
    db_session,
    observer_node_id: str | None,
    packet_hash: str,
    path_hashes: list[str],
    received_at: datetime | None = None,
) -> str:
    """Insert a RawPacket + PacketPathHop rows for a test reception."""
    ts = received_at or _NOW
    rp_id = str(uuid4())
    rp = RawPacket(
        id=rp_id,
        observer_node_id=observer_node_id,
        packet_hash=packet_hash,
        received_at=ts,
    )
    db_session.add(rp)
    db_session.flush()
    for pos, nh in enumerate(path_hashes):
        db_session.add(
            PacketPathHop(
                raw_packet_id=rp_id,
                position=pos,
                node_hash=nh,
                packet_hash=packet_hash,
                received_at=ts,
                observer_node_id=observer_node_id,
            )
        )
    db_session.flush()
    return rp_id


def _make_route(
    db_session,
    name: str,
    nodes: list[Node],
    match_width: int = 1,
    threshold: int = 3,
    clear_bar: int | None = None,
    max_hop_span: int | None = None,
    observers: list[Node] | None = None,
    enabled: bool = True,
    window_hours: int = 24,
    reversible: bool = True,
) -> Route:
    route = Route(
        from_label=name,
        to_label=name,
        match_width=match_width,
        packet_count_threshold=threshold,
        clear_threshold=clear_bar,
        max_hop_span=max_hop_span,
        enabled=enabled,
        window_hours=window_hours,
        reversible=reversible,
    )
    db_session.add(route)
    db_session.flush()
    for pos, node in enumerate(nodes):
        db_session.add(
            RouteNode(
                route_id=route.id,
                node_id=node.id,
                position=pos,
                expected_hash=derive_expected_hash(node.public_key, match_width),
            )
        )
    if observers:
        for obs in observers:
            db_session.add(RouteObserver(route_id=route.id, node_id=obs.id))
    db_session.flush()
    return route


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestIsSubsequence:
    def test_exact_match(self):
        path = [{"position": 0, "node_hash": "A1"}, {"position": 1, "node_hash": "B2"}]
        assert is_subsequence(path, ["A1", "B2"]) is True

    def test_gaps_allowed(self):
        path = [
            {"position": 0, "node_hash": "A1"},
            {"position": 1, "node_hash": "XX"},
            {"position": 2, "node_hash": "B2"},
        ]
        assert is_subsequence(path, ["A1", "B2"]) is True

    def test_order_enforced(self):
        path = [{"position": 0, "node_hash": "B2"}, {"position": 1, "node_hash": "A1"}]
        assert is_subsequence(path, ["A1", "B2"]) is False

    def test_prefix_match(self):
        """A1B2 startswith A1 — prefix match should succeed."""
        path = [
            {"position": 0, "node_hash": "A1B2"},
            {"position": 1, "node_hash": "C3"},
        ]
        assert is_subsequence(path, ["A1", "C3"]) is True

    def test_span_cap_within(self):
        path = [
            {"position": 0, "node_hash": "A1"},
            {"position": 1, "node_hash": "X"},
            {"position": 2, "node_hash": "B2"},
        ]
        assert is_subsequence(path, ["A1", "B2"], max_hop_span=2) is True

    def test_span_cap_exceeds(self):
        path = [
            {"position": 0, "node_hash": "A1"},
            {"position": 1, "node_hash": "X"},
            {"position": 2, "node_hash": "X"},
            {"position": 3, "node_hash": "X"},
            {"position": 4, "node_hash": "B2"},
        ]
        assert is_subsequence(path, ["A1", "B2"], max_hop_span=2) is False

    def test_empty_expected(self):
        assert is_subsequence([{"position": 0, "node_hash": "A1"}], []) is False


class TestDeriveQuality:
    def test_clear(self):
        assert (
            derive_quality(RouteState.HEALTHY.value, 10, 3, 6)
            == RouteQuality.CLEAR.value
        )

    def test_marginal(self):
        assert (
            derive_quality(RouteState.HEALTHY.value, 4, 3, 6)
            == RouteQuality.MARGINAL.value
        )

    def test_failing(self):
        assert (
            derive_quality(RouteState.UNHEALTHY.value, 1, 3, 6)
            == RouteQuality.FAILING.value
        )

    def test_unknown(self):
        assert (
            derive_quality(RouteState.NO_COVERAGE.value, 0, 3, 6)
            == RouteQuality.UNKNOWN.value
        )


class TestEffectiveClear:
    def test_explicit(self, db_session):
        route = Route(
            from_label="t",
            to_label="t",
            packet_count_threshold=5,
            clear_threshold=20,
        )
        assert effective_clear_threshold(route) == 20

    def test_default_2x(self, db_session):
        route = Route(
            from_label="t",
            to_label="t",
            packet_count_threshold=5,
            clear_threshold=None,
        )
        assert effective_clear_threshold(route) == 10


class TestDeriveExpectedHash:
    def test_uppercased(self):
        assert derive_expected_hash("aabbccdd" * 8, 1) == "AA"
        assert derive_expected_hash("aabbccdd" * 8, 2) == "AABB"
        assert derive_expected_hash("aabbccdd" * 8, 3) == "AABBCC"


# ---------------------------------------------------------------------------
# DB-backed evaluation tests
# ---------------------------------------------------------------------------


class TestEvaluateRoute:
    def test_healthy_clear(self, db_session):
        """Enough distinct matching packets → healthy/clear."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        for i in range(10):
            _make_reception(db_session, None, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert state == RouteState.HEALTHY.value
        assert quality == RouteQuality.CLEAR.value
        assert count >= 6  # short-circuited at effective_clear = 6

    def test_healthy_marginal(self, db_session):
        """Meets threshold but not comfort bar → healthy/marginal."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        for i in range(4):
            _make_reception(db_session, None, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert state == RouteState.HEALTHY.value
        assert quality == RouteQuality.MARGINAL.value
        assert count == 4

    def test_unhealthy(self, db_session):
        """Receptions exist but not enough matches → unhealthy/failing."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        _make_reception(db_session, None, "pkt1", ["AA", "BB"])
        _make_reception(db_session, None, "pkt2", ["CC", "DD"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert state == RouteState.UNHEALTHY.value
        assert quality == RouteQuality.FAILING.value
        assert count == 1

    def test_no_coverage(self, db_session):
        """Zero hops in window → no_coverage/unknown."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert state == RouteState.NO_COVERAGE.value
        assert quality == RouteQuality.UNKNOWN.value
        assert count == 0

    def test_per_reception_isolation(self, db_session):
        """Hops from different receptions are never spliced together."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=1)

        # Reception 1: has AA only
        _make_reception(db_session, None, "pkt1", ["AA"])
        # Reception 2: has BB only
        _make_reception(db_session, None, "pkt2", ["BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, _, count = evaluate_route(db_session, route, since)
        assert count == 0  # Neither reception has both A and B in order
        assert state == RouteState.UNHEALTHY.value

    def test_multi_observer_dedup(self, db_session):
        """Same packet from two observers counts once."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        obs1 = _make_node(db_session, "cc" + "0" * 62)
        obs2 = _make_node(db_session, "dd" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=1)

        _make_reception(db_session, obs1.id, "shared", ["AA", "BB"])
        _make_reception(db_session, obs2.id, "shared", ["AA", "BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, _, count = evaluate_route(db_session, route, since)
        assert count == 1
        assert state == RouteState.HEALTHY.value

    def test_observer_scope_filter(self, db_session):
        """Only in-scope observers are considered."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        obs1 = _make_node(db_session, "cc" + "0" * 62)
        obs2 = _make_node(db_session, "dd" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], threshold=1, observers=[obs1]
        )

        # obs1 has no matching reception; obs2 has a match but is out of scope
        _make_reception(db_session, obs2.id, "pkt1", ["AA", "BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, _, count = evaluate_route(db_session, route, since)
        assert count == 0

    def test_short_circuit_at_effective_clear(self, db_session):
        """Evaluation stops counting at the comfort bar."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], threshold=2, clear_bar=4
        )

        for i in range(20):
            _make_reception(db_session, None, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert quality == RouteQuality.CLEAR.value
        assert count == 4  # short-circuited at effective_clear = 4

    def test_reversible_matches_reverse_direction(self, db_session):
        """Reversible route matches packets travelling the reverse path."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        # Packets going B->A (reverse of configured A->B)
        for i in range(5):
            _make_reception(db_session, None, f"pkt{i}", ["BB", "AA"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert state == RouteState.HEALTHY.value
        assert count == 5

    def test_non_reversible_ignores_reverse_direction(self, db_session):
        """Non-reversible route does NOT match reverse-direction packets."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], threshold=3, reversible=False
        )

        # Only reverse-direction packets exist (B->A)
        for i in range(5):
            _make_reception(db_session, None, f"pkt{i}", ["BB", "AA"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert count == 0

    def test_reversible_matches_both_directions(self, db_session):
        """Reversible route matches packets in both directions."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        _make_reception(db_session, None, "fwd1", ["AA", "BB"])
        _make_reception(db_session, None, "rev1", ["BB", "AA"])
        _make_reception(db_session, None, "fwd2", ["AA", "BB"])
        _make_reception(db_session, None, "rev2", ["BB", "AA"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        state, quality, count = evaluate_route(db_session, route, since)
        assert state == RouteState.HEALTHY.value
        assert count == 4


class TestEvaluateAllRoutes:
    def test_only_enabled_routes(self, db_session):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        _make_route(db_session, "enabled", [node_a, node_b], enabled=True)
        _make_route(db_session, "disabled", [node_a, node_b], enabled=False)
        db_session.commit()

        results = evaluate_all_routes(db_session, _NOW)
        assert len(results) == 1


class TestUpsertRouteResult:
    def test_idempotent(self, db_session):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b])
        db_session.commit()

        upsert_route_result(
            db_session, route, RouteState.HEALTHY.value, RouteQuality.CLEAR.value, 5
        )
        db_session.commit()
        assert len(db_session.execute(select(RouteResult)).scalars().all()) == 1

        upsert_route_result(
            db_session, route, RouteState.UNHEALTHY.value, RouteQuality.FAILING.value, 1
        )
        db_session.commit()
        results = db_session.execute(select(RouteResult)).scalars().all()
        assert len(results) == 1
        assert results[0].state == RouteState.UNHEALTHY.value
        assert results[0].quality == RouteQuality.FAILING.value


class TestRecentMatches:
    def test_ordering_and_limit(self, db_session):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b])

        for i in range(5):
            _make_reception(
                db_session,
                None,
                f"pkt{i}",
                ["AA", "BB"],
                received_at=_NOW - timedelta(hours=i),
            )
        db_session.commit()

        matches = recent_matches(db_session, route, limit=3, now=_NOW)
        assert len(matches) == 3
        assert matches[0]["received_at"] > matches[1]["received_at"]

    def test_returns_sliced_subpath(self, db_session):
        """Recent matches return only the hops between From and To, not the
        full packet path."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b])

        # Packet path has noise before AA and after BB; only AA..BB should be kept.
        _make_reception(db_session, None, "pkt0", ["XX", "AA", "YY", "BB", "ZZ"])
        db_session.commit()

        matches = recent_matches(db_session, route, limit=3, now=_NOW)
        assert len(matches) == 1
        hops = matches[0]["hops"]
        assert [h["node_hash"] for h in hops] == ["AA", "YY", "BB"]

    def test_returns_sliced_subpath_reverse(self, db_session):
        """A reverse-direction packet is sliced in traversal order (To..From)."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], reversible=True)

        _make_reception(db_session, None, "pkt0", ["XX", "BB", "YY", "AA", "ZZ"])
        db_session.commit()

        matches = recent_matches(db_session, route, limit=3, now=_NOW)
        assert len(matches) == 1
        hops = matches[0]["hops"]
        assert [h["node_hash"] for h in hops] == ["BB", "YY", "AA"]


class TestPreviewRoute:
    def test_normal_preview(self, db_session):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)

        for i in range(7):
            _make_reception(db_session, None, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        since = _NOW - timedelta(hours=24)
        result = preview_route(
            db_session,
            {
                "node_ids": [node_a.id, node_b.id],
                "match_width": 1,
                "packet_count_threshold": 3,
            },
            since,
        )
        assert result["matched_count"] == 7
        assert result["quality"] == RouteQuality.CLEAR.value
        assert result["truncated"] is False

    def test_truncation_at_cap(self, db_session, monkeypatch):
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)

        for i in range(10):
            _make_reception(db_session, None, f"pkt{i}", ["AA", "BB"])
        db_session.commit()

        monkeypatch.setattr("meshcore_hub.collector.routes.PREVIEW_CANDIDATE_CAP", 5)
        since = _NOW - timedelta(hours=24)
        result = preview_route(
            db_session,
            {
                "node_ids": [node_a.id, node_b.id],
                "match_width": 1,
                "packet_count_threshold": 3,
                "reversible": False,
            },
            since,
        )
        assert result["truncated"] is True
        assert result["matched_count"] is None
        assert result["candidate_count"] == 10

    def test_collisions(self, db_session):
        """Two nodes sharing the same first byte collide."""
        _make_node(db_session, "aa11" + "0" * 60)
        _make_node(db_session, "aa22" + "0" * 60)
        _make_node(db_session, "bb33" + "0" * 60)
        db_session.commit()

        counts = prefix_collision_counts(db_session, 1)
        assert counts.get("AA") == 2
        assert counts.get("BB") == 1

    def test_detect_observed_widths(self, db_session):
        node = _make_node(db_session, "aabb" + "0" * 60)
        _make_reception(db_session, None, "p1", ["AABB"])
        db_session.commit()

        widths = detect_observed_widths(db_session, node.public_key)
        assert 2 in widths  # observed at 2-byte prefix "AABB"


# ---------------------------------------------------------------------------
# Day-bounded evaluation tests
# ---------------------------------------------------------------------------


class TestEvaluateRouteDay:
    def test_clear_within_day(self, db_session):
        """Enough matches within the day window → clear."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        day_start = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(10):
            _make_reception(
                db_session,
                None,
                f"pkt{i}",
                ["AA", "BB"],
                received_at=day_start + timedelta(hours=2),
            )
        db_session.commit()

        quality, state, count = evaluate_route_day(
            db_session, route, day_start, day_end
        )
        assert quality == RouteQuality.CLEAR.value
        assert state == RouteState.HEALTHY.value
        assert count >= 6  # short-circuited at effective_clear = 6

    def test_marginal_within_day(self, db_session):
        """Meets threshold but not comfort bar → marginal."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        day_start = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(4):
            _make_reception(
                db_session,
                None,
                f"pkt{i}",
                ["AA", "BB"],
                received_at=day_start + timedelta(hours=1),
            )
        db_session.commit()

        quality, state, count = evaluate_route_day(
            db_session, route, day_start, day_end
        )
        assert quality == RouteQuality.MARGINAL.value
        assert state == RouteState.HEALTHY.value
        assert count == 4

    def test_failing_within_day(self, db_session):
        """Traffic exists but not enough matches → failing."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        day_start = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc)

        _make_reception(
            db_session,
            None,
            "pkt1",
            ["AA", "BB"],
            received_at=day_start + timedelta(hours=1),
        )
        _make_reception(
            db_session,
            None,
            "pkt2",
            ["CC", "DD"],
            received_at=day_start + timedelta(hours=2),
        )
        db_session.commit()

        quality, state, count = evaluate_route_day(
            db_session, route, day_start, day_end
        )
        assert quality == RouteQuality.FAILING.value
        assert state == RouteState.UNHEALTHY.value
        assert count == 1

    def test_no_coverage_within_day(self, db_session):
        """Zero hops in the day window → no_coverage/unknown."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        day_start = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc)

        db_session.commit()

        quality, state, count = evaluate_route_day(
            db_session, route, day_start, day_end
        )
        assert quality == RouteQuality.UNKNOWN.value
        assert state == RouteState.NO_COVERAGE.value
        assert count == 0

    def test_strict_day_boundary(self, db_session):
        """Hops in the adjacent day do not leak across the day_end bound."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        day_start = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc)

        # 10 matches the day AFTER day_end
        for i in range(10):
            _make_reception(
                db_session,
                None,
                f"after{i}",
                ["AA", "BB"],
                received_at=day_end + timedelta(hours=2, seconds=i),
            )
        db_session.commit()

        quality, state, count = evaluate_route_day(
            db_session, route, day_start, day_end
        )
        assert state == RouteState.NO_COVERAGE.value
        assert count == 0

    def test_hops_outside_before_boundary_excluded(self, db_session):
        """Hops before day_start are excluded."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        day_start = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(2026, 7, 11, 0, 0, 0, tzinfo=timezone.utc)

        # Matches the day BEFORE day_start
        for i in range(10):
            _make_reception(
                db_session,
                None,
                f"before{i}",
                ["AA", "BB"],
                received_at=day_start - timedelta(hours=12, seconds=i),
            )
        db_session.commit()

        quality, state, count = evaluate_route_day(
            db_session, route, day_start, day_end
        )
        assert state == RouteState.NO_COVERAGE.value
        assert count == 0


class TestEvaluateRouteHistory:
    def test_returns_days_entries_oldest_first(self, db_session):
        """History returns *days* entries, oldest first."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=1)
        db_session.commit()

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        results = evaluate_route_history(db_session, route, days=7, now=now)

        assert len(results) == 7
        dates = [r[0] for r in results]
        assert dates == sorted(dates)
        assert dates[0] == (now - timedelta(days=7)).date()
        assert dates[-1] == (now - timedelta(days=1)).date()

    def test_include_today_adds_extra(self, db_session):
        """include_today=True adds one partial-day entry."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=1)
        db_session.commit()

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        results = evaluate_route_history(
            db_session, route, days=7, include_today=True, now=now
        )

        assert len(results) == 8
        assert results[-1][0] == now.date()  # today is the final entry

    def test_disabled_route_all_unknown(self, db_session):
        """Disabled route returns unknown/no_coverage/0 for every day."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], threshold=1, enabled=False
        )
        db_session.commit()

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        results = evaluate_route_history(db_session, route, days=7, now=now)

        assert len(results) == 7
        for _day, quality, state, count in results:
            assert quality == RouteQuality.UNKNOWN.value
            assert state == RouteState.NO_COVERAGE.value
            assert count == 0

    def test_disabled_route_include_today(self, db_session):
        """Disabled route with include_today returns days+1 entries."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(
            db_session, "R1", [node_a, node_b], threshold=1, enabled=False
        )
        db_session.commit()

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        results = evaluate_route_history(
            db_session, route, days=7, include_today=True, now=now
        )

        assert len(results) == 8
        for _day, quality, _state, _count in results:
            assert quality == RouteQuality.UNKNOWN.value

    def test_correct_quality_per_day(self, db_session):
        """Different days produce different quality bands."""
        node_a = _make_node(db_session, "aa" + "0" * 62)
        node_b = _make_node(db_session, "bb" + "0" * 62)
        route = _make_route(db_session, "R1", [node_a, node_b], threshold=3)

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

        # 3 days ago: clear (10 matches)
        clear_day = now - timedelta(days=3)
        for i in range(10):
            _make_reception(
                db_session,
                None,
                f"clear{i}",
                ["AA", "BB"],
                received_at=clear_day.replace(hour=6) + timedelta(seconds=i),
            )
        # 2 days ago: marginal (4 matches)
        marginal_day = now - timedelta(days=2)
        for i in range(4):
            _make_reception(
                db_session,
                None,
                f"marg{i}",
                ["AA", "BB"],
                received_at=marginal_day.replace(hour=6) + timedelta(seconds=i),
            )
        db_session.commit()

        results = evaluate_route_history(db_session, route, days=7, now=now)
        by_date = {r[0]: (r[1], r[2], r[3]) for r in results}

        clear_date = (now - timedelta(days=3)).date()
        marginal_date = (now - timedelta(days=2)).date()
        assert by_date[clear_date][0] == RouteQuality.CLEAR.value
        assert by_date[marginal_date][0] == RouteQuality.MARGINAL.value
