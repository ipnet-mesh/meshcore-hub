"""Smoke tests for the top-level CLI entry point.

Verify the ``cli`` group wiring: version reporting, help output, and the
registered component subcommands (collector, api, web, db).
"""

from click.testing import CliRunner

from meshcore_hub import __version__
from meshcore_hub.__main__ import cli


def test_version_reports_package_version() -> None:
    """--version prints the package version and exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_component_commands() -> None:
    """--help advertises the component subcommands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    for command in ("collector", "api", "web", "db"):
        assert command in result.output


def test_db_help_lists_migration_commands() -> None:
    """db --help advertises the Alembic migration commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["db", "--help"])

    assert result.exit_code == 0
    assert "upgrade" in result.output
    assert "downgrade" in result.output
