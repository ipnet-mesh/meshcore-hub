"""Tests for the API CLI command (server launch wiring)."""

from unittest.mock import patch

from click.testing import CliRunner

from meshcore_hub.api.cli import api

# Opaque URL: satisfies the fail-fast database check; nothing connects
# (uvicorn.run is mocked, so the lifespan never starts).
_TEST_DB_URL = "postgresql+psycopg2://meshcorehub:pw@localhost:5432/meshcorehub"


def test_api_default_runs_single_process():
    """With the default worker count, the app object is passed directly and no
    worker/factory options are used."""
    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(
            api, ["--database-url", _TEST_DB_URL], catch_exceptions=False
        )

    assert result.exit_code == 0
    assert mock_run.call_count == 1
    args, kwargs = mock_run.call_args
    # Single-process path passes the built app object, not an import string.
    assert not isinstance(args[0], str)
    assert "workers" not in kwargs


def test_api_workers_uses_env_factory_import_string():
    """workers > 1 launches uvicorn against the env-driven factory by import
    string with the requested worker count."""
    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(
            api,
            ["--database-url", _TEST_DB_URL, "--workers", "3"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    args, kwargs = mock_run.call_args
    assert args[0] == "meshcore_hub.api.app:create_app_from_env"
    assert kwargs["workers"] == 3
    assert kwargs["factory"] is True


def test_api_workers_from_env_var():
    """API_WORKERS env var drives the worker count (the Docker path)."""
    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(
            api,
            ["--database-url", _TEST_DB_URL],
            env={"API_WORKERS": "2"},
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    _, kwargs = mock_run.call_args
    assert kwargs["workers"] == 2


def test_api_single_process_passes_spam_and_role_settings():
    """The single-process app must carry the env-configured spam + OIDC role
    settings — previously this path dropped them, silently disabling the
    spam hide-filter and custom role names (the env factory path was fine)."""
    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(
            api,
            ["--database-url", _TEST_DB_URL],
            env={
                "SPAM_DETECTION_ENABLED": "true",
                "SPAM_SCORE_THRESHOLD": "0.8",
                "OIDC_ROLE_ADMIN": "superadmin",
                "OIDC_ROLE_OPERATOR": "moderator",
                "OIDC_ROLE_MEMBER": "user",
            },
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    app = mock_run.call_args[0][0]
    assert app.state.spam_detection_enabled is True
    assert app.state.spam_score_threshold == 0.8
    assert app.state.oidc_role_admin == "superadmin"
    assert app.state.oidc_role_operator == "moderator"
    assert app.state.oidc_role_member == "user"
