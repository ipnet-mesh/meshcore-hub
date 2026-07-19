"""Tests for API cache layer."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel

from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.common.redis import NullCache, RedisCacheBackend


class _SampleModel(BaseModel):
    items: list
    total: int


class TestSortedQueryString:
    def test_empty_query_params(self):
        scope = {"type": "http", "query_string": b"", "headers": []}
        request = Request(scope)
        assert sorted_query_string(request) == ""

    def test_single_param(self):
        scope = {"type": "http", "query_string": b"limit=50", "headers": []}
        request = Request(scope)
        assert sorted_query_string(request) == "limit=50"

    def test_multiple_params_sorted(self):
        scope = {
            "type": "http",
            "query_string": b"offset=0&limit=50",
            "headers": [],
        }
        request = Request(scope)
        result = sorted_query_string(request)
        assert result == "limit=50&offset=0"

    def test_url_encoded_special_chars(self):
        scope = {
            "type": "http",
            "query_string": b"search=foo+bar",
            "headers": [],
        }
        request = Request(scope)
        result = sorted_query_string(request)
        assert "search=" in result
        assert "foo" in result

    def test_repeated_param_preserves_all_values(self):
        # Repeated keys (e.g. observed_by) must all appear in the key; using
        # items() instead of multi_items() would drop all but the last value.
        scope = {
            "type": "http",
            "query_string": b"observed_by=A&observed_by=B",
            "headers": [],
        }
        request = Request(scope)
        result = sorted_query_string(request)
        assert "observed_by=A" in result
        assert "observed_by=B" in result

    def test_repeated_param_order_independent(self):
        # A&B and B&A describe the same OR filter and must map to one cache key.
        ab = Request(
            {
                "type": "http",
                "query_string": b"observed_by=A&observed_by=B",
                "headers": [],
            }
        )
        ba = Request(
            {
                "type": "http",
                "query_string": b"observed_by=B&observed_by=A",
                "headers": [],
            }
        )
        assert sorted_query_string(ab) == sorted_query_string(ba)

    def test_repeated_param_distinct_from_single(self):
        # The collision that caused the bug: {A, B} must not share a cache key
        # with {B} alone.
        both = Request(
            {
                "type": "http",
                "query_string": b"observed_by=A&observed_by=B",
                "headers": [],
            }
        )
        single = Request(
            {
                "type": "http",
                "query_string": b"observed_by=B",
                "headers": [],
            }
        )
        assert sorted_query_string(both) != sorted_query_string(single)


class TestNullCache:
    def test_get_returns_none(self):
        cache = NullCache()
        assert cache.get("any_key") is None

    def test_set_does_not_raise(self):
        cache = NullCache()
        cache.set("key", "value", 30)

    def test_ping_returns_false(self):
        cache = NullCache()
        assert cache.ping() is False

    def test_delete_does_not_raise(self):
        cache = NullCache()
        cache.delete("prefix")


class TestRedisCacheBackend:
    def test_get_returns_cached_value(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.get.return_value = b'{"items": []}'

            backend = RedisCacheBackend(key_prefix="hub")
            result = backend.get("nodes:limit=50")
            assert result == '{"items": []}'
            mock_client.get.assert_called_once_with("hub:nodes:limit=50")

    def test_get_returns_none_on_miss(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.get.return_value = None

            backend = RedisCacheBackend(key_prefix="hub")
            assert backend.get("nodes:limit=50") is None

    def test_set_stores_with_ttl(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client

            backend = RedisCacheBackend(key_prefix="hub")
            backend.set("nodes:limit=50", '{"items": []}', 30)
            mock_client.setex.assert_called_once_with(
                "hub:nodes:limit=50", 30, '{"items": []}'
            )

    def test_ping_returns_true(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.ping.return_value = True

            backend = RedisCacheBackend(key_prefix="hub")
            assert backend.ping() is True

    def test_ping_returns_false_on_error(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.ping.side_effect = Exception("connection refused")

            backend = RedisCacheBackend(key_prefix="hub")
            assert backend.ping() is False

    def test_get_returns_none_on_connection_error(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("connection error")

            backend = RedisCacheBackend(key_prefix="hub")
            assert backend.get("any_key") is None

    def test_set_logs_warning_on_error(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.setex.side_effect = Exception("timeout")

            backend = RedisCacheBackend(key_prefix="hub")
            backend.set("key", "value", 30)
            # Should not raise

    def test_key_prefix_prepended(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.get.return_value = None

            backend = RedisCacheBackend(key_prefix="hub-stg")
            backend.get("nodes:")
            mock_client.get.assert_called_once_with("hub-stg:nodes:")

    def test_get_decodes_str_value(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.get.return_value = '{"already": "str"}'

            backend = RedisCacheBackend(key_prefix="hub")
            result = backend.get("key")
            assert result == '{"already": "str"}'

    def test_delete_scans_and_deletes_keys(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.return_value = (0, [b"hub:nodes:1", b"hub:nodes:2"])

            backend = RedisCacheBackend(key_prefix="hub")
            backend.delete("nodes")
            mock_client.scan.assert_called_once_with(0, match="hub:nodes*", count=100)
            mock_client.delete.assert_called_once_with(b"hub:nodes:1", b"hub:nodes:2")

    def test_delete_multi_page_scan(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.side_effect = [
                (42, [b"hub:nodes:1"]),
                (0, [b"hub:nodes:2"]),
            ]

            backend = RedisCacheBackend(key_prefix="hub")
            backend.delete("nodes")
            assert mock_client.scan.call_count == 2
            assert mock_client.delete.call_count == 2

    def test_delete_handles_exception(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.side_effect = Exception("scan error")

            backend = RedisCacheBackend(key_prefix="hub")
            backend.delete("nodes")

    def test_close_calls_client_close(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client

            backend = RedisCacheBackend(key_prefix="hub")
            backend.close()
            mock_client.close.assert_called_once()

    def test_close_handles_exception(self):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.close.side_effect = Exception("close error")

            backend = RedisCacheBackend(key_prefix="hub")
            backend.close()


class TestCachedDecorator:
    async def test_cache_hit_returns_cached_data(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = json.dumps({"items": [], "total": 0})
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["should not appear"], "total": 1}

        scope = {
            "type": "http",
            "query_string": b"limit=50",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == {"items": [], "total": 0}
        assert request.state.cache_status == "HIT"

    async def test_cache_miss_calls_handler(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["real"], "total": 1}

        scope = {
            "type": "http",
            "query_string": b"limit=50",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == {"items": ["real"], "total": 1}
        assert request.state.cache_status == "MISS"
        mock_cache.set.assert_called_once()

    async def test_null_cache_always_calls_handler(self):
        app = FastAPI()
        app.state.redis_cache = NullCache()
        app.state.redis_cache_ttl = 30

        call_count = 0

        @cached("nodes")
        async def handler(request: Request):
            nonlocal call_count
            call_count += 1
            return {"items": [], "total": 0}

        scope = {
            "type": "http",
            "query_string": b"limit=50",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        await handler(request=request)
        await handler(request=request)
        assert call_count == 2

    async def test_redis_error_falls_through(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.side_effect = Exception("redis down")
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["fallback"], "total": 1}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == {"items": ["fallback"], "total": 1}

    async def test_no_request_raises_error(self):
        @cached("nodes")
        async def handler():
            return {"items": []}

        with pytest.raises(TypeError, match="No Request"):
            await handler()

    async def test_custom_key_builder(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        def role_key_builder(request: Request) -> str:
            role = request.headers.get("x-user-roles", "anonymous")
            return f"messages:role={role}:"

        @cached("messages", key_builder=role_key_builder)
        async def handler(request: Request):
            return {"items": []}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [(b"x-user-roles", b"admin")],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        await handler(request=request)
        mock_cache.get.assert_called_once_with("messages:role=admin:")

    async def test_dashboard_ttl_override(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30
        app.state.redis_cache_ttl_dashboard = 60

        @cached("dashboard/stats", ttl_setting="redis_cache_ttl_dashboard")
        async def handler(request: Request):
            return {"total_nodes": 10}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        await handler(request=request)
        call_args = mock_cache.set.call_args
        assert call_args[0][2] == 60  # TTL should be 60, not 30

    async def test_route_detail_ttl_override(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30
        app.state.redis_cache_ttl_dashboard = 90

        @cached("routes/{id}", ttl_setting="redis_cache_ttl_dashboard")
        async def handler(request: Request):
            return {"id": "abc", "matches": []}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        await handler(request=request)
        call_args = mock_cache.set.call_args
        assert call_args[0][2] == 90  # TTL should be 90, not 30

    async def test_serializes_pydantic_model_result(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return _SampleModel(items=[1, 2], total=2)

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result.items == [1, 2]
        set_call = mock_cache.set.call_args
        envelope = json.loads(set_call[0][1])
        assert envelope["body"] == {"items": [1, 2], "total": 2}
        assert isinstance(envelope["etag"], str)
        assert envelope["etag"].startswith('"')

    async def test_serializes_dict_result(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"key": "value"}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == {"key": "value"}
        set_call = mock_cache.set.call_args
        envelope = json.loads(set_call[0][1])
        assert envelope["body"] == {"key": "value"}
        assert isinstance(envelope["etag"], str)

    async def test_serializes_other_result_with_default_str(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return ["a", "b"]

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == ["a", "b"]
        set_call = mock_cache.set.call_args
        envelope = json.loads(set_call[0][1])
        assert envelope["body"] == ["a", "b"]

    async def test_cache_set_error_falls_through(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception("set error")
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["ok"]}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == {"items": ["ok"]}

    async def test_no_cache_on_app_state_calls_handler(self):
        app = FastAPI()

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["direct"]}

        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()

        result = await handler(request=request)
        assert result == {"items": ["direct"]}


class TestCachedEtag:
    """ETag / If-None-Match behavior of @cached."""

    @staticmethod
    def _make_request(app, headers=None):
        scope = {
            "type": "http",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or [])],
            "app": app,
        }
        from starlette.datastructures import State

        request = Request(scope)
        request._state = State()
        return request

    async def test_miss_sets_request_state_etag(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["a"], "total": 1}

        request = self._make_request(app)
        result = await handler(request=request)
        assert result == {"items": ["a"], "total": 1}
        etag = request.state.api_etag
        assert isinstance(etag, str)
        assert etag.startswith('"')

    async def test_hit_reads_etag_from_envelope(self):
        app = FastAPI()
        mock_cache = MagicMock()
        body = {"items": [], "total": 0}
        etag = '"deadbeefdeadbeefdeadbeefdeadbeef"'
        mock_cache.get.return_value = json.dumps({"body": body, "etag": etag})
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["should not appear"], "total": 1}

        request = self._make_request(app)
        result = await handler(request=request)
        assert result == body
        assert request.state.api_etag == etag
        assert request.state.cache_status == "HIT"

    async def test_hit_computes_etag_for_legacy_entry(self):
        """Legacy bare-JSON cache entries (no etag envelope) still serve and
        get an ETag computed on the fly."""
        app = FastAPI()
        mock_cache = MagicMock()
        body = {"items": [], "total": 0}
        mock_cache.get.return_value = json.dumps(body)
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["should not appear"], "total": 1}

        request = self._make_request(app)
        result = await handler(request=request)
        assert result == body
        assert request.state.cache_status == "HIT"
        # ETag is computed deterministically from the legacy body bytes.
        assert request.state.api_etag.startswith('"')

    async def test_garbage_cache_entry_treated_as_miss(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = "not valid json {"
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["real"], "total": 1}

        request = self._make_request(app)
        result = await handler(request=request)
        assert result == {"items": ["real"], "total": 1}
        assert request.state.cache_status == "MISS"

    async def test_if_none_match_returns_304_on_miss(self):
        app = FastAPI()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["a"], "total": 1}

        # First call to learn the ETag.
        request = self._make_request(app)
        await handler(request=request)
        etag = request.state.api_etag

        # Second call with matching If-None-Match.
        request2 = self._make_request(app, headers=[("if-none-match", etag)])
        response = await handler(request=request2)
        from fastapi.responses import Response

        assert isinstance(response, Response)
        assert response.status_code == 304
        assert response.headers["ETag"] == etag

    async def test_if_none_match_returns_304_on_hit(self):
        app = FastAPI()
        mock_cache = MagicMock()
        body = {"items": [], "total": 0}
        etag = '"abc123abc123abc123abc123abc123ab"'
        mock_cache.get.return_value = json.dumps({"body": body, "etag": etag})
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["should not appear"], "total": 1}

        request = self._make_request(app, headers=[("if-none-match", etag)])
        response = await handler(request=request)
        from fastapi.responses import Response

        assert isinstance(response, Response)
        assert response.status_code == 304
        assert response.headers["ETag"] == etag

    async def test_if_none_match_non_matching_returns_body(self):
        app = FastAPI()
        mock_cache = MagicMock()
        body = {"items": [], "total": 0}
        etag = '"abc123abc123abc123abc123abc123ab"'
        mock_cache.get.return_value = json.dumps({"body": body, "etag": etag})
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["should not appear"], "total": 1}

        request = self._make_request(
            app, headers=[("if-none-match", '"different-etag-value"')]
        )
        result = await handler(request=request)
        assert result == body

    async def test_if_none_match_wildcard_matches_any_etag(self):
        app = FastAPI()
        mock_cache = MagicMock()
        body = {"items": [], "total": 0}
        etag = '"abc123abc123abc123abc123abc123ab"'
        mock_cache.get.return_value = json.dumps({"body": body, "etag": etag})
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["nope"], "total": 1}

        request = self._make_request(app, headers=[("if-none-match", "*")])
        from fastapi.responses import Response

        response = await handler(request=request)
        assert isinstance(response, Response)
        assert response.status_code == 304

    async def test_if_none_match_accepts_weak_indicator(self):
        app = FastAPI()
        mock_cache = MagicMock()
        body = {"items": [], "total": 0}
        etag = '"abc123abc123abc123abc123abc123ab"'
        mock_cache.get.return_value = json.dumps({"body": body, "etag": etag})
        app.state.redis_cache = mock_cache
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": ["nope"], "total": 1}

        request = self._make_request(app, headers=[("if-none-match", f"W/{etag}")])
        from fastapi.responses import Response

        response = await handler(request=request)
        assert isinstance(response, Response)
        assert response.status_code == 304

    async def test_cache_control_ttl_always_set(self):
        """Even when Redis is NullCache, request.state.cache_control_ttl
        is set so the middleware can emit Cache-Control."""
        app = FastAPI()
        app.state.redis_cache = NullCache()
        app.state.redis_cache_ttl = 30

        @cached("nodes")
        async def handler(request: Request):
            return {"items": [], "total": 0}

        request = self._make_request(app)
        await handler(request=request)
        assert request.state.cache_control_ttl == 30

    async def test_cache_control_ttl_uses_overridden_setting(self):
        app = FastAPI()
        app.state.redis_cache = NullCache()
        app.state.redis_cache_ttl = 30
        app.state.redis_cache_ttl_dashboard = 90

        @cached("routes/{id}", ttl_setting="redis_cache_ttl_dashboard")
        async def handler(request: Request):
            return {"id": "abc"}

        request = self._make_request(app)
        await handler(request=request)
        assert request.state.cache_control_ttl == 90


class TestCachedEtagHelpers:
    """Direct unit tests for the etag helpers."""

    def test_compute_etag_is_quoted_hex(self):
        from meshcore_hub.api.cache import _compute_etag

        etag = _compute_etag('{"a": 1}')
        assert etag.startswith('"')
        assert etag.endswith('"')
        assert len(etag) == 34  # 32 hex chars + 2 quotes

    def test_compute_etag_is_deterministic(self):
        from meshcore_hub.api.cache import _compute_etag

        assert _compute_etag("body") == _compute_etag("body")

    def test_compute_etag_changes_with_input(self):
        from meshcore_hub.api.cache import _compute_etag

        assert _compute_etag("body1") != _compute_etag("body2")

    def test_etag_matches_strong_equality(self):
        from meshcore_hub.api.cache import _etag_matches

        etag = '"abc123"'
        assert _etag_matches('"abc123"', etag)

    def test_etag_matches_wildcard(self):
        from meshcore_hub.api.cache import _etag_matches

        assert _etag_matches("*", '"any"')

    def test_etag_matches_weak_indicator(self):
        from meshcore_hub.api.cache import _etag_matches

        etag = '"abc123"'
        assert _etag_matches('W/"abc123"', etag)

    def test_etag_matches_one_of_list(self):
        from meshcore_hub.api.cache import _etag_matches

        etag = '"abc123"'
        assert _etag_matches('"xyz", "abc123", "def"', etag)

    def test_etag_no_match(self):
        from meshcore_hub.api.cache import _etag_matches

        assert not _etag_matches('"other"', '"abc123"')


class TestCacheControlMiddleware:
    """End-to-end Cache-Control / ETag tests via the FastAPI test client."""

    def test_cached_get_emits_cache_control_and_etag(self, client_no_auth):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30
        response = client_no_auth.get("/api/v1/nodes")
        assert response.status_code == 200
        # no-cache (must-revalidate) — see api/app.py middleware docstring.
        # The Redis TTL still flows to cache.set(...); only HTTP max-age is
        # dropped so server-side invalidation can reach the browser.
        assert response.headers["cache-control"] == "private, no-cache"
        assert "etag" in response.headers

    def test_cached_get_ttl_flows_to_redis_not_http(self, client_no_auth):
        """Route detail endpoint's TTL must drive cache.set, not Cache-Control.

        Regression: previously the per-endpoint TTL (e.g. 300s for
        ``/routes/{id}``) was emitted as ``Cache-Control: max-age=300``,
        which let the browser serve stale data for 5 min after a mutation.
        The TTL now only bounds the Redis cache lifetime; HTTP-layer is
        always ``private, no-cache`` so the browser revalidates and the
        server-side invalidation wins.
        """
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30
        client_no_auth.app.state.redis_cache_ttl_dashboard = 300
        # Hit the route detail endpoint with a fake id. The endpoint returns
        # 404 but still flows through the @cached decorator; we only care
        # that the TTL is NOT surfaced as an HTTP header.
        response = client_no_auth.get("/api/v1/routes/nonexistent-id")
        assert response.headers.get("cache-control") == "private, no-cache"

    def test_cached_get_304_on_matching_if_none_match(self, client_no_auth):
        mock_cache = MagicMock()
        body = {
            "items": [],
            "total": 0,
            "limit": 50,
            "offset": 0,
        }
        etag = '"abc123abc123abc123abc123abc123ab"'
        mock_cache.get.return_value = json.dumps({"body": body, "etag": etag})
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30

        response = client_no_auth.get("/api/v1/nodes", headers={"If-None-Match": etag})
        assert response.status_code == 304
        assert response.headers["ETag"] == etag
        assert response.headers["cache-control"] == "private, no-cache"
        assert response.headers["x-cache"] == "HIT"
        # 304 must not carry a body.
        assert response.content in (b"", b"null")

    def test_uncached_get_emits_no_cache(self, client_no_auth, sample_node):
        """Uncached GET detail endpoints get the same no-cache policy."""
        # Force the @cached list endpoint to NOT be the target by hitting the
        # per-id endpoint, which is not cached.
        if hasattr(client_no_auth.app.state, "redis_cache"):
            del client_no_auth.app.state.redis_cache
        response = client_no_auth.get(f"/api/v1/nodes/{sample_node.public_key}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-cache"

    def test_post_emits_no_store(self, client_no_auth, api_db_session):
        """POST endpoints always get Cache-Control: no-store.

        Depends on ``api_db_session`` so its teardown truncates the channel
        row even if the create succeeds (channel creates mutate the DB and
        would otherwise leak into later tests in the same module).
        """
        response = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "CacheControlTestChan",
                "key_hex": "AABBCCDDEEFF00112233445566778899",
                "visibility": "community",
            },
        )
        # May succeed (201) or fail (400/500) depending on validation; we
        # only care that the middleware set no-store on the response.
        assert response.headers["cache-control"] == "no-store"

    def test_health_emits_no_store(self, client_no_auth):
        response = client_no_auth.get("/health")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    def test_health_ready_emits_no_store(self, client_no_auth):
        response = client_no_auth.get("/health/ready")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    def test_kill_switch_suppresses_cache_control(self, client_no_auth):
        """When api_cache_control_enabled is False, no Cache-Control is added."""
        client_no_auth.app.state.api_cache_control_enabled = False
        if hasattr(client_no_auth.app.state, "redis_cache"):
            del client_no_auth.app.state.redis_cache
        response = client_no_auth.get("/api/v1/nodes")
        assert "cache-control" not in response.headers

    def test_kill_switch_preserves_x_cache_header(self, client_no_auth):
        """X-Cache is observability, not a client-caching directive, so the
        kill switch should not suppress it."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30
        client_no_auth.app.state.api_cache_control_enabled = False
        response = client_no_auth.get("/api/v1/nodes")
        assert response.headers.get("x-cache") == "MISS"
        assert "cache-control" not in response.headers


