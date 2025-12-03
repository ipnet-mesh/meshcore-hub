"""Tests for configuration settings."""

from meshcore_hub.common.config import (
    CommonSettings,
    InterfaceSettings,
    CollectorSettings,
    APISettings,
    WebSettings,
    LogLevel,
    InterfaceMode,
)


class TestCommonSettings:
    """Tests for CommonSettings."""

    def test_default_values(self) -> None:
        """Test default setting values without .env file influence."""
        settings = CommonSettings(_env_file=None)

        assert settings.data_home == "./data"
        assert settings.log_level == LogLevel.INFO
        assert settings.mqtt_host == "localhost"
        assert settings.mqtt_port == 1883
        assert settings.mqtt_username is None
        assert settings.mqtt_password is None
        assert settings.mqtt_prefix == "meshcore"

    def test_custom_data_home(self) -> None:
        """Test custom DATA_HOME setting."""
        settings = CommonSettings(_env_file=None, data_home="/custom/data")

        assert settings.data_home == "/custom/data"


class TestInterfaceSettings:
    """Tests for InterfaceSettings."""

    def test_default_values(self) -> None:
        """Test default setting values without .env file influence."""
        settings = InterfaceSettings(_env_file=None)

        assert settings.interface_mode == InterfaceMode.RECEIVER
        assert settings.serial_port == "/dev/ttyUSB0"
        assert settings.serial_baud == 115200
        assert settings.mock_device is False


class TestCollectorSettings:
    """Tests for CollectorSettings."""

    def test_default_values(self) -> None:
        """Test default setting values without .env file influence."""
        settings = CollectorSettings(_env_file=None)

        # database_url is None by default, effective_database_url computes it
        assert settings.database_url is None
        # Path normalizes ./data to data
        assert settings.effective_database_url == "sqlite:///data/collector/meshcore.db"
        assert settings.data_home == "./data"
        assert settings.collector_data_dir == "data/collector"

        # seed_home defaults to ./seed (normalized to "seed")
        assert settings.seed_home == "./seed"
        assert settings.effective_seed_home == "seed"
        # node_tags_file and members_file are derived from effective_seed_home
        assert settings.node_tags_file == "seed/node_tags.json"
        assert settings.members_file == "seed/members.json"

    def test_custom_data_home(self) -> None:
        """Test that custom data_home affects effective paths."""
        settings = CollectorSettings(_env_file=None, data_home="/custom/data")

        assert (
            settings.effective_database_url
            == "sqlite:////custom/data/collector/meshcore.db"
        )
        assert settings.collector_data_dir == "/custom/data/collector"
        # seed_home is independent of data_home
        assert settings.effective_seed_home == "seed"
        assert settings.node_tags_file == "seed/node_tags.json"
        assert settings.members_file == "seed/members.json"

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
        assert settings.node_tags_file == "/seed/data/node_tags.json"
        assert settings.members_file == "/seed/data/members.json"


class TestAPISettings:
    """Tests for APISettings."""

    def test_default_values(self) -> None:
        """Test default setting values without .env file influence."""
        settings = APISettings(_env_file=None)

        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8000
        # database_url is None by default, effective_database_url computes it
        assert settings.database_url is None
        # Path normalizes ./data to data
        assert settings.effective_database_url == "sqlite:///data/collector/meshcore.db"
        assert settings.api_read_key is None
        assert settings.api_admin_key is None

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

    def test_default_values(self) -> None:
        """Test default setting values without .env file influence."""
        settings = WebSettings(_env_file=None)

        assert settings.web_host == "0.0.0.0"
        assert settings.web_port == 8080
        assert settings.api_base_url == "http://localhost:8000"
        assert settings.network_name == "MeshCore Network"
        # Path normalizes ./data to data
        assert settings.web_data_dir == "data/web"

    def test_custom_data_home(self) -> None:
        """Test that custom data_home affects effective paths."""
        settings = WebSettings(_env_file=None, data_home="/custom/data")

        assert settings.web_data_dir == "/custom/data/web"
