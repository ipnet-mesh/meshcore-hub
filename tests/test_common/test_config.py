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

    def test_websocket_transport_settings(self) -> None:
        """Test MQTT websocket transport settings."""
        settings = CommonSettings(
            _env_file=None,
            mqtt_transport="websockets",
            mqtt_ws_path="/",
        )

        assert settings.mqtt_transport.value == "websockets"
        assert settings.mqtt_ws_path == "/"


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

    def test_collector_ingest_mode_letsmesh_upload(self) -> None:
        """Test collector ingest mode can be set to LetsMesh upload."""
        settings = CollectorSettings(
            _env_file=None,
            collector_ingest_mode="letsmesh_upload",
        )

        assert settings.collector_ingest_mode.value == "letsmesh_upload"

    def test_collector_letsmesh_decoder_keys_list(self) -> None:
        """LetsMesh decoder keys are parsed from comma/space-separated env values."""
        settings = CollectorSettings(
            _env_file=None,
            collector_letsmesh_decoder_keys="aa11, bb22 cc33",
        )

        assert settings.collector_letsmesh_decoder_keys_list == [
            "aa11",
            "bb22",
            "cc33",
        ]


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

    def test_web_datetime_locale_default_and_override(self) -> None:
        """Date formatting locale has sensible default and can be overridden."""
        default_settings = WebSettings(_env_file=None)
        custom_settings = WebSettings(_env_file=None, web_datetime_locale="en-GB")

        assert default_settings.web_datetime_locale == "en-US"
        assert custom_settings.web_datetime_locale == "en-GB"