class TestLifespanRedis:
    async def test_lifespan_creates_null_cache_when_disabled(self):
        import meshcore_hub.api.app as app_module
        from meshcore_hub.api.app import lifespan

        app = FastAPI()
        app.state.database_url = "sqlite:///./test.db"
        app.state.redis_enabled = False
        app_module._db_manager = None

        with patch.object(app_module, "DatabaseManager", return_value=MagicMock()):
            async with lifespan(app):
                assert isinstance(app.state.redis_cache, NullCache)

    async def test_lifespan_creates_redis_cache_when_enabled(self):
        import meshcore_hub.api.app as app_module
        from meshcore_hub.api.app import lifespan

        app = FastAPI()
        app.state.database_url = "sqlite:///./test.db"
        app.state.redis_enabled = True
        app.state.redis_host = "redis-host"
        app.state.redis_port = 6380
        app.state.redis_db = 1
        app.state.redis_password = "secret"
        app.state.redis_key_prefix = "myprefix"
        app_module._db_manager = None

        with patch.object(app_module, "DatabaseManager", return_value=MagicMock()):
            with patch("meshcore_hub.common.redis.RedisCacheBackend") as mock_cls:
                mock_instance = MagicMock()
                mock_cls.return_value = mock_instance
                async with lifespan(app):
                    mock_cls.assert_called_once_with(
                        host="redis-host",
                        port=6380,
                        db=1,
                        password="secret",
                        key_prefix="myprefix",
                    )
                    assert app.state.redis_cache is mock_instance

    async def test_lifespan_closes_cache_on_shutdown(self):
        import meshcore_hub.api.app as app_module
        from meshcore_hub.api.app import lifespan

        app = FastAPI()
        app.state.database_url = "sqlite:///./test.db"
        app.state.redis_enabled = True

        mock_cache = MagicMock()
        mock_db_manager = MagicMock()
        app_module._db_manager = None

        with patch.object(app_module, "DatabaseManager", return_value=mock_db_manager):
            with patch(
                "meshcore_hub.common.redis.RedisCacheBackend",
                return_value=mock_cache,
            ):
                async with lifespan(app):
                    pass
                mock_cache.close.assert_called_once()
                mock_db_manager.dispose.assert_called_once()


