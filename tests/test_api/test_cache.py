"""Tests for API cache layer."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request

from meshcore_hub.api.cache import cached, sorted_query_string
from meshcore_hub.common.redis import NullCache, RedisCacheBackend


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
