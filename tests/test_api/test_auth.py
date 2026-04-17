"""Tests for API authentication.

Verifies that constant-time key comparison (hmac.compare_digest) works
correctly with no behavioral regressions from the original == operator.
"""

import base64


def _make_basic_auth(username: str, password: str) -> str:
    """Create a Basic auth header value."""
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {credentials}"


def _clear_metrics_cache() -> None:
    """Clear the metrics module cache."""
    from meshcore_hub.api.metrics import _cache

    _cache["output"] = b""
    _cache["expires_at"] = 0.0


class TestReadAuthentication:
    """Tests for read-level authentication (require_read)."""

    def test_no_auth_when_keys_not_configured(self, client_no_auth):
        """Test that no auth is required when keys are not configured."""
        # All endpoints should work without auth
        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200

        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200

    def test_read_endpoints_accept_read_key(self, client_with_auth):
        """Test that read endpoints accept read key."""
        response = client_with_auth.get(
            "/api/v1/nodes",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200

    def test_read_key_accepted_on_multiple_endpoints(self, client_with_auth):
        """Test that read key is accepted across different read endpoints."""
        for endpoint in ["/api/v1/nodes", "/api/v1/messages"]:
            response = client_with_auth.get(
                endpoint,
                headers={"Authorization": "Bearer test-read-key"},
            )
            assert response.status_code == 200, f"Read key rejected on {endpoint}"

    def test_read_endpoints_accept_admin_key(self, client_with_auth):
        """Test that admin key also grants read access."""
        response = client_with_auth.get(
            "/api/v1/nodes",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert response.status_code == 200

    def test_admin_key_grants_read_on_multiple_endpoints(self, client_with_auth):
        """Test that admin key grants read access across different endpoints."""
        for endpoint in ["/api/v1/nodes", "/api/v1/messages"]:
            response = client_with_auth.get(
                endpoint,
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert (
                response.status_code == 200
            ), f"Admin key rejected on read endpoint {endpoint}"

    def test_invalid_key_rejected_on_read_endpoint(self, client_with_auth):
        """Test that invalid keys are rejected with 401 on read endpoints."""
        response = client_with_auth.get(
            "/api/v1/nodes",
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert response.status_code == 401

    def test_no_auth_header_rejected_on_read_endpoint(self, client_with_auth):
        """Test that missing auth header is rejected on read endpoints."""
        response = client_with_auth.get("/api/v1/nodes")
        assert response.status_code == 401

    def test_missing_bearer_prefix_rejected(self, client_with_auth):
        """Test that tokens without Bearer prefix are rejected."""
        response = client_with_auth.get(
            "/api/v1/nodes",
            headers={"Authorization": "test-read-key"},
        )
        assert response.status_code == 401

    def test_empty_auth_header_rejected(self, client_with_auth):
        """Test that empty auth headers are rejected."""
        response = client_with_auth.get(
            "/api/v1/nodes",
            headers={"Authorization": ""},
        )
        assert response.status_code == 401


class TestAdminAuthentication:
    """Tests for admin-level authentication (require_admin)."""

    def test_admin_endpoints_accept_admin_key(self, client_with_auth):
        """Test that admin endpoints accept admin key."""
        response = client_with_auth.post(
            "/api/v1/nodes/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/tags",
            json={
                "tag_key": "name",
                "tag_value": "test-node",
            },
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert response.status_code in (200, 201, 404, 422)

    def test_admin_endpoints_reject_read_key(self, client_with_auth):
        """Test that admin endpoints reject read key with 403."""
        response = client_with_auth.post(
            "/api/v1/nodes/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/tags",
            json={
                "tag_key": "name",
                "tag_value": "test-node",
            },
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 403

    def test_admin_endpoints_reject_invalid_key(self, client_with_auth):
        """Test that admin endpoints reject invalid keys with 403."""
        response = client_with_auth.post(
            "/api/v1/nodes/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/tags",
            json={
                "tag_key": "name",
                "tag_value": "test-node",
            },
            headers={"Authorization": "Bearer completely-wrong-key"},
        )
        assert response.status_code == 403

    def test_admin_endpoints_reject_no_auth_header(self, client_with_auth):
        """Test that admin endpoints reject missing auth header with 401."""
        response = client_with_auth.post(
            "/api/v1/nodes/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/tags",
            json={
                "tag_key": "name",
                "tag_value": "test-node",
            },
        )
        assert response.status_code == 401


class TestMetricsAuthentication:
    """Tests for metrics endpoint authentication (Basic auth with hmac.compare_digest)."""

    def test_metrics_no_auth_when_no_read_key(self, client_no_auth):
        """Test that metrics requires no auth when no read key is configured."""
        _clear_metrics_cache()
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200

    def test_metrics_accepts_valid_basic_auth(self, client_with_auth):
        """Test that metrics accepts correct Basic credentials."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": _make_basic_auth("metrics", "test-read-key")},
        )
        assert response.status_code == 200

    def test_metrics_rejects_no_auth_when_key_set(self, client_with_auth):
        """Test 401 when read key is set but no auth provided."""
        _clear_metrics_cache()
        response = client_with_auth.get("/metrics")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_metrics_rejects_wrong_password(self, client_with_auth):
        """Test that metrics rejects incorrect password."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": _make_basic_auth("metrics", "wrong-key")},
        )
        assert response.status_code == 401

    def test_metrics_rejects_wrong_username(self, client_with_auth):
        """Test that metrics rejects incorrect username."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": _make_basic_auth("admin", "test-read-key")},
        )
        assert response.status_code == 401

    def test_metrics_rejects_bearer_auth(self, client_with_auth):
        """Test that Bearer auth does not work for metrics."""
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 401

    def test_metrics_rejects_admin_key_as_password(self, client_with_auth):
        """Test that admin key is not accepted as metrics password.

        Metrics uses only the read key for Basic auth, not the admin key.
        """
        _clear_metrics_cache()
        response = client_with_auth.get(
            "/metrics",
            headers={
                "Authorization": _make_basic_auth("metrics", "test-admin-key"),
            },
        )
        assert response.status_code == 401


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_no_auth(self, client_no_auth):
        """Test health endpoint without auth."""
        response = client_no_auth.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_with_auth_configured(self, client_with_auth):
        """Test health endpoint works even when auth is configured."""
        # Health endpoint should always be accessible
        response = client_with_auth.get("/health")
        assert response.status_code == 200
