"""Tests for configuration settings."""

from meshcore_hub.common.config import (
    CommonSettings,
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

    def test_channel_refresh_interval_seconds(self) -> None:
        """Channel refresh interval defaults to 300."""
        settings = CollectorSettings(_env_file=None)

        assert settings.channel_refresh_interval_seconds == 300

    def test_channel_refresh_interval_seconds_custom(self) -> None:
        """Channel refresh interval can be overridden."""
        settings = CollectorSettings(
            _env_file=None,
            channel_refresh_interval_seconds=60,
        )

        assert settings.channel_refresh_interval_seconds == 60


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

    def test_network_announcement_default_none(self) -> None:
        """Test that network_announcement defaults to None."""
        settings = WebSettings(_env_file=None)

        assert settings.network_announcement is None