class TestXCacheMiddleware:
    def test_adds_x_cache_header_on_hit(self, client_no_auth):
        mock_cache = MagicMock()
        mock_cache.get.return_value = json.dumps(
            {"items": [], "total": 0, "limit": 50, "offset": 0}
        )
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30
        response = client_no_auth.get("/api/v1/nodes")
        assert response.headers.get("x-cache") == "HIT"

    def test_adds_x_cache_header_on_miss(self, client_no_auth):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30
        response = client_no_auth.get("/api/v1/nodes")
        assert response.headers.get("x-cache") == "MISS"

    def test_no_x_cache_header_when_no_cache_status(self, client_no_auth):
        if hasattr(client_no_auth.app.state, "redis_cache"):
            del client_no_auth.app.state.redis_cache
        response = client_no_auth.get("/api/v1/nodes")
        assert "x-cache" not in response.headers


class TestHealthReadyRedis:
    def test_health_ready_omits_redis_when_disabled(self, client_no_auth):
        if hasattr(client_no_auth.app.state, "redis_cache"):
            del client_no_auth.app.state.redis_cache
        client_no_auth.app.state.redis_enabled = False
        response = client_no_auth.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "redis" not in data

    def test_health_ready_reports_connected(self, client_no_auth):
        mock_cache = MagicMock()
        mock_cache.ping.return_value = True
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_enabled = True
        response = client_no_auth.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["redis"] == "connected"

    def test_health_ready_reports_unreachable(self, client_no_auth):
        mock_cache = MagicMock()
        mock_cache.ping.return_value = False
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_enabled = True
        response = client_no_auth.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["redis"] == "unreachable"


