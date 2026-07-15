"""Tests for route API endpoints."""

from datetime import datetime, timezone

from meshcore_hub.common.models import Node, Route, RouteNode


def _make_node(session, public_key: str, name: str | None = None) -> Node:
    node = Node(public_key=public_key, name=name, first_seen=datetime.now(timezone.utc))
    session.add(node)
    session.flush()
    return node


def _sample_nodes(session, count: int = 2) -> list[Node]:
    keys = [f"{chr(97 + i)}" * 64 for i in range(count)]
    return [_make_node(session, k, f"Node-{i}") for i, k in enumerate(keys)]


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
