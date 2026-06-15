"""Tests for the top-level CLI, focused on ``db migrate-to-postgres``.

The migration engine itself is covered in test_common/test_db_migrate.py; here we
verify the command's wiring: option plumbing, dry-run vs. real output, and how the
MigrationResult (or an error) maps onto exit codes and messages.
"""

from unittest.mock import patch

from click.testing import CliRunner

from meshcore_hub.__main__ import cli
from meshcore_hub.common.db_migrate import MigrationResult, TableResult


def _result(*tables: TableResult, dry_run: bool = False) -> MigrationResult:
    return MigrationResult(tables=list(tables), dry_run=dry_run)


def test_migrate_to_postgres_success() -> None:
    """A matching run reports OK per table and exits 0."""
    runner = CliRunner()
    fake = _result(TableResult("nodes", 5, 5))

    with patch(
        "meshcore_hub.common.db_migrate.migrate_sqlite_to_postgres",
        return_value=fake,
    ) as mock_migrate:
        result = runner.invoke(
            cli,
            [
                "db",
                "migrate-to-postgres",
                "--source",
                "sqlite:///src.db",
                "--target",
                "postgresql://u@h/db",
            ],
        )

    assert result.exit_code == 0
    assert "nodes" in result.output
    assert "OK" in result.output
    assert "Migration complete." in result.output
    # Flags thread through to the engine call.
    _, kwargs = mock_migrate.call_args
    assert kwargs["dry_run"] is False
    assert kwargs["truncate"] is False


def test_migrate_to_postgres_dry_run() -> None:
    """Dry run prints a preview and never renders OK/MISMATCH judgements."""
    runner = CliRunner()
    fake = _result(TableResult("nodes", 3, 0), dry_run=True)

    with patch(
        "meshcore_hub.common.db_migrate.migrate_sqlite_to_postgres",
        return_value=fake,
    ) as mock_migrate:
        result = runner.invoke(
            cli,
            [
                "db",
                "migrate-to-postgres",
                "--source",
                "sqlite:///src.db",
                "--target",
                "postgresql://u@h/db",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert "Dry run complete." in result.output
    assert "OK" not in result.output
    assert mock_migrate.call_args.kwargs["dry_run"] is True


def test_migrate_to_postgres_mismatch_exits_nonzero() -> None:
    """A row-count mismatch surfaces as a ClickException (non-zero exit)."""
    runner = CliRunner()
    fake = _result(TableResult("nodes", 5, 4))  # ok == False

    with patch(
        "meshcore_hub.common.db_migrate.migrate_sqlite_to_postgres",
        return_value=fake,
    ):
        result = runner.invoke(
            cli,
            [
                "db",
                "migrate-to-postgres",
                "--source",
                "sqlite:///src.db",
                "--target",
                "postgresql://u@h/db",
            ],
        )

    assert result.exit_code != 0
    assert "MISMATCH" in result.output
    assert "mismatch" in result.output.lower()


def test_migrate_to_postgres_value_error_becomes_click_exception() -> None:
    """A ValueError from the engine (e.g. bad target) maps to a clean CLI error."""
    runner = CliRunner()

    with patch(
        "meshcore_hub.common.db_migrate.migrate_sqlite_to_postgres",
        side_effect=ValueError("Target must be a PostgreSQL database URL"),
    ):
        result = runner.invoke(
            cli,
            [
                "db",
                "migrate-to-postgres",
                "--source",
                "sqlite:///src.db",
                "--target",
                "sqlite:///bad.db",
            ],
        )

    assert result.exit_code != 0
    assert "PostgreSQL" in result.output
