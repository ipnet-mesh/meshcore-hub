"""Tests for the environment-driven app factory used by multi-worker runs."""

import pytest
from starlette.middleware.cors import CORSMiddleware

from meshcore_hub.api.app import create_app_from_env

# Env vars the factory reads, cleared before each test so the host
# environment can't leak into assertions.
_FACTORY_ENV = [
    "DATABASE_URL",
    "DATA_HOME",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_SCHEMA",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "REDIS_ENABLED",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_CACHE_TTL",
    "MQTT_HOST",
    "CORS_ORIGINS",
    "METRICS_ENABLED",
    "METRICS_CACHE_TTL",
    "METRICS_PUBLIC",
    "SPAM_DETECTION_ENABLED",
    "SPAM_SCORE_THRESHOLD",
    "OIDC_ROLE_ADMIN",
    "OIDC_ROLE_OPERATOR",
    "OIDC_ROLE_MEMBER",
]


@pytest.fixture
def clean_env(monkeypatch):
    for var in _FACTORY_ENV:
        monkeypatch.delenv(var, raising=False)
    # The factory requires a database connection (PostgreSQL-only); default
    # to an explicit URL so tests not about DB resolution still build an app.
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg2://u:p@factory-test:5432/hub"
    )
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
    clean_env.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@workers-test:5432/hub")
    clean_env.setenv("REDIS_ENABLED", "true")
    clean_env.setenv("REDIS_HOST", "redis-test")
    clean_env.setenv("REDIS_PORT", "6390")
    clean_env.setenv("MQTT_HOST", "mqtt-test")
    clean_env.setenv("METRICS_CACHE_TTL", "99")

    app = create_app_from_env()

    assert app.state.database_url == "postgresql+psycopg2://u:p@workers-test:5432/hub"
    assert app.state.redis_enabled is True
    assert app.state.redis_host == "redis-test"
    assert app.state.redis_port == 6390
    assert app.state.mqtt_host == "mqtt-test"
    assert app.state.metrics_cache_ttl == 99


def test_factory_assembles_url_from_component_vars(clean_env):
    """Without an explicit DATABASE_URL, the DATABASE_* components assemble
    the connection — the app factory never falls back to a default file DB."""
    clean_env.delenv("DATABASE_URL")
    clean_env.setenv("REDIS_ENABLED", "false")
    clean_env.setenv("DATABASE_HOST", "pg-test")
    clean_env.setenv("DATABASE_PASSWORD", "pw")

    app = create_app_from_env()

    assert app.state.redis_enabled is False
    assert app.state.database_url == (
        "postgresql+psycopg2://meshcorehub:pw@pg-test:5432/meshcorehub"
    )


def test_factory_without_database_config_raises(clean_env):
    """Missing connection config fails fast instead of guessing a default."""
    clean_env.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="PostgreSQL connection is not configured"):
        _ = create_app_from_env()


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


def _cors_middleware(app):
    """Return the CORSMiddleware Middleware entry for the app."""
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware
    raise AssertionError("CORSMiddleware not installed")


def test_factory_default_cors_wildcard_without_credentials(clean_env):
    """Unset CORS_ORIGINS keeps the wildcard but disables credentials."""
    app = create_app_from_env()
    cors = _cors_middleware(app)
    assert cors.kwargs["allow_origins"] == ["*"]
    assert cors.kwargs["allow_credentials"] is False


def test_factory_explicit_origins_allow_credentials(clean_env):
    """Explicit CORS_ORIGINS lists keep credentials enabled."""
    clean_env.setenv("CORS_ORIGINS", "https://mesh.example.com,https://web.example.com")
    app = create_app_from_env()
    cors = _cors_middleware(app)
    assert cors.kwargs["allow_origins"] == [
        "https://mesh.example.com",
        "https://web.example.com",
    ]
    assert cors.kwargs["allow_credentials"] is True


def test_factory_metrics_public_defaults_deny(clean_env):
    """METRICS_PUBLIC unset means /metrics denies unauthenticated access."""
    app = create_app_from_env()
    assert app.state.metrics_public is False


def test_factory_metrics_public_via_env(clean_env):
    """METRICS_PUBLIC=true opts into unauthenticated metrics."""
    clean_env.setenv("METRICS_PUBLIC", "true")
    app = create_app_from_env()
    assert app.state.metrics_public is True


def test_factory_reads_spam_settings_from_env(clean_env):
    """SPAM_DETECTION_ENABLED / SPAM_SCORE_THRESHOLD reach app.state so the
    messages hide-filter actually runs when the feature is enabled."""
    clean_env.setenv("SPAM_DETECTION_ENABLED", "true")
    clean_env.setenv("SPAM_SCORE_THRESHOLD", "0.9")

    app = create_app_from_env()

    assert app.state.spam_detection_enabled is True
    assert app.state.spam_score_threshold == 0.9


def test_factory_spam_settings_default_off(clean_env):
    """Without env config the feature stays dark (create_app default)."""
    app = create_app_from_env()
    assert app.state.spam_detection_enabled is False
    assert app.state.spam_score_threshold == 0.65


def test_factory_reads_oidc_role_names_from_env(clean_env):
    """Custom OIDC_ROLE_* names reach app.state, matching the web tier, so
    API authorization honors customized IdP role naming."""
    clean_env.setenv("OIDC_ROLE_ADMIN", "superadmin")
    clean_env.setenv("OIDC_ROLE_OPERATOR", "moderator")
    clean_env.setenv("OIDC_ROLE_MEMBER", "user")

    app = create_app_from_env()

    assert app.state.oidc_role_admin == "superadmin"
    assert app.state.oidc_role_operator == "moderator"
    assert app.state.oidc_role_member == "user"


def test_factory_oidc_role_names_default(clean_env):
    """Default role names match the documented admin/operator/member."""
    app = create_app_from_env()
    assert app.state.oidc_role_admin == "admin"
    assert app.state.oidc_role_operator == "operator"
    assert app.state.oidc_role_member == "member"
