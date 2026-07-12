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
        api_db_session.add(Route(name="Public", visibility="community"))
        api_db_session.add(Route(name="Secret", visibility="admin"))
        api_db_session.commit()

        resp = client_no_auth.get("/api/v1/routes")
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()["items"]]
        assert "Public" in names
        assert "Secret" not in names

    def test_admin_sees_all(self, client_no_auth, api_db_session):
        api_db_session.add(Route(name="Public", visibility="community"))
        api_db_session.add(Route(name="Secret", visibility="admin"))
        api_db_session.commit()

        resp = client_no_auth.get("/api/v1/routes", headers={"X-User-Roles": "admin"})
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()["items"]]
        assert "Public" in names
        assert "Secret" in names


class TestCreateRoute:
    def test_create_success(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "name": "Route1",
                "node_public_keys": [n.public_key for n in nodes],
                "match_width": 1,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Route1"
        assert len(data["route_nodes"]) == 2
        assert data["route_nodes"][0]["expected_hash"] is not None
        assert data["reversible"] is True

    def test_create_non_reversible(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "name": "OneWay",
                "node_public_keys": [n.public_key for n in nodes],
                "reversible": False,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        assert resp.json()["reversible"] is False

    def test_duplicate_name_rejected(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.add(Route(name="Dup"))
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={"name": "Dup", "node_public_keys": [n.public_key for n in nodes]},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 409

    def test_min_two_nodes(self, client_no_auth, api_db_session):
        node = _make_node(api_db_session, "a" * 64)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={"name": "R", "node_public_keys": [node.public_key]},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 422

    def test_distinct_nodes(self, client_no_auth, api_db_session):
        node = _make_node(api_db_session, "a" * 64)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={"name": "R", "node_public_keys": [node.public_key, node.public_key]},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 422

    def test_degraded_threshold_validation(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "name": "R",
                "node_public_keys": [n.public_key for n in nodes],
                "packet_count_threshold": 5,
                "degraded_threshold": 3,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 422

    def test_non_admin_rejected(self, client_with_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        api_db_session.commit()

        resp = client_with_auth.post(
            "/api/v1/routes",
            json={"name": "R", "node_public_keys": [n.public_key for n in nodes]},
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert resp.status_code == 403


class TestGetRouteDetail:
    def test_detail_shape(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session, 3)
        route = Route(name="R1")
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
        assert data["name"] == "R1"
        assert len(data["route_nodes"]) == 3
        assert "contributing_observers" in data
        assert "recent_matches" in data

    def test_not_found(self, client_no_auth):
        resp = client_no_auth.get("/api/v1/routes/nonexistent")
        assert resp.status_code == 404


class TestUpdateRoute:
    def test_update_name(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session)
        route = Route(name="OldName")
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
            json={"name": "NewName"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    def test_update_path_nodes(self, client_no_auth, api_db_session):
        nodes = _sample_nodes(api_db_session, 2)
        route = Route(name="R")
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
        route = Route(name="Bye")
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
