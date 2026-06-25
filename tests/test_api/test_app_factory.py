"""Tests for the environment-driven app factory used by multi-worker runs."""

import pytest

from meshcore_hub.api.app import create_app_from_env

# Env vars the factory reads, cleared before each test so the host
# environment can't leak into assertions.
_FACTORY_ENV = [
    "DATABASE_URL",
    "DATA_HOME",
    "REDIS_ENABLED",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_CACHE_TTL",
    "MQTT_HOST",
    "CORS_ORIGINS",
    "METRICS_ENABLED",
    "METRICS_CACHE_TTL",
]


@pytest.fixture
def clean_env(monkeypatch):
    for var in _FACTORY_ENV:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def _served_paths(app):
    """Return the set of paths the app actually serves.

    FastAPI 0.137 refactored ``include_router`` to keep included routers as
    nested objects instead of flattening their routes into ``app.routes``, so
    iterating ``app.routes`` no longer surfaces routed endpoints like
    ``/metrics``. The OpenAPI schema is the stable, version-independent way to
    introspect mounted paths (and it resolves router prefixes correctly).
    """
    return set(app.openapi()["paths"])


def test_factory_reads_database_and_redis_from_env(clean_env):
    """Workers must pick up the real DB/Redis config from env, not the
    hardcoded create_app defaults."""
    clean_env.setenv("DATABASE_URL", "sqlite:////tmp/workers-test.db")
    clean_env.setenv("REDIS_ENABLED", "true")
    clean_env.setenv("REDIS_HOST", "redis-test")
    clean_env.setenv("REDIS_PORT", "6390")
    clean_env.setenv("MQTT_HOST", "mqtt-test")
    clean_env.setenv("METRICS_CACHE_TTL", "99")

    app = create_app_from_env()

    assert app.state.database_url == "sqlite:////tmp/workers-test.db"
    assert app.state.redis_enabled is True
    assert app.state.redis_host == "redis-test"
    assert app.state.redis_port == 6390
    assert app.state.mqtt_host == "mqtt-test"
    assert app.state.metrics_cache_ttl == 99


def test_factory_honours_explicit_disable_and_data_home(clean_env):
    """Env values override anything else, and a data-home (no explicit
    DATABASE_URL) resolves to the collector DB path — never the bare
    create_app default that would point workers at ./meshcore.db."""
    clean_env.setenv("REDIS_ENABLED", "false")
    clean_env.setenv("DATA_HOME", "/srv/hubdata")

    app = create_app_from_env()

    assert app.state.redis_enabled is False
    assert app.state.database_url == "sqlite:////srv/hubdata/collector/meshcore.db"


def test_factory_redis_enabled_accepts_truthy_values(clean_env):
    """REDIS_ENABLED / METRICS_ENABLED parse common truthy spellings."""
    clean_env.setenv("REDIS_ENABLED", "1")
    app = create_app_from_env()
    assert app.state.redis_enabled is True


def test_factory_metrics_enabled_via_env(clean_env):
    """METRICS_ENABLED=true mounts the /metrics endpoint."""
    clean_env.setenv("METRICS_ENABLED", "true")
    app = create_app_from_env()
    assert "/metrics" in _served_paths(app)


def test_factory_metrics_disabled_via_env(clean_env):
    """METRICS_ENABLED=false omits the /metrics endpoint."""
    clean_env.setenv("METRICS_ENABLED", "false")
    app = create_app_from_env()
    assert "/metrics" not in _served_paths(app)