class TestCliRedis:
    def test_redis_enabled_shows_banner(self):
        from click.testing import CliRunner

        from meshcore_hub.api.cli import api

        runner = CliRunner()
        with patch("uvicorn.run"):
            with patch("meshcore_hub.common.config.get_api_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    data_home="/tmp/test",
                    effective_database_url="sqlite:///test.db",
                )
                result = runner.invoke(
                    api,
                    ["--redis-enabled", "--redis-host", "myredis"],
                    catch_exceptions=False,
                )
                assert "Redis enabled: True" in result.output
                assert "Redis: myredis:6379/0" in result.output
                assert "Redis key prefix: hub" in result.output

    def test_redis_disabled_hides_details(self):
        from click.testing import CliRunner

        from meshcore_hub.api.cli import api

        runner = CliRunner()
        with patch("uvicorn.run"):
            with patch("meshcore_hub.common.config.get_api_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    data_home="/tmp/test",
                    effective_database_url="sqlite:///test.db",
                )
                result = runner.invoke(api, catch_exceptions=False)
                assert "Redis enabled: False" in result.output
                assert "Redis:" not in result.output.replace("Redis enabled: False", "")

    def test_redis_params_passed_to_create_app(self):
        from click.testing import CliRunner

        from meshcore_hub.api.cli import api

        runner = CliRunner()
        with patch("uvicorn.run"):
            with patch("meshcore_hub.common.config.get_api_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    data_home="/tmp/test",
                    effective_database_url="sqlite:///test.db",
                )
                with patch("meshcore_hub.api.app.create_app") as mock_create_app:
                    mock_create_app.return_value = MagicMock()
                    runner.invoke(
                        api,
                        [
                            "--redis-enabled",
                            "--redis-host",
                            "rhost",
                            "--redis-port",
                            "6380",
                            "--redis-db",
                            "2",
                            "--redis-password",
                            "pw",
                            "--redis-key-prefix",
                            "pre",
                            "--redis-cache-ttl",
                            "60",
                            "--redis-cache-ttl-dashboard",
                            "120",
                            "--no-api-cache-control",
                        ],
                        catch_exceptions=False,
                    )
                    call_kwargs = mock_create_app.call_args[1]
                    assert call_kwargs["redis_enabled"] is True
                    assert call_kwargs["redis_host"] == "rhost"
                    assert call_kwargs["redis_port"] == 6380
                    assert call_kwargs["redis_db"] == 2
                    assert call_kwargs["redis_password"] == "pw"
                    assert call_kwargs["redis_key_prefix"] == "pre"
                    assert call_kwargs["redis_cache_ttl"] == 60
                    assert call_kwargs["redis_cache_ttl_dashboard"] == 120
                    assert call_kwargs["api_cache_control_enabled"] is False

    def test_api_cache_control_enabled_default(self):
        """Without --no-api-cache-control, the flag defaults to True."""
        from click.testing import CliRunner

        from meshcore_hub.api.cli import api

        runner = CliRunner()
        with patch("uvicorn.run"):
            with patch("meshcore_hub.common.config.get_api_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    data_home="/tmp/test",
                    effective_database_url="sqlite:///test.db",
                )
                with patch("meshcore_hub.api.app.create_app") as mock_create_app:
                    mock_create_app.return_value = MagicMock()
                    runner.invoke(api, catch_exceptions=False)
                    call_kwargs = mock_create_app.call_args[1]
                    assert call_kwargs["api_cache_control_enabled"] is True

    def test_redis_cache_ttl_dashboard_default(self):
        """--redis-cache-ttl-dashboard defaults to 3600 (1 hour).

        Covers /dashboard/* endpoints, /routes/{id} detail, and
        /routes/{id}/history. Trend/aggregation data tolerates much longer
        staleness than the default 30 s TTL — Recent Adverts / Recent
        Channel Messages widgets were split into /dashboard/recent-activity
        so they can stay on the short default TTL independently.
        """
        from click.testing import CliRunner

        from meshcore_hub.api.cli import api

        runner = CliRunner()
        with patch("uvicorn.run"):
            with patch("meshcore_hub.common.config.get_api_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    data_home="/tmp/test",
                    effective_database_url="sqlite:///test.db",
                )
                with patch("meshcore_hub.api.app.create_app") as mock_create_app:
                    mock_create_app.return_value = MagicMock()
                    runner.invoke(api, catch_exceptions=False)
                    call_kwargs = mock_create_app.call_args[1]
                    assert call_kwargs["redis_cache_ttl_dashboard"] == 3600


