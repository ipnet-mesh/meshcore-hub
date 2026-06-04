"""Tests for collector CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from meshcore_hub.collector.cli import _import_channels, collector
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models.channel import Channel


def _make_mock_settings(db_url: str, seed_home: str = "/tmp/seed") -> MagicMock:
    mock_settings = MagicMock(
        data_home="/tmp/data",
        effective_seed_home=seed_home,
        effective_database_url=db_url,
        node_tags_file=f"{seed_home}/node_tags.yaml",
        channels_file=f"{seed_home}/channels.yaml",
    )
    mock_settings.model_copy.return_value = mock_settings
    return mock_settings


def _invoke_channel_cmd(runner: CliRunner, db_url: str, args: list[str]):
    mock_settings = _make_mock_settings(db_url)
    with patch(
        "meshcore_hub.common.config.get_collector_settings",
        return_value=mock_settings,
    ):
        return runner.invoke(
            collector,
            ["--database-url", db_url] + args,
            catch_exceptions=False,
        )


class TestCollectorGroup:
    """Tests for the collector group command."""

    def test_collector_without_subcommand_calls_run_service(self):
        runner = CliRunner()
        mock_settings = _make_mock_settings("sqlite:///tmp/test.db")

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
        runner = CliRunner()
        mock_settings = _make_mock_settings("sqlite:///default/db")

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
        runner = CliRunner()
        mock_settings = _make_mock_settings("sqlite:///tmp/test.db")

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
        runner = CliRunner()
        mock_settings = _make_mock_settings("sqlite:///tmp/test.db")

        with patch(
            "meshcore_hub.common.config.get_collector_settings",
            return_value=mock_settings,
        ):
            result = runner.invoke(collector, ["seed", "--help"])

        assert result.exit_code == 0
        assert "seed" in result.output.lower() or "import" in result.output.lower()


class TestChannelCommands:
    """Integration tests for channel CLI commands using real SQLite."""

    @pytest.fixture
    def cli_db_url(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_url = f"sqlite:///{db_path}"
        db = DatabaseManager(db_url)
        db.create_tables()
        db.dispose()
        return db_url

    def test_channel_list_empty(self, cli_db_url):
        runner = CliRunner()
        result = _invoke_channel_cmd(runner, cli_db_url, ["channel", "list"])
        assert result.exit_code == 0
        assert "No channels found." in result.output

    def test_channel_add_success(self, cli_db_url):
        runner = CliRunner()
        result = _invoke_channel_cmd(
            runner,
            cli_db_url,
            ["channel", "add", "--name", "TestCh", "--key", "AABB" * 8],
        )
        assert result.exit_code == 0
        assert "TestCh" in result.output
        assert "added" in result.output

        result = _invoke_channel_cmd(runner, cli_db_url, ["channel", "list"])
        assert "TestCh" in result.output

    def test_channel_add_duplicate_name(self, cli_db_url):
        runner = CliRunner()
        _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "add", "--name", "Dup", "--key", "A" * 32]
        )
        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "add", "--name", "Dup", "--key", "B" * 32]
        )
        assert result.exit_code == 0
        assert "already exists" in result.output

    def test_channel_add_custom_visibility(self, cli_db_url):
        runner = CliRunner()
        result = _invoke_channel_cmd(
            runner,
            cli_db_url,
            [
                "channel",
                "add",
                "--name",
                "PrivateCh",
                "--key",
                "C" * 32,
                "--visibility",
                "member",
            ],
        )
        assert result.exit_code == 0
        assert "added" in result.output

        db = DatabaseManager(cli_db_url)
        with db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "PrivateCh").first()
            assert ch is not None
            assert ch.visibility == "member"
        db.dispose()

    def test_channel_list_with_data(self, cli_db_url):
        runner = CliRunner()
        _invoke_channel_cmd(
            runner,
            cli_db_url,
            ["channel", "add", "--name", "Alpha", "--key", "D" * 32],
        )
        result = _invoke_channel_cmd(runner, cli_db_url, ["channel", "list"])
        assert result.exit_code == 0
        assert "Alpha" in result.output
        assert "Yes" in result.output

    def test_channel_remove_success(self, cli_db_url):
        runner = CliRunner()
        _invoke_channel_cmd(
            runner,
            cli_db_url,
            ["channel", "add", "--name", "Gone", "--key", "E" * 32],
        )
        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "remove", "--name", "Gone"]
        )
        assert result.exit_code == 0
        assert "removed" in result.output

        result = _invoke_channel_cmd(runner, cli_db_url, ["channel", "list"])
        assert "Gone" not in result.output

    def test_channel_remove_not_found(self, cli_db_url):
        runner = CliRunner()
        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "remove", "--name", "Missing"]
        )
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_channel_disable_then_enable(self, cli_db_url):
        runner = CliRunner()
        _invoke_channel_cmd(
            runner,
            cli_db_url,
            ["channel", "add", "--name", "Toggle", "--key", "F" * 32],
        )

        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "disable", "--name", "Toggle"]
        )
        assert result.exit_code == 0
        assert "disabled" in result.output

        db = DatabaseManager(cli_db_url)
        with db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "Toggle").first()
            assert ch is not None
            assert ch.enabled is False
        db.dispose()

        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "enable", "--name", "Toggle"]
        )
        assert result.exit_code == 0
        assert "enabled" in result.output

        db = DatabaseManager(cli_db_url)
        with db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "Toggle").first()
            assert ch is not None
            assert ch.enabled is True
        db.dispose()

    def test_channel_enable_not_found(self, cli_db_url):
        runner = CliRunner()
        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "enable", "--name", "Missing"]
        )
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_channel_disable_not_found(self, cli_db_url):
        runner = CliRunner()
        result = _invoke_channel_cmd(
            runner, cli_db_url, ["channel", "disable", "--name", "Missing"]
        )
        assert result.exit_code == 0
        assert "not found" in result.output


class TestImportChannels:
    """Unit tests for _import_channels YAML import function."""

    @pytest.fixture
    def import_db(self, tmp_path):
        db_path = tmp_path / "import.db"
        db = DatabaseManager(f"sqlite:///{db_path}")
        db.create_tables()
        yield db
        db.dispose()

    def _write_yaml(self, tmp_path, content: str) -> str:
        yaml_file = tmp_path / "channels.yaml"
        yaml_file.write_text(content)
        return str(yaml_file)

    def test_import_shorthand_format(self, import_db, tmp_path):
        key = "AABBCCDDEEFF00112233445566778899"
        path = self._write_yaml(tmp_path, f"TestCh: {key}\n")
        result = _import_channels(path, import_db)

        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["errors"] == []

        with import_db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "TestCh").first()
            assert ch is not None
            assert ch.key_hex == key.upper()
            assert ch.visibility == "community"
            assert ch.enabled is True

    def test_import_expanded_format(self, import_db, tmp_path):
        key = "11223344556677889900AABBCCDDEEFF"
        path = self._write_yaml(tmp_path, f"Expanded: {{key: {key}, enabled: false}}\n")
        result = _import_channels(path, import_db)

        assert result["created"] == 1
        assert result["updated"] == 0

        with import_db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "Expanded").first()
            assert ch is not None
            assert ch.enabled is False

    def test_import_updates_existing(self, import_db, tmp_path):
        old_key = "A" * 32
        new_key = "B" * 32
        path1 = self._write_yaml(tmp_path, f"MyCh: {old_key}\n")
        _import_channels(path1, import_db)

        path2 = self._write_yaml(tmp_path, f"MyCh: {new_key}\n")
        result = _import_channels(path2, import_db)

        assert result["created"] == 0
        assert result["updated"] == 1

        with import_db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "MyCh").first()
            assert ch.key_hex == new_key.upper()
            assert ch.channel_hash == Channel.compute_channel_hash(new_key.upper())

    def test_import_empty_yaml(self, import_db, tmp_path):
        path = self._write_yaml(tmp_path, "")
        result = _import_channels(path, import_db)

        assert result["created"] == 0
        assert result["updated"] == 0
        errors: list[str] = result["errors"]  # type: ignore[assignment]
        assert errors == []

    def test_import_invalid_format(self, import_db, tmp_path):
        path = self._write_yaml(tmp_path, "BadCh: 12345\n")
        result = _import_channels(path, import_db)

        assert result["created"] == 0
        errors: list[str] = result["errors"]  # type: ignore[assignment]
        assert len(errors) == 1
        assert "Invalid format" in errors[0]

    def test_import_empty_key(self, import_db, tmp_path):
        path = self._write_yaml(tmp_path, "EmptyKey: {key: ''}\n")
        result = _import_channels(path, import_db)

        assert result["created"] == 0
        errors: list[str] = result["errors"]  # type: ignore[assignment]
        assert len(errors) == 1
        assert "Empty key" in errors[0]

    def test_import_exception_handling(self, import_db, tmp_path):
        path = self._write_yaml(tmp_path, "Boom: AABBCCDDEEFF00112233445566778899\n")
        with patch(
            "meshcore_hub.common.models.channel.Channel",
            side_effect=RuntimeError("db boom"),
        ):
            result = _import_channels(path, import_db)

        errors: list[str] = result["errors"]  # type: ignore[assignment]
        assert len(errors) == 1
        assert "Boom" in errors[0]

    def test_import_multiple_channels(self, import_db, tmp_path):
        path = self._write_yaml(
            tmp_path,
            "Ch1: AABBCCDDEEFF00112233445566778899\n"
            "Ch2: 11223344556677889900AABBCCDDEEFF\n",
        )
        result = _import_channels(path, import_db)

        assert result["created"] == 2
        assert result["updated"] == 0


class TestChannelSeedImport:
    """Integration tests for seed command with channels.yaml."""

    def test_seed_imports_channels_yaml(self, tmp_path):
        runner = CliRunner()
        seed_dir = tmp_path / "seed"
        seed_dir.mkdir()
        (seed_dir / "channels.yaml").write_text(
            "SeededCh: AABBCCDDEEFF00112233445566778899\n"
        )

        db_path = tmp_path / "seed_test.db"
        db_url = f"sqlite:///{db_path}"
        db = DatabaseManager(db_url)
        db.create_tables()
        db.dispose()

        mock_settings = _make_mock_settings(db_url, seed_home=str(seed_dir))

        with patch(
            "meshcore_hub.common.config.get_collector_settings",
            return_value=mock_settings,
        ):
            result = runner.invoke(
                collector,
                ["--database-url", db_url, "--seed-home", str(seed_dir), "seed"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "Channels: 1 created" in result.output

        db = DatabaseManager(db_url)
        with db.session_scope() as session:
            ch = session.query(Channel).filter(Channel.name == "SeededCh").first()
            assert ch is not None
            assert ch.visibility == "community"
        db.dispose()

    def test_seed_no_seed_files(self, tmp_path):
        runner = CliRunner()
        empty_seed = tmp_path / "empty_seed"
        empty_seed.mkdir()

        db_path = tmp_path / "noseed.db"
        db_url = f"sqlite:///{db_path}"
        db = DatabaseManager(db_url)
        db.create_tables()
        db.dispose()

        mock_settings = _make_mock_settings(db_url, seed_home=str(empty_seed))

        with patch(
            "meshcore_hub.common.config.get_collector_settings",
            return_value=mock_settings,
        ):
            result = runner.invoke(
                collector,
                [
                    "--database-url",
                    db_url,
                    "--seed-home",
                    str(empty_seed),
                    "seed",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "No seed files found" in result.output
