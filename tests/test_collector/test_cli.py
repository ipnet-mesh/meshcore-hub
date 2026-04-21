"""Tests for collector CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from meshcore_hub.collector.cli import collector


class TestCollectorGroup:
    """Tests for the collector group command."""

    def test_collector_without_subcommand_calls_run_service(self):
        """Invoking collector without subcommand calls _run_collector_service."""
        runner = CliRunner()
        mock_settings = MagicMock(
            data_home="/tmp/data",
            effective_seed_home="/tmp/seed",
            effective_database_url="sqlite:///tmp/test.db",
        )
        mock_settings.model_copy.return_value = mock_settings

        with (
            patch(
                "meshcore_hub.common.config.get_collector_settings",
                return_value=mock_settings,
            ),
            patch("meshcore_hub.collector.cli._run_collector_service") as mock_run,
        ):
            result = runner.invoke(
                collector, ["--mqtt-host", "testhost"], catch_exceptions=False
            )

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_collector_with_data_home_override(self):
        """--data-home overrides the default data home."""
        runner = CliRunner()
        mock_settings = MagicMock(
            data_home="/default",
            effective_seed_home="/default/seed",
            effective_database_url="sqlite:///default/db",
        )
        mock_settings.model_copy.return_value = mock_settings

        with (
            patch(
                "meshcore_hub.common.config.get_collector_settings",
                return_value=mock_settings,
            ),
            patch("meshcore_hub.collector.cli._run_collector_service"),
        ):
            result = runner.invoke(
                collector,
                ["--data-home", "/custom/data"],
                catch_exceptions=False,
                env={"SEED_HOME": None},
            )

        assert result.exit_code == 0
        mock_settings.model_copy.assert_called_once_with(
            update={"data_home": "/custom/data"}
        )


class TestCollectorRunSubcommand:
    """Tests for the 'collector run' subcommand."""

    def test_run_subcommand_calls_run_service(self):
        """'collector run' delegates to _run_collector_service."""
        runner = CliRunner()
        mock_settings = MagicMock(
            data_home="/tmp/data",
            effective_seed_home="/tmp/seed",
            effective_database_url="sqlite:///tmp/test.db",
        )
        mock_settings.model_copy.return_value = mock_settings

        with (
            patch(
                "meshcore_hub.common.config.get_collector_settings",
                return_value=mock_settings,
            ),
            patch("meshcore_hub.collector.cli._run_collector_service") as mock_run,
        ):
            result = runner.invoke(collector, ["run"], catch_exceptions=False)

        assert result.exit_code == 0
        mock_run.assert_called_once()


class TestCollectorSeedSubcommand:
    """Tests for the 'collector seed' subcommand."""

    def test_seed_command_help(self):
        """'collector seed --help' shows usage."""
        runner = CliRunner()
        mock_settings = MagicMock(
            data_home="/tmp/data",
            effective_seed_home="/tmp/seed",
            effective_database_url="sqlite:///tmp/test.db",
        )
        mock_settings.model_copy.return_value = mock_settings

        with patch(
            "meshcore_hub.common.config.get_collector_settings",
            return_value=mock_settings,
        ):
            result = runner.invoke(collector, ["seed", "--help"])

        assert result.exit_code == 0
        assert "seed" in result.output.lower() or "import" in result.output.lower()