class TestKeyBuilders:
    def test_dashboard_stats_key_builder(self):
        from meshcore_hub.api.routes.dashboard import _dashboard_stats_key_builder

        with patch(
            "meshcore_hub.api.routes.dashboard.resolve_user_role",
            return_value="admin",
        ):
            scope = {
                "type": "http",
                "query_string": b"days=30",
                "headers": [],
            }
            request = Request(scope)
            key = _dashboard_stats_key_builder(request)
            assert key == "dashboard/stats:role=admin:days=30"

    def test_dashboard_stats_key_builder_anonymous(self):
        from meshcore_hub.api.routes.dashboard import _dashboard_stats_key_builder

        with patch(
            "meshcore_hub.api.routes.dashboard.resolve_user_role",
            return_value=None,
        ):
            scope = {
                "type": "http",
                "query_string": b"",
                "headers": [],
            }
            request = Request(scope)
            key = _dashboard_stats_key_builder(request)
            assert "role=anonymous" in key

    def test_dashboard_msg_activity_key_builder(self):
        from meshcore_hub.api.routes.dashboard import (
            _dashboard_msg_activity_key_builder,
        )

        with patch(
            "meshcore_hub.api.routes.dashboard.resolve_user_role",
            return_value="member",
        ):
            scope = {
                "type": "http",
                "query_string": b"days=7",
                "headers": [],
            }
            request = Request(scope)
            key = _dashboard_msg_activity_key_builder(request)
            assert key == "dashboard/message-activity:role=member:days=7"

    def test_channels_key_builder(self):
        from meshcore_hub.api.routes.channels import _channels_key_builder

        with patch(
            "meshcore_hub.api.routes.channels.resolve_user_role",
            return_value="operator",
        ):
            scope = {
                "type": "http",
                "query_string": b"",
                "headers": [],
            }
            request = Request(scope)
            key = _channels_key_builder(request)
            assert key == "channels:role=operator:"

    def test_channels_key_builder_anonymous(self):
        from meshcore_hub.api.routes.channels import _channels_key_builder

        with patch(
            "meshcore_hub.api.routes.channels.resolve_user_role",
            return_value=None,
        ):
            scope = {
                "type": "http",
                "query_string": b"",
                "headers": [],
            }
            request = Request(scope)
            key = _channels_key_builder(request)
            assert "role=anonymous" in key

    def test_messages_key_builder(self):
        from meshcore_hub.api.routes.messages import _messages_key_builder

        with patch(
            "meshcore_hub.api.routes.messages.resolve_user_role",
            return_value="admin",
        ):
            scope = {
                "type": "http",
                "query_string": b"limit=10&offset=0",
                "headers": [],
            }
            request = Request(scope)
            key = _messages_key_builder(request)
            assert "role=admin" in key
            assert "limit=10" in key


def _make_request_with_cache(cache):
    """Build a Request whose ``app.state.redis_cache`` is *cache* (or absent)."""
    app = FastAPI()
    if cache is not None:
        app.state.redis_cache = cache
    return Request(
        scope={"type": "http", "query_string": b"", "headers": [], "app": app}
    )


