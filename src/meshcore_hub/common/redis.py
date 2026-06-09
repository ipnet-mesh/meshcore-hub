"""Redis cache backend for API response caching."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CacheBackend:
    """Abstract base class for cache backends."""

    def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def set(self, key: str, value: str, ttl: int) -> None:
        raise NotImplementedError

    def delete(self, prefix: str) -> None:
        raise NotImplementedError

    def ping(self) -> bool:
        raise NotImplementedError


class NullCache(CacheBackend):
    """No-op cache backend used when Redis is disabled."""

    def get(self, key: str) -> Optional[str]:
        return None

    def set(self, key: str, value: str, ttl: int) -> None:
        pass

    def delete(self, prefix: str) -> None:
        pass

    def ping(self) -> bool:
        return False


class RedisCacheBackend(CacheBackend):
    """Redis-backed cache using a connection pool."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        key_prefix: str = "hub",
    ) -> None:
        import redis

        self._prefix = key_prefix
        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=False,
        )

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Optional[str]:
        try:
            full_key = self._full_key(key)
            value = self._client.get(full_key)
            if value is not None:
                return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.warning("Redis GET error for %s: %s", key, e)
            return None

    def set(self, key: str, value: str, ttl: int) -> None:
        try:
            full_key = self._full_key(key)
            self._client.setex(full_key, ttl, value)
        except Exception as e:
            logger.warning("Redis SET error for %s: %s", key, e)

    def delete(self, prefix: str) -> None:
        try:
            full_prefix = self._full_key(prefix)
            cursor = 0
            while True:
                cursor, keys = self._client.scan(
                    cursor, match=f"{full_prefix}*", count=100
                )
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Redis DELETE error for prefix %s: %s", prefix, e)

    def ping(self) -> bool:
        try:
            result = self._client.ping()
            return bool(result)
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
