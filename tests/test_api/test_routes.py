"""Tests for route API endpoints."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from meshcore_hub.collector.routes import derive_expected_hash
from meshcore_hub.common.models import (
    Node,
    PacketPathHop,
    RawPacket,
    Route,
    RouteNode,
)


def _make_node(session, public_key: str, name: str | None = None) -> Node:
    node = Node(public_key=public_key, name=name, first_seen=datetime.now(timezone.utc))
    session.add(node)
    session.flush()
    return node


def _sample_nodes(session, count: int = 2) -> list[Node]:
    keys = [f"{chr(97 + i)}" * 64 for i in range(count)]
    return [_make_node(session, k, f"Node-{i}") for i, k in enumerate(keys)]


def _make_reception(
    session,
    observer_node_id: str | None,
    packet_hash: str,
    path_hashes: list[str],
    received_at: datetime | None = None,
) -> str:
    """Insert a RawPacket + PacketPathHop rows for a test reception."""
    ts = received_at or datetime.now(timezone.utc)
    rp_id = str(uuid4())
    session.add(
        RawPacket(
            id=rp_id,
            observer_node_id=observer_node_id,
            packet_hash=packet_hash,
            received_at=ts,
        )
    )
    session.flush()
    for pos, nh in enumerate(path_hashes):
        session.add(
            PacketPathHop(
                raw_packet_id=rp_id,
                position=pos,
                node_hash=nh,
                packet_hash=packet_hash,
                received_at=ts,
                observer_node_id=observer_node_id,
            )
        )
    session.flush()
    return rp_id


class TestListRoutes:
    def test_empty(self, client_no_auth):
        resp = client_no_auth.get("/api/v1/routes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_visibility_filter(self, client_no_auth, api_db_session):
        api_db_session.add(
            Route(from_label="Public", to_label="Endpoint", visibility="community")
        )
        api_db_session.add(
            Route(from_label="Secret", to_label="Endpoint", visibility="admin")
        )
        api_db_session.commit()

        resp = client_no_auth.get("/api/v1/routes")
        assert resp.status_code == 200
        labels = [r["from_label"] for r in resp.json()["items"]]
        assert "Public" in labels
        assert "Secret" not in labels

    def test_admin_sees_all(self, client_no_auth, api_db_session):
        api_db_session.add(
            Route(from_label="Public", to_label="Endpoint", visibility="community")
        )
        api_db_session.add(
            Route(from_label="Secret", to_label="Endpoint", visibility="admin")
        )
        api_db_session.commit()

        resp = client_no_auth.get("/api/v1/routes", headers={"X-User-Roles": "admin"})
        assert resp.status_code == 200
        labels = [r["from_label"] for r in resp.json()["items"]]
        assert "Public" in labels
        assert "Secret" in labels


class TestCreateRoute:
    def test_create_success(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "Alpha",
                "to_label": "Beta",
                "node_public_keys": [n.public_key for n in nodes],
                "match_width": 1,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["from_label"] == "Alpha"
        assert data["to_label"] == "Beta"
        assert len(data["route_nodes"]) == 2
        assert data["route_nodes"][0]["expected_hash"] is not None
        assert data["reversible"] is True

    def test_create_non_reversible(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "Alpha",
                "to_label": "Beta",
                "node_public_keys": [n.public_key for n in nodes],
                "reversible": False,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        assert resp.json()["reversible"] is False

    def test_duplicate_from_to_rejected(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.add(Route(from_label="Dup", to_label="End"))
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "Dup",
                "to_label": "End",
                "node_public_keys": [n.public_key for n in nodes],
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 409

    def test_min_two_nodes(self, client_no_auth, api_db_session):
        node = _make_node(api_db_session, "a" * 64)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "A",
                "to_label": "B",
                "node_public_keys": [node.public_key],
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 422

    def test_distinct_nodes(self, client_no_auth, api_db_session):
        node = _make_node(api_db_session, "a" * 64)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "A",
                "to_label": "B",
                "node_public_keys": [node.public_key, node.public_key],
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 422

    def test_clear_threshold_validation(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "A",
                "to_label": "B",
                "node_public_keys": [n.public_key for n in nodes],
                "packet_count_threshold": 5,
                "clear_threshold": 3,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 422

    def test_non_admin_rejected(self, client_with_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_with_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "A",
                "to_label": "B",
                "node_public_keys": [n.public_key for n in nodes],
            },
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert resp.status_code == 403


class TestGetRouteDetail:
    def test_detail_shape(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session, 3)
        route = Route(from_label="Alpha", to_label="Beta")
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["from_label"] == "Alpha"
        assert data["to_label"] == "Beta"
        assert len(data["route_nodes"]) == 3
        assert "contributing_observers" in data
        assert "recent_matches" in data

    def test_not_found(self, client_no_auth):
        resp = client_no_auth.get("/api/v1/routes/nonexistent")
        assert resp.status_code == 404

    def test_detail_response_is_cached(self, client_no_auth, api_db_session):
        """Detail endpoint writes its response to the cache after a miss."""
        import json
        from unittest.mock import MagicMock

        nodes = _sample_nodes(api_db_session, 2)
        route = Route(from_label="Alpha", to_label="Beta")
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        api_db_session.commit()

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl_dashboard = 90

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        assert resp.headers.get("x-cache") == "MISS"

        mock_cache.set.assert_called_once()
        cache_key, serialized, ttl = mock_cache.set.call_args[0]
        assert cache_key.startswith(f"/api/v1/routes/{route.id}:")
        assert "role=anonymous" in cache_key
        assert ttl == 90
        envelope = json.loads(serialized)
        assert envelope["body"]["from_label"] == "Alpha"
        assert isinstance(envelope["etag"], str)

    def test_detail_serves_from_cache_on_hit(self, client_no_auth, api_db_session):
        """A second call within the TTL window is served from the cache."""
        nodes = _sample_nodes(api_db_session, 2)
        route = Route(from_label="Alpha", to_label="Beta")
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        api_db_session.commit()

        store: dict[str, str] = {}

        class _FakeCache:
            def get(self, key):
                return store.get(key)

            def set(self, key, value, ttl):
                store[key] = value

            def ping(self):
                return True

        client_no_auth.app.state.redis_cache = _FakeCache()
        client_no_auth.app.state.redis_cache_ttl_dashboard = 60

        first = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert first.status_code == 200
        assert first.headers.get("x-cache") == "MISS"
        first_body = first.json()

        second = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert second.status_code == 200
        assert second.headers.get("x-cache") == "HIT"
        assert second.json() == first_body


class TestRouteQualityAvg:
    """``quality_avg`` field — rolling 7-day average tier.

    Backs the route card badge and summary strip counts on /routes so a
    flapping route that's currently up still shows as marginal/failing if
    the 7-day mean warrants it. See ``compute_average_quality`` in
    ``collector/routes.py`` for the algorithm.

    With precomputed history, ``quality_avg`` is sourced from
    ``route_result.quality_avg`` (written by the background evaluator).
    A fresh route has no history rows yet, so the field stays ``None``
    until the first evaluator tick — the frontend's
    ``quality_avg || route_result?.quality || 'unknown'`` fallback chain
    covers that gap.
    """

    @staticmethod
    def _make_route(session, *, enabled: bool = True, label: str = "Avg"):
        # Use uuid-derived public_keys so concurrent tests using _sample_nodes
        # (which always inserts "a"*64 / "b"*64) can't trip the unique
        # constraint on Node.public_key during parallel xdist runs against
        # the shared SQLite file.
        suffix = uuid4().hex
        keys = [(suffix[:32]).rjust(64, "0"), (suffix[32:64]).rjust(64, "0")]
        nodes = [_make_node(session, k) for k in keys]
        route = Route(from_label=label, to_label="Sink", enabled=enabled)
        session.add(route)
        session.flush()
        for pos, n in enumerate(nodes):
            session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        session.commit()
        return route

    @staticmethod
    def _seed_quality_avg(session, route: Route, value: str) -> None:
        """Write a ``route_result`` row with a precomputed ``quality_avg``.

        Mirrors what the background evaluator would produce once it has
        rolled over at least one day's worth of history.
        """
        from meshcore_hub.common.models.route_result import RouteResult

        existing = (
            session.query(RouteResult)
            .filter(RouteResult.route_id == route.id)
            .one_or_none()
        )
        if existing is None:
            session.add(
                RouteResult(
                    route_id=route.id,
                    state="healthy",
                    quality="clear",
                    matched_count=1,
                    threshold=route.packet_count_threshold,
                    effective_clear=route.packet_count_threshold * 3,
                    quality_avg=value,
                )
            )
        else:
            existing.quality_avg = value
        session.commit()

    def test_present_on_list_for_enabled_routes(self, client_no_auth, api_db_session):
        """Each enabled route in the list response carries the persisted tier.

        With precomputed storage, ``quality_avg`` reflects whatever the
        background evaluator last wrote on ``route_result``. A fresh route
        with no evaluator tick yet has ``None``; the point of this
        assertion is that the field surfaces verbatim from the DB.
        """
        route = self._make_route(api_db_session, enabled=True, label="Enabled")
        self._seed_quality_avg(api_db_session, route, "failing")
        resp = client_no_auth.get("/api/v1/routes")
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Lookup by id — parallel tests in the same worker may leave
        # other routes in the truncated-but-not-yet-reaped window.
        matching = [i for i in items if i["id"] == str(route.id)]
        assert len(matching) == 1
        avg = matching[0]["quality_avg"]
        assert avg in {"clear", "marginal", "failing"}
        # Seeded value passes through verbatim.
        assert avg == "failing"

    def test_none_for_disabled_routes(self, client_no_auth, api_db_session):
        """Disabled routes never carry a quality_avg (None regardless of
        what the evaluator wrote)."""
        route = self._make_route(api_db_session, enabled=False, label="Disabled")
        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        assert resp.json()["quality_avg"] is None

    def test_present_on_detail(self, client_no_auth, api_db_session):
        """Detail endpoint surfaces the persisted rolling average."""
        route = self._make_route(api_db_session, enabled=True, label="Detail")
        self._seed_quality_avg(api_db_session, route, "marginal")
        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        assert resp.json()["quality_avg"] == "marginal"

    def test_none_on_create_response(self, client_no_auth, api_db_session):
        """Create handler skips the rolling computation.

        A brand-new route has no meaningful 7-day history; the create
        response always returns ``None`` and the frontend falls back to
        ``route_result.quality`` via the
        ``q = route.quality_avg || route.route_result?.quality`` chain.
        """
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()
        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "Fresh",
                "to_label": "Route",
                "node_public_keys": [n.public_key for n in nodes],
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        assert resp.json()["quality_avg"] is None

    def test_computed_on_update_response(self, client_no_auth, api_db_session):
        """Update handler recomputes the average inline.

        ``_reevaluate_route`` runs ``compute_persisted_quality_avg`` which
        reads ``route_result_history`` and returns ``None`` when no rows
        exist yet (a fresh route with no hourly backfill under its belt).
        Seeding history before the PUT exercises the populated path.
        """
        from meshcore_hub.common.models.route_result_history import (
            RouteResultHistory,
        )
        from datetime import date

        route = self._make_route(api_db_session, enabled=True, label="UpdateMe")
        # Seed 7 days of failing history so the average resolves to failing.
        today = date.today()
        for i in range(1, 8):
            api_db_session.add(
                RouteResultHistory(
                    route_id=route.id,
                    date=today - timedelta(days=i),
                    quality="failing",
                    state="unhealthy",
                    matched_count=0,
                )
            )
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"description": "now with description"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["quality_avg"] == "failing"


class TestUpdateRoute:
    def test_update_from_to(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        route = Route(from_label="OldFrom", to_label="OldTo")
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"from_label": "NewFrom", "to_label": "NewTo"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["from_label"] == "NewFrom"
        assert data["to_label"] == "NewTo"

    def test_update_path_nodes(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session, 2)
        route = Route(from_label="A", to_label="B")
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        api_db_session.commit()

        new_node = _make_node(api_db_session, "z" * 64)
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"node_public_keys": [nodes[0].public_key, new_node.public_key]},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        public_keys = [rn["public_key"] for rn in data["route_nodes"]]
        assert new_node.public_key in public_keys

    def test_update_threshold_immediately_reflects_in_route_result(
        self, client_no_auth, api_db_session
    ):
        """Regression: PUT-changed threshold must surface in route_result now.

        Before this fix, ``route_result`` (written by a background
        evaluator on a 30-60s schedule) kept the OLD threshold until the
        next evaluator cycle. The routes list card displays
        ``route_result.threshold`` / ``effective_clear``, so the UI showed
        stale values for ~30s after a PUT even though the server returned
        ``x-cache: MISS`` with the route's direct fields updated. The
        PUT handler now runs ``_reevaluate_route`` synchronously after
        commit so the very next GET sees a fresh ``route_result``.
        """
        from meshcore_hub.common.models.route_result import RouteResult

        nodes = _sample_nodes(api_db_session, 2)
        route = Route(
            from_label="Sync",
            to_label="Eval",
            packet_count_threshold=6,
            clear_threshold=12,
            enabled=True,
        )
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        # Seed a stale RouteResult snapshot from a hypothetical prior
        # evaluator run using the OLD config (threshold=6, clear=12).
        # Without synchronous re-eval, this is what the PUT response
        # would continue to return until the next background sweep.
        api_db_session.add(
            RouteResult(
                route_id=route.id,
                state="healthy",
                quality="clear",
                matched_count=24,
                threshold=6,
                effective_clear=12,
                evaluated_at=datetime.now(timezone.utc),
            )
        )
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"packet_count_threshold": 3, "clear_threshold": 6},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # The route's direct fields reflect the new config...
        assert data["packet_count_threshold"] == 3
        assert data["clear_threshold"] == 6
        # ...AND route_result must reflect them too, not the stale
        # snapshot from the seeded prior evaluation.
        assert data["route_result"] is not None
        assert (
            data["route_result"]["threshold"] == 3
        ), "route_result.threshold should reflect the new packet_count_threshold"
        assert (
            data["route_result"]["effective_clear"] == 6
        ), "route_result.effective_clear should reflect the new clear_threshold"

    def test_disabled_route_does_not_trigger_evaluation(
        self, client_no_auth, api_db_session, monkeypatch
    ):
        """Disabled routes short-circuit ``_reevaluate_route`` (no point
        evaluating a route that won't be displayed as active). Guards
        against unnecessary DB scans on bulk config changes."""
        from meshcore_hub.api.routes import routes as routes_module

        called = {"count": 0}

        def _spy_evaluate(*args, **kwargs):
            called["count"] += 1
            return ("healthy", "clear", 0)

        monkeypatch.setattr(routes_module, "evaluate_route", _spy_evaluate)

        nodes = _sample_nodes(api_db_session, 2)
        route = Route(
            from_label="Off",
            to_label="Line",
            packet_count_threshold=3,
            enabled=False,
        )
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate(nodes):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"description": "still off"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        assert (
            called["count"] == 0
        ), "evaluate_route must not be called for disabled routes"


class TestDeleteRoute:
    def test_delete_success(self, client_no_auth, api_db_session):
        route = Route(from_label="Bye", to_label="Gone")
        api_db_session.add(route)
        api_db_session.commit()

        resp = client_no_auth.delete(
            f"/api/v1/routes/{route.id}",
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 204

    def test_not_found(self, client_no_auth):
        resp = client_no_auth.delete(
            "/api/v1/routes/nonexistent",
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 404


class TestPreview:
    def test_preview_no_match(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes/preview",
            json={
                "node_public_keys": [n.public_key for n in nodes],
                "match_width": 1,
                "window_hours": 24,
                "packet_count_threshold": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["truncated"] is False
        assert data["matched_count"] == 0

    def test_preview_validation_min_nodes(self, client_no_auth, api_db_session):
        node = _make_node(api_db_session, "a" * 64)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes/preview",
            json={"node_public_keys": [node.public_key]},
        )
        assert resp.status_code == 422


def _make_route_with_nodes(
    session,
    from_label: str,
    to_label: str,
    pubkeys: list[str],
    visibility: str = "community",
    enabled: bool = True,
    match_width: int = 1,
) -> Route:
    nodes = [_make_node(session, pk) for pk in pubkeys]
    route = Route(
        from_label=from_label,
        to_label=to_label,
        visibility=visibility,
        enabled=enabled,
        match_width=match_width,
    )
    session.add(route)
    session.flush()
    for pos, n in enumerate(nodes):
        session.add(
            RouteNode(
                route_id=route.id,
                node_id=n.id,
                position=pos,
                expected_hash=n.public_key[: 2 * match_width].upper(),
            )
        )
    return route


class TestRouteHistory:
    def test_response_shape(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session, "A", "B", ["aa" + "0" * 62, "bb" + "0" * 62]
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}/history?days=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["route_id"] == route.id
        assert "days" in data
        assert "data" in data
        assert isinstance(data["data"], list)
        for entry in data["data"]:
            assert "date" in entry
            assert "quality" in entry
            assert "state" in entry
            assert "matched_count" in entry

    def test_includes_today(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session, "A", "B", ["aa" + "0" * 62, "bb" + "0" * 62]
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}/history?days=7")
        assert resp.status_code == 200
        data = resp.json()
        # days=7 + include_today=True → 8 entries
        assert len(data["data"]) == 8

    def test_not_found(self, client_no_auth):
        resp = client_no_auth.get("/api/v1/routes/nonexistent/history")
        assert resp.status_code == 404

    def test_hidden_route_404(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session,
            "Secret",
            "EP",
            ["aa" + "0" * 62, "bb" + "0" * 62],
            visibility="admin",
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}/history")
        assert resp.status_code == 404

    def test_admin_sees_hidden_route(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session,
            "Secret",
            "EP",
            ["aa" + "0" * 62, "bb" + "0" * 62],
            visibility="admin",
        )
        api_db_session.commit()

        resp = client_no_auth.get(
            f"/api/v1/routes/{route.id}/history",
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200

    def test_disabled_route_history(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session,
            "Disabled",
            "Route",
            ["aa" + "0" * 62, "bb" + "0" * 62],
            enabled=False,
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}/history?days=3")
        assert resp.status_code == 200
        data = resp.json()
        for entry in data["data"]:
            assert entry["quality"] == "unknown"
            assert entry["state"] == "no_coverage"
            assert entry["matched_count"] == 0

    def test_retention_clamp(self, client_no_auth, api_db_session, monkeypatch):
        route = _make_route_with_nodes(
            api_db_session, "A", "B", ["aa" + "0" * 62, "bb" + "0" * 62]
        )
        api_db_session.commit()

        from unittest.mock import MagicMock

        mock_settings = MagicMock(effective_raw_packet_retention_days=2)
        monkeypatch.setattr(
            "meshcore_hub.api.routes.routes.get_collector_settings",
            lambda: mock_settings,
        )

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}/history?days=7")
        assert resp.status_code == 200
        data = resp.json()
        # retention=2 → days clamped to 2 → 3 entries (days + today)
        assert len(data["data"]) == 3

    def test_today_segment_matches_route_result_badge(
        self, client_no_auth, api_db_session
    ):
        """The rightmost history segment must match route_result (the badge).

        Regression for the rolling-window/calendar-day mismatch: packets
        placed yesterday evening are inside the rolling 24h window used by
        the badge but outside today's UTC calendar bucket. After this fix,
        the history endpoint's today segment must reflect the same
        matched_count/quality/state as route_result.
        """
        from datetime import timedelta

        from meshcore_hub.collector.routes import (
            evaluate_route,
            upsert_route_result,
        )

        route = _make_route_with_nodes(
            api_db_session, "A", "B", ["aa" + "0" * 62, "bb" + "0" * 62]
        )
        api_db_session.commit()

        # Place 3 matching packets 6h ago — within the 24h rolling window.
        # If "now" is early in the UTC day, this may land in yesterday's
        # calendar bucket, which is exactly the scenario we're fixing.
        now = datetime.now(timezone.utc)
        for i in range(3):
            _make_reception(
                api_db_session,
                None,
                f"badge{i}",
                ["AA", "BB"],
                received_at=now - timedelta(hours=6, seconds=i),
            )
        api_db_session.commit()

        # Populate route_result the same way the background evaluator does.
        rolling_start = now - timedelta(hours=route.window_hours)
        state, quality, matched = evaluate_route(api_db_session, route, rolling_start)
        upsert_route_result(api_db_session, route, state, quality, matched)
        api_db_session.commit()
        api_db_session.refresh(route)

        badge = route.route_result
        assert badge is not None, "fixture: route_result must be populated"

        # Bypass cache to read fresh state.
        client_no_auth.app.dependency_overrides = {}

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}/history?days=3")
        assert resp.status_code == 200
        today_segment = resp.json()["data"][-1]
        assert today_segment["matched_count"] == badge.matched_count
        assert today_segment["quality"] == badge.quality
        assert today_segment["state"] == badge.state


# ---------------------------------------------------------------------------
# Additional coverage: update fields, observers, hidden detail, preview guards
# ---------------------------------------------------------------------------


class TestUpdateRouteFields:
    """Cover the per-field update branches and edge cases of update_route."""

    def _make_route(self, session) -> Route:
        nodes = _sample_nodes(session)
        route = Route(from_label="OldFrom", to_label="OldTo")
        session.add(route)
        session.flush()
        for pos, n in enumerate(nodes):
            session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=n.public_key[:2].upper(),
                )
            )
        session.commit()
        return route

    def test_update_all_scalar_fields(self, client_no_auth, api_db_session):
        route = self._make_route(api_db_session)

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={
                "description": "updated desc",
                "visibility": "member",
                "match_width": 2,
                "window_hours": 48,
                "packet_count_threshold": 5,
                "clear_threshold": 8,
                "max_hop_span": 4,
                "enabled": False,
                "reversible": False,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "updated desc"
        assert data["visibility"] == "member"
        assert data["match_width"] == 2
        assert data["window_hours"] == 48
        assert data["packet_count_threshold"] == 5
        assert data["clear_threshold"] == 8
        assert data["max_hop_span"] == 4
        assert data["enabled"] is False
        assert data["reversible"] is False

    def test_update_duplicate_label_409(self, client_no_auth, api_db_session):
        self._make_route(api_db_session)
        api_db_session.add(Route(from_label="Other", to_label="Pair"))
        api_db_session.commit()
        other = api_db_session.query(Route).filter(Route.from_label == "Other").first()

        resp = client_no_auth.put(
            f"/api/v1/routes/{other.id}",
            json={"from_label": "OldFrom", "to_label": "OldTo"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 409

    def test_update_observers(self, client_no_auth, api_db_session):
        route = self._make_route(api_db_session)
        obs = _make_node(api_db_session, "c" * 64, "Observer")
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"observer_public_keys": [obs.public_key]},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["route_observers"]) == 1
        assert data["route_observers"][0]["public_key"] == obs.public_key

    def test_update_unresolved_path_nodes_400(self, client_no_auth, api_db_session):
        route = self._make_route(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={
                "node_public_keys": ["ff" + "0" * 62, "ee" + "0" * 62],
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 400

    def test_update_not_found(self, client_no_auth):
        resp = client_no_auth.put(
            "/api/v1/routes/nonexistent",
            json={"description": "x"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 404


class TestGetRouteVisibility:
    def test_hidden_route_404(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session,
            "Secret",
            "EP",
            ["aa" + "0" * 62, "bb" + "0" * 62],
            visibility="admin",
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 404

    def test_admin_sees_hidden_route(self, client_no_auth, api_db_session):
        route = _make_route_with_nodes(
            api_db_session,
            "Secret",
            "EP",
            ["aa" + "0" * 62, "bb" + "0" * 62],
            visibility="admin",
        )
        api_db_session.commit()

        resp = client_no_auth.get(
            f"/api/v1/routes/{route.id}",
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200

    def test_contributing_observers(self, client_no_auth, api_db_session):
        node_a = _make_node(api_db_session, "aa" + "0" * 62)
        node_b = _make_node(api_db_session, "bb" + "0" * 62)
        obs = _make_node(api_db_session, "cc" + "0" * 62, "Charlie")
        route = Route(from_label="A", to_label="B", match_width=1)
        api_db_session.add(route)
        api_db_session.flush()
        for pos, n in enumerate([node_a, node_b]):
            api_db_session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=derive_expected_hash(n.public_key, 1),
                )
            )
        _make_reception(
            api_db_session,
            observer_node_id=obs.id,
            packet_hash="pkt-contrib",
            path_hashes=["AA", "BB"],
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["contributing_observers"]) == 1
        assert data["contributing_observers"][0]["node_id"] == obs.id
        assert data["contributing_observers"][0]["match_count"] == 1
        assert len(data["recent_matches"]) == 1


class TestCreateWithObservers:
    def test_create_with_observers(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        obs = _make_node(api_db_session, "c" * 64, "Observer")
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "Alpha",
                "to_label": "Beta",
                "node_public_keys": [n.public_key for n in nodes],
                "observer_public_keys": [obs.public_key],
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["route_observers"]) == 1
        assert data["route_observers"][0]["public_key"] == obs.public_key


class TestPreviewGuards:
    def test_preview_unresolved_nodes(self, client_no_auth, api_db_session):
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes/preview",
            json={
                "node_public_keys": ["ff" + "0" * 62, "ee" + "0" * 62],
                "match_width": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched_count"] == 0
        assert data["quality"] == "unknown"
        assert data["state"] == "no_coverage"

    def test_preview_with_observers(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        obs = _make_node(api_db_session, "c" * 64, "Obs")
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes/preview",
            json={
                "node_public_keys": [n.public_key for n in nodes],
                "observer_public_keys": [obs.public_key],
                "match_width": 1,
                "window_hours": 24,
                "packet_count_threshold": 3,
            },
        )
        assert resp.status_code == 200


class TestPrecomputedRecentMatches:
    """``route_recent_matches`` table → detail-page read path.

    The 60s evaluator sweep persists top-3 matches as normalized rows
    (``route_id``, ``raw_packet_id``, ``first_position``, ``last_position``).
    The detail endpoint JOINs through ``raw_packets`` and slices the
    packet's hops on read, so the JSON shape stays identical to the
    legacy on-demand compute — but the data is sourced from its
    canonical home in ``packet_path_hops``.
    """

    def _seed_route_with_match(self, session) -> tuple[Route, str]:
        node_a = _make_node(session, "aa" + "0" * 62)
        node_b = _make_node(session, "bb" + "0" * 62)
        route = Route(
            from_label="Rm",
            to_label="Detail",
            packet_count_threshold=1,
            clear_threshold=2,
        )
        session.add(route)
        session.flush()
        for pos, n in enumerate([node_a, node_b]):
            session.add(
                RouteNode(
                    route_id=route.id,
                    node_id=n.id,
                    position=pos,
                    expected_hash=derive_expected_hash(n.public_key, 1),
                )
            )
        rp_id = _make_reception(
            session,
            observer_node_id=None,
            packet_hash="pkt-rm",
            path_hashes=["XX", "AA", "BB", "ZZ"],
        )
        session.commit()
        return route, rp_id

    def test_detail_reads_from_normalized_table(self, client_no_auth, api_db_session):
        """When the table is populated, the detail endpoint JOINs through
        ``raw_packets`` / ``packet_path_hops`` instead of computing live."""
        from meshcore_hub.common.models import RouteRecentMatch

        route, rp_id = self._seed_route_with_match(api_db_session)
        # Seed a normalized match row with the matched subpath positions
        # (indices 1..2 → ["AA", "BB"]).
        api_db_session.add(
            RouteRecentMatch(
                route_id=route.id,
                raw_packet_id=rp_id,
                first_position=1,
                last_position=2,
            )
        )
        api_db_session.commit()

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recent_matches"]) == 1
        match = data["recent_matches"][0]
        assert match["packet_hash"] == "pkt-rm"
        # Sliced subpath excludes the noise before/after the matched nodes.
        assert [h["node_hash"] for h in match["hops"]] == ["AA", "BB"]

    def test_detail_falls_back_to_live_when_table_empty(
        self, client_no_auth, api_db_session
    ):
        """When the table has no rows for the route (fresh, evaluator hasn't
        run yet), the detail endpoint computes matches live so the page
        still renders."""
        route, _rp_id = self._seed_route_with_match(api_db_session)
        # No RouteRecentMatch row — exercise the live fallback.

        resp = client_no_auth.get(f"/api/v1/routes/{route.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recent_matches"]) == 1
        match = data["recent_matches"][0]
        assert match["packet_hash"] == "pkt-rm"
        # Live path also slices the matched subpath.
        assert [h["node_hash"] for h in match["hops"]] == ["AA", "BB"]

    def test_put_persists_normalized_matches(self, client_no_auth, api_db_session):
        """PUT triggers ``_reevaluate_route`` which writes through the
        normalized table — the subsequent GET reads from there."""
        from sqlalchemy import select

        from meshcore_hub.common.models import RouteRecentMatch

        route, _rp_id = self._seed_route_with_match(api_db_session)
        # No rows yet.
        existing = (
            api_db_session.execute(
                select(RouteRecentMatch).where(RouteRecentMatch.route_id == route.id)
            )
            .scalars()
            .all()
        )
        assert existing == []

        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"description": "trigger reeval"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200

        # The synchronous re-evaluation on PUT should have written a
        # match row through ``upsert_route_recent_matches``.
        rows = (
            api_db_session.execute(
                select(RouteRecentMatch).where(RouteRecentMatch.route_id == route.id)
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].first_position == 1
        assert rows[0].last_position == 2