class TestCacheInvalidationHelpers:
    """Unit tests for ``meshcore_hub.api.cache_invalidation`` helpers."""

    def test_invalidate_channels_drops_url_path_prefix(self):
        from meshcore_hub.api.cache_invalidation import invalidate_channels

        cache = MagicMock()
        invalidate_channels(_make_request_with_cache(cache))
        cache.delete.assert_called_once_with("/api/v1/channels")

    def test_invalidate_routes_drops_url_path_prefix(self):
        from meshcore_hub.api.cache_invalidation import invalidate_routes

        cache = MagicMock()
        invalidate_routes(_make_request_with_cache(cache))
        # Two prefixes: /api/v1/routes covers the list, detail, and history
        # endpoints (URL-path key_builder); dashboard/routes-overview covers
        # the dashboard aggregate (endpoint-name key namespace).
        assert cache.delete.call_count == 2
        cache.delete.assert_any_call("/api/v1/routes")
        cache.delete.assert_any_call("dashboard/routes-overview")

    def test_invalidate_nodes_drops_endpoint_name_prefix(self):
        from meshcore_hub.api.cache_invalidation import invalidate_nodes

        cache = MagicMock()
        invalidate_nodes(_make_request_with_cache(cache))
        cache.delete.assert_called_once_with("nodes")

    def test_invalidate_profiles_drops_endpoint_name_prefix(self):
        from meshcore_hub.api.cache_invalidation import invalidate_profiles

        cache = MagicMock()
        invalidate_profiles(_make_request_with_cache(cache))
        cache.delete.assert_called_once_with("profiles")

    def test_invalidate_messages_drops_url_path_prefix(self):
        from meshcore_hub.api.cache_invalidation import invalidate_messages

        cache = MagicMock()
        invalidate_messages(_make_request_with_cache(cache))
        cache.delete.assert_called_once_with("/api/v1/messages")

    def test_invalidate_advertisements_drops_endpoint_name_prefix(self):
        from meshcore_hub.api.cache_invalidation import invalidate_advertisements

        cache = MagicMock()
        invalidate_advertisements(_make_request_with_cache(cache))
        cache.delete.assert_called_once_with("advertisements")

    def test_invalidate_dashboard_drops_both_prefix_formats(self):
        from meshcore_hub.api.cache_invalidation import invalidate_dashboard

        cache = MagicMock()
        invalidate_dashboard(_make_request_with_cache(cache))
        # Dashboard endpoints split between endpoint-name keys and URL-path keys
        cache.delete.assert_any_call("dashboard")
        cache.delete.assert_any_call("/api/v1/dashboard")
        assert cache.delete.call_count == 2

    def test_helpers_are_noop_when_cache_missing(self):
        # No redis_cache attribute on state — must not raise.
        from meshcore_hub.api import cache_invalidation as inv

        request = _make_request_with_cache(cache=None)
        inv.invalidate_channels(request)
        inv.invalidate_routes(request)
        inv.invalidate_nodes(request)
        inv.invalidate_profiles(request)
        inv.invalidate_messages(request)
        inv.invalidate_advertisements(request)
        inv.invalidate_dashboard(request)

    def test_helpers_swallow_backend_errors(self):
        from meshcore_hub.api import cache_invalidation as inv

        cache = MagicMock()
        cache.delete.side_effect = Exception("redis down")
        request = _make_request_with_cache(cache)
        # Must not raise.
        inv.invalidate_channels(request)
        inv.invalidate_dashboard(request)


class TestMutationInvalidationIntegration:
    """End-to-end: mutation handlers must drop the expected cache prefixes."""

    def _install_mock_cache(self, client) -> MagicMock:
        """Attach a mock cache that always misses; return it for assertions."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client.app.state.redis_cache = mock_cache
        client.app.state.redis_cache_ttl = 30
        client.app.state.redis_cache_ttl_dashboard = 300
        return mock_cache

    # --- Channels ---------------------------------------------------------

    def test_create_channel_invalidates_channels(self, client_no_auth, api_db_session):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.post(
            "/api/v1/channels",
            json={
                "name": "InvalidationTest",
                "key_hex": "AABBCCDDEEFF00112233445566778899",
                "visibility": "community",
                "enabled": True,
            },
        )
        assert resp.status_code == 201
        mock_cache.delete.assert_any_call("/api/v1/channels")

    def test_update_channel_invalidates_channels(self, client_no_auth, sample_channel):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.put(
            f"/api/v1/channels/{sample_channel.id}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        mock_cache.delete.assert_any_call("/api/v1/channels")

    def test_delete_channel_invalidates_channels(self, client_no_auth, sample_channel):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.delete(f"/api/v1/channels/{sample_channel.id}")
        assert resp.status_code == 204
        mock_cache.delete.assert_any_call("/api/v1/channels")

    # --- Routes -----------------------------------------------------------

    def test_create_route_invalidates_routes(self, client_no_auth, api_db_session):
        from meshcore_hub.common.models import Node

        n1 = Node(public_key="aa" * 16, name="A")
        n2 = Node(public_key="bb" * 16, name="B")
        api_db_session.add_all([n1, n2])
        api_db_session.commit()

        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.post(
            "/api/v1/routes",
            json={
                "from_label": "A",
                "to_label": "B",
                "node_public_keys": [n1.public_key, n2.public_key],
                "match_width": 2,
            },
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 201
        mock_cache.delete.assert_any_call("/api/v1/routes")
        # Dashboard routes-overview embeds per-route state, so it must be
        # dropped too — otherwise the new route stays invisible on the
        # dashboard until TTL expiry.
        mock_cache.delete.assert_any_call("dashboard/routes-overview")

    def test_update_route_invalidates_routes(self, client_no_auth, api_db_session):
        from meshcore_hub.common.models import Node, Route, RouteNode

        nodes = [Node(public_key=f"{c:02x}" * 16, name=str(c)) for c in (1, 2)]
        api_db_session.add_all(nodes)
        api_db_session.flush()
        route = Route(from_label="X", to_label="Y")
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

        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"from_label": "NewFrom", "to_label": "NewTo"},
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 200
        mock_cache.delete.assert_any_call("/api/v1/routes")
        mock_cache.delete.assert_any_call("dashboard/routes-overview")

    def test_delete_route_invalidates_routes(self, client_no_auth, api_db_session):
        from meshcore_hub.common.models import Node, Route, RouteNode

        nodes = [Node(public_key=f"{c:02x}" * 16, name=str(c)) for c in (3, 4)]
        api_db_session.add_all(nodes)
        api_db_session.flush()
        route = Route(from_label="P", to_label="Q")
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

        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.delete(
            f"/api/v1/routes/{route.id}",
            headers={"X-User-Roles": "admin"},
        )
        assert resp.status_code == 204
        mock_cache.delete.assert_any_call("/api/v1/routes")
        mock_cache.delete.assert_any_call("dashboard/routes-overview")

    # --- User profiles ----------------------------------------------------

    def test_update_profile_invalidates_profiles_and_dashboard(
        self, client_no_auth, sample_user_profile
    ):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.put(
            f"/api/v1/user/profile/{sample_user_profile.id}",
            json={"name": "Renamed"},
            headers={
                "X-User-Id": sample_user_profile.user_id,
                "X-User-Roles": "operator",
            },
        )
        assert resp.status_code == 200
        mock_cache.delete.assert_any_call("profiles")
        mock_cache.delete.assert_any_call("dashboard")
        mock_cache.delete.assert_any_call("/api/v1/dashboard")

    # --- Node tags --------------------------------------------------------

    def test_create_node_tag_invalidates_cross_entity_caches(
        self, client_no_auth, sample_node, sample_operator_adoption
    ):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.post(
            f"/api/v1/nodes/{sample_node.public_key}/tags",
            json={"key": "name", "value": "Friendly"},
            headers={
                "X-User-Id": "operator-123",
                "X-User-Roles": "operator",
            },
        )
        assert resp.status_code == 201
        for prefix in ("nodes", "/api/v1/messages", "advertisements"):
            mock_cache.delete.assert_any_call(prefix)
        # Dashboard covers both key formats
        mock_cache.delete.assert_any_call("dashboard")
        mock_cache.delete.assert_any_call("/api/v1/dashboard")

    def test_delete_node_tag_invalidates_cross_entity_caches(
        self, client_no_auth, sample_node, sample_node_tag, sample_operator_adoption
    ):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.delete(
            f"/api/v1/nodes/{sample_node.public_key}/tags/{sample_node_tag.key}",
            headers={
                "X-User-Id": "operator-123",
                "X-User-Roles": "operator",
            },
        )
        assert resp.status_code == 204
        for prefix in ("nodes", "/api/v1/messages", "advertisements", "dashboard"):
            mock_cache.delete.assert_any_call(prefix)

    # --- Adoptions --------------------------------------------------------

    def test_adopt_node_invalidates_cross_entity_caches(
        self, client_no_auth, sample_node
    ):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.post(
            "/api/v1/adoptions",
            json={"public_key": sample_node.public_key},
            headers={"X-User-Id": "adopter-1", "X-User-Roles": "operator"},
        )
        assert resp.status_code == 201
        for prefix in ("nodes", "profiles", "advertisements", "dashboard"):
            mock_cache.delete.assert_any_call(prefix)
        mock_cache.delete.assert_any_call("/api/v1/dashboard")

    def test_release_node_invalidates_cross_entity_caches(
        self, client_no_auth, sample_node, sample_adopted_node
    ):
        mock_cache = self._install_mock_cache(client_no_auth)
        resp = client_no_auth.delete(
            f"/api/v1/adoptions/{sample_node.public_key}",
            headers={"X-User-Id": "oidc-user-123", "X-User-Roles": "operator"},
        )
        assert resp.status_code == 204
        for prefix in ("nodes", "profiles", "advertisements", "dashboard"):
            mock_cache.delete.assert_any_call(prefix)

    # --- Resilience -------------------------------------------------------

    def test_cache_delete_error_does_not_break_mutation(
        self, client_no_auth, sample_channel
    ):
        """If Redis is down, the mutation must still succeed."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.delete.side_effect = Exception("redis down")
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30

        resp = client_no_auth.put(
            f"/api/v1/channels/{sample_channel.id}",
            json={"enabled": False},
        )
        assert resp.status_code == 200


