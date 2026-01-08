"""Tests for configuration settings."""

from meshcore_hub.common.config import (
    CommonSettings,
    InterfaceSettings,
    CollectorSettings,
    APISettings,
    WebSettings,
)


class TestCommonSettings:
    """Tests for CommonSettings."""

    def test_custom_data_home(self) -> None:
        """Test custom DATA_HOME setting."""
        settings = CommonSettings(_env_file=None, data_home="/custom/data")

        assert settings.data_home == "/custom/data"


class TestInterfaceSettings:
    """Tests for InterfaceSettings."""

    def test_custom_values(self) -> None:
        """Test custom setting values."""
        settings = InterfaceSettings(
            _env_file=None, serial_port="/dev/ttyACM0", serial_baud=9600
        )

        assert settings.serial_port == "/dev/ttyACM0"
        assert settings.serial_baud == 9600


class TestCollectorSettings:
    """Tests for CollectorSettings."""

    def test_custom_data_home(self) -> None:
        """Test that custom data_home affects effective paths."""
        settings = CollectorSettings(_env_file=None, data_home="/custom/data")

        assert (
            settings.effective_database_url
            == "sqlite:////custom/data/collector/meshcore.db"
        )
        assert settings.collector_data_dir == "/custom/data/collector"

    def test_explicit_database_url_overrides(self) -> None:
        """Test that explicit database_url overrides the default."""
        settings = CollectorSettings(
            _env_file=None, database_url="postgresql://user@host/db"
        )

        assert settings.database_url == "postgresql://user@host/db"
        assert settings.effective_database_url == "postgresql://user@host/db"

    def test_explicit_seed_home_overrides(self) -> None:
        """Test that explicit seed_home overrides the default."""
        settings = CollectorSettings(_env_file=None, seed_home="/seed/data")

        assert settings.seed_home == "/seed/data"
        assert settings.effective_seed_home == "/seed/data"
        assert settings.node_tags_file == "/seed/data/node_tags.yaml"
        assert settings.members_file == "/seed/data/members.yaml"


class TestAPISettings:
    """Tests for APISettings."""

    def test_custom_data_home(self) -> None:
        """Test that custom data_home affects effective database path."""
        settings = APISettings(_env_file=None, data_home="/custom/data")

        assert (
            settings.effective_database_url
            == "sqlite:////custom/data/collector/meshcore.db"
        )

    def test_explicit_database_url_overrides(self) -> None:
        """Test that explicit database_url overrides the default."""
        settings = APISettings(_env_file=None, database_url="postgresql://user@host/db")

        assert settings.database_url == "postgresql://user@host/db"
        assert settings.effective_database_url == "postgresql://user@host/db"


class TestWebSettings:
    """Tests for WebSettings."""

    def test_custom_data_home(self) -> None:
        """Test that custom data_home affects effective paths."""
        settings = WebSettings(_env_file=None, data_home="/custom/data")

        assert settings.web_data_dir == "/custom/data/web"
