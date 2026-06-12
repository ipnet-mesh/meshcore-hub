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

    def test_raw_packet_retention_defaults_to_global(self) -> None:
        """Unset raw_packet_retention_days resolves to data_retention_days."""
        settings = CollectorSettings(_env_file=None, data_retention_days=12)

        assert settings.raw_packet_retention_days is None
        assert settings.effective_raw_packet_retention_days == 12

    def test_raw_packet_retention_explicit_override(self) -> None:
        """An explicit raw_packet_retention_days wins over the global value."""
        settings = CollectorSettings(
            _env_file=None, data_retention_days=30, raw_packet_retention_days=3
        )

        assert settings.effective_raw_packet_retention_days == 3

    def test_raw_packet_capture_disabled_by_default(self) -> None:
        """raw_packet_capture_enabled defaults to False."""
        settings = CollectorSettings(_env_file=None)

        assert settings.raw_packet_capture_enabled is False

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

    def test_channels_file_path(self) -> None:
        """channels_file property resolves to seed_home/channels.yaml."""
        settings = CollectorSettings(_env_file=None, seed_home="/seed/data")

        assert settings.channels_file == "/seed/data/channels.yaml"

    def test_channels_file_default(self) -> None:
        """channels_file uses default seed_home."""
        settings = CollectorSettings(_env_file=None)

        assert settings.channels_file.endswith("channels.yaml")
        assert "seed" in settings.channels_file


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

    def test_feature_channels_default_true(self) -> None:
        """Test that feature_channels defaults to True."""
        settings = WebSettings(_env_file=None)

        assert settings.feature_channels is True

    def test_radio_config_defaults(self) -> None:
        """Test that radio config fields default to EU/UK Narrow values."""
        settings = WebSettings(_env_file=None)

        assert settings.network_radio_profile == "EU/UK Narrow"
        assert settings.network_radio_frequency == 869.618
        assert settings.network_radio_bandwidth == 62.5
        assert settings.network_radio_spreading_factor == 8
        assert settings.network_radio_coding_rate == 8
        assert settings.network_radio_tx_power == 22.0

    def test_radio_config_no_legacy_field(self) -> None:
        """Test that network_radio_config no longer exists."""
        settings = WebSettings(_env_file=None)
        assert not hasattr(settings, "network_radio_config")

    def test_radio_config_custom_frequency(self) -> None:
        """Test that frequency can be set as a float."""
        settings = WebSettings(
            _env_file=None,
            network_radio_frequency=915.0,
        )
        assert settings.network_radio_frequency == 915.0

    def test_feature_channels_override(self) -> None:
        """Test that feature_channels can be disabled."""
        settings = WebSettings(_env_file=None, feature_channels=False)

        assert settings.feature_channels is False

    def test_features_dict_includes_channels(self) -> None:
        """Test that features dict includes channels key."""
        settings = WebSettings(_env_file=None)
        features = settings.features

        assert "channels" in features
        assert features["channels"] is True

    def test_features_dashboard_auto_disables(self) -> None:
        """Dashboard disables when nodes, ads, and messages all off."""
        settings = WebSettings(
            _env_file=None,
            feature_dashboard=True,
            feature_nodes=False,
            feature_advertisements=False,
            feature_messages=False,
        )
        assert settings.features["dashboard"] is False

    def test_features_map_auto_disables_without_nodes(self) -> None:
        """Map disables when nodes feature is off."""
        settings = WebSettings(
            _env_file=None,
            feature_map=True,
            feature_nodes=False,
        )
        assert settings.features["map"] is False

    def test_features_members_auto_disables_without_oidc(self) -> None:
        """Members disables when OIDC is not enabled."""
        settings = WebSettings(
            _env_file=None,
            feature_members=True,
            oidc_enabled=False,
        )
        assert settings.features["members"] is False

    def test_features_all_enabled_by_default(self) -> None:
        """All features are enabled with default settings."""
        settings = WebSettings(
            _env_file=None,
            oidc_enabled=True,
        )
        features = settings.features
        assert features["dashboard"] is True
        assert features["nodes"] is True
        assert features["advertisements"] is True
        assert features["messages"] is True
        assert features["map"] is True
        assert features["members"] is True
        assert features["channels"] is True
        assert features["pages"] is True
        assert features["radio_config"] is True

    def test_feature_radio_config_default_true(self) -> None:
        """Test that feature_radio_config defaults to True."""
        settings = WebSettings(_env_file=None)

        assert settings.feature_radio_config is True

    def test_feature_radio_config_can_disable(self) -> None:
        """Test that feature_radio_config can be disabled."""
        settings = WebSettings(_env_file=None, feature_radio_config=False)

        assert settings.feature_radio_config is False
        assert settings.features["radio_config"] is False