class TestMutationVisibilityThroughHttpCache:
    """Regression: stale browser HTTP cache after a mutation.

    Scenario reported in the wild: user edits a Route, the routes list page
    keeps showing old values for ~30s. Root cause was the API emitting
    ``Cache-Control: private, max-age=30`` on ``@cached`` GETs, which lets
    the browser serve its local copy without revalidating — so the
    server-side invalidation never had a chance to fire.

    The policy is now ``private, no-cache`` for all ``@cached`` GETs, which
    forces the browser to send ``If-None-Match`` on every navigation. This
    test models the full round trip: cache-fill, conditional 304, mutation
    (invalidating Redis), then conditional 200 with the fresh body.
    """

    def test_routes_list_refresh_after_mutation(self, client_no_auth, api_db_session):
        from meshcore_hub.common.models import Node, Route, RouteNode

        # Seed a route the user will later edit.
        nodes = [Node(public_key=f"{c:02x}" * 16, name=str(c)) for c in (1, 2)]
        api_db_session.add_all(nodes)
        api_db_session.flush()
        route = Route(from_label="Origin", to_label="Dest")
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

        # Real in-memory cache so set/get/delete behave end-to-end. Keys
        # store the envelope the @cached decorator writes.
        store: dict[str, str] = {}

        class _FakeCache:
            def get(self, key):
                return store.get(key)

            def set(self, key, value, ttl):
                store[key] = value

            def delete(self, prefix):
                # SCAN-style prefix glob, matching RedisCacheBackend.delete.
                for k in list(store.keys()):
                    if k.startswith(prefix):
                        del store[k]

            def ping(self):
                return True

        client_no_auth.app.state.redis_cache = _FakeCache()
        client_no_auth.app.state.redis_cache_ttl = 30

        # 1) Initial GET — populates cache and returns an ETag.
        first = client_no_auth.get("/api/v1/routes", headers={"X-User-Roles": "admin"})
        assert first.status_code == 200
        assert first.headers["x-cache"] == "MISS"
        assert first.headers["cache-control"] == "private, no-cache"
        first_etag = first.headers["etag"]
        first_body = first.json()
        assert first_body["items"][0]["from_label"] == "Origin"

        # 2) Immediate re-fetch with If-None-Match must 304 (cache HIT,
        #    ETag matches). This is the cheap fast path the policy
        #    preserves: browser revalidates, server answers 304, no body.
        cond = client_no_auth.get(
            "/api/v1/routes",
            headers={"X-User-Roles": "admin", "If-None-Match": first_etag},
        )
        assert cond.status_code == 304
        assert cond.headers["x-cache"] == "HIT"
        assert cond.headers["cache-control"] == "private, no-cache"
        assert cond.content in (b"", b"null")

        # 3) Mutate the route. The handler calls invalidate_routes(request),
        #    which must drop the cached entry so the next GET is a MISS.
        mut = client_no_auth.put(
            f"/api/v1/routes/{route.id}",
            json={"from_label": "NewOrigin", "to_label": "NewDest"},
            headers={"X-User-Roles": "admin"},
        )
        assert mut.status_code == 200
        # Mutations are always no-store.
        assert mut.headers["cache-control"] == "no-store"

        # 4) Browser navigates again, sending the stale If-None-Match from
        #    step 1. The server MUST NOT 304 here: Redis was invalidated,
        #    so the handler re-runs, produces a new ETag, and returns 200
        #    with the fresh body. This is exactly the bug the user hit —
        #    under the old max-age=30 policy the browser never sent this
        #    request at all.
        after = client_no_auth.get(
            "/api/v1/routes",
            headers={"X-User-Roles": "admin", "If-None-Match": first_etag},
        )
        assert after.status_code == 200
        assert after.headers["x-cache"] == "MISS"
        assert after.headers["etag"] != first_etag
        assert after.json()["items"][0]["from_label"] == "NewOrigin"

    def test_cached_gets_always_emit_no_cache_regardless_of_ttl(self, client_no_auth):
        """Even a 300s dashboard TTL must not surface as max-age=300.

        The dashboard endpoints have ``redis_cache_ttl_dashboard=300``, but
        that bound applies only to the Redis cache. The HTTP policy is
        always ``private, no-cache`` so server-side invalidation can reach
        the browser after any mutation.
        """
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        client_no_auth.app.state.redis_cache = mock_cache
        client_no_auth.app.state.redis_cache_ttl = 30
        client_no_auth.app.state.redis_cache_ttl_dashboard = 300

        resp = client_no_auth.get("/api/v1/dashboard/activity")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "private, no-cache"


