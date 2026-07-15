"""Tests for the route evaluator."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from meshcore_hub.collector.route_evaluator import run_evaluation
from meshcore_hub.collector.routes import derive_expected_hash
from meshcore_hub.common.models import (
    Node,
    PacketPathHop,
    RawPacket,
    Route,
    RouteNode,
    RouteResult,
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