class TestInvalidationLogging:
    """Diagnostic logging for cache invalidation.

    These tests pin down the log lines that operators grep for when
    diagnosing whether mutation handlers actually fire invalidation and
    whether Redis SCAN matches stored keys. The shape of the log output
    is part of the contract — changing it breaks log dashboards and the
    diagnostic runbook.
    """

    def test_drop_logs_start_and_ok_on_success(self, caplog):
        from meshcore_hub.api.cache_invalidation import invalidate_routes

        cache = MagicMock()
        cache.__class__.__name__ = "RedisCacheBackend"
        request = _make_request_with_cache(cache)

        with caplog.at_level("INFO", logger="meshcore_hub.api.cache_invalidation"):
            invalidate_routes(request)

        messages = [r.message for r in caplog.records]
        assert any(
            "Cache invalidate start" in m
            and "prefix=/api/v1/routes" in m
            and "backend=RedisCacheBackend" in m
            for m in messages
        ), f"start line missing or malformed: {messages}"
        assert any(
            "Cache invalidate ok" in m and "prefix=/api/v1/routes" in m
            for m in messages
        ), f"ok line missing or malformed: {messages}"

    def test_drop_logs_warning_on_backend_error(self, caplog):
        from meshcore_hub.api.cache_invalidation import invalidate_channels

        cache = MagicMock()
        cache.delete.side_effect = Exception("redis down")
        request = _make_request_with_cache(cache)

        with caplog.at_level("WARNING", logger="meshcore_hub.api.cache_invalidation"):
            invalidate_channels(request)

        # Must not raise; warning must carry prefix + error text.
        assert any(
            "Cache invalidate error" in r.message
            and "prefix=/api/v1/channels" in r.message
            and "redis down" in r.message
            for r in caplog.records
        ), [r.message for r in caplog.records]

    def test_drop_logs_skipped_when_no_backend(self, caplog):
        from meshcore_hub.api.cache_invalidation import invalidate_nodes

        # No redis_cache attribute on app.state.
        request = _make_request_with_cache(cache=None)

        with caplog.at_level("DEBUG", logger="meshcore_hub.api.cache_invalidation"):
            invalidate_nodes(request)

        assert any(
            "Cache invalidate skipped" in r.message and "prefix=nodes" in r.message
            for r in caplog.records
        ), [r.message for r in caplog.records]

    def test_drop_logs_backend_name_distinguishes_nullcache(self, caplog):
        """If NullCache is wired in, the start log must say so.

        Catches the 'REDIS_ENABLED is actually false in production' case
        in one log line.
        """
        from meshcore_hub.api.cache_invalidation import invalidate_routes

        null_cache = NullCache()
        request = _make_request_with_cache(null_cache)

        with caplog.at_level("INFO", logger="meshcore_hub.api.cache_invalidation"):
            invalidate_routes(request)

        messages = [r.message for r in caplog.records]
        assert any(
            "backend=NullCache" in m and "prefix=/api/v1/routes" in m for m in messages
        ), f"expected backend=NullCache in start log, got: {messages}"

    def test_redis_delete_logs_keys_deleted_count(self, caplog):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.return_value = (0, [b"hub:nodes:1", b"hub:nodes:2"])

            backend = RedisCacheBackend(key_prefix="hub")
            with caplog.at_level("INFO", logger="meshcore_hub.common.redis"):
                backend.delete("nodes")

        # One INFO line with prefix, full_prefix, and keys_deleted=2.
        info_records = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_records) == 1, [r.message for r in caplog.records]
        msg = info_records[0].message
        assert "Redis cache delete" in msg
        assert "prefix=nodes" in msg
        assert "full_prefix=hub:nodes" in msg
        assert "keys_deleted=2" in msg
        assert "scan_iterations=1" in msg

    def test_redis_delete_logs_zero_keys_on_empty_scan(self, caplog):
        """The smoking-gun signal for the production bug.

        If invalidation fires but SCAN matches nothing, ``keys_deleted=0``
        appears in the log. That points directly at a cache-key mismatch
        between the store path (key_builder) and the delete path (prefix).
        """
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.return_value = (0, [])

            backend = RedisCacheBackend(key_prefix="hub")
            with caplog.at_level("INFO", logger="meshcore_hub.common.redis"):
                backend.delete("/api/v1/routes")

        info_records = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_records) == 1
        msg = info_records[0].message
        assert "keys_deleted=0" in msg
        assert "prefix=/api/v1/routes" in msg
        assert "full_prefix=hub:/api/v1/routes" in msg

    def test_redis_delete_warning_includes_full_prefix(self, caplog):
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.side_effect = Exception("scan timeout")

            backend = RedisCacheBackend(key_prefix="hub")
            with caplog.at_level("WARNING", logger="meshcore_hub.common.redis"):
                backend.delete("nodes")

        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) == 1
        msg = warning_records[0].message
        assert "Redis DELETE error" in msg
        assert "prefix=nodes" in msg
        assert "full_prefix=hub:nodes" in msg
        assert "scan timeout" in msg

    def test_redis_delete_multi_page_scan_logs_total_keys(self, caplog):
        """Multi-page SCAN must accumulate keys_deleted across iterations."""
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_redis_cls.return_value = mock_client
            mock_client.scan.side_effect = [
                (42, [b"hub:nodes:1", b"hub:nodes:2"]),
                (0, [b"hub:nodes:3"]),
            ]

            backend = RedisCacheBackend(key_prefix="hub")
            with caplog.at_level("INFO", logger="meshcore_hub.common.redis"):
                backend.delete("nodes")

        info_records = [r for r in caplog.records if r.levelname == "INFO"]
        assert len(info_records) == 1
        msg = info_records[0].message
        assert "keys_deleted=3" in msg
        assert "scan_iterations=2" in msg

    def test_nullcache_delete_emits_debug_log(self, caplog):
        cache = NullCache()
        with caplog.at_level("DEBUG", logger="meshcore_hub.common.redis"):
            cache.delete("nodes")
        assert any(
            "NullCache delete" in r.message and "prefix=nodes" in r.message
            for r in caplog.records
        ), [r.message for r in caplog.records]
