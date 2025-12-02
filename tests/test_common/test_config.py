"""Tests for configuration settings."""

import pytest

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
        """Test default setting values."""
        settings = CommonSettings()

        assert settings.log_level == LogLevel.INFO
        assert settings.mqtt_host == "localhost"
        assert settings.mqtt_port == 1883
        assert settings.mqtt_username is None
        assert settings.mqtt_password is None
        assert settings.mqtt_prefix == "meshcore"


class TestInterfaceSettings:
    """Tests for InterfaceSettings."""

    def test_default_values(self) -> None:
        """Test default setting values."""
        settings = InterfaceSettings()

        assert settings.interface_mode == InterfaceMode.RECEIVER
        assert settings.serial_port == "/dev/ttyUSB0"
        assert settings.serial_baud == 115200
        assert settings.mock_device is False


class TestCollectorSettings:
    """Tests for CollectorSettings."""

    def test_default_values(self) -> None:
        """Test default setting values."""
        settings = CollectorSettings()

        assert settings.database_url == "sqlite:///./meshcore.db"

    def test_database_url_validation(self) -> None:
        """Test database URL validation."""
        with pytest.raises(ValueError):
            CollectorSettings(database_url="")


class TestAPISettings:
    """Tests for APISettings."""

    def test_default_values(self) -> None:
        """Test default setting values."""
        settings = APISettings()

        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8000
        assert settings.database_url == "sqlite:///./meshcore.db"
        assert settings.api_read_key is None
        assert settings.api_admin_key is None


class TestWebSettings:
    """Tests for WebSettings."""

    def test_default_values(self) -> None:
        """Test default setting values."""
        settings = WebSettings()

        assert settings.web_host == "0.0.0.0"
        assert settings.web_port == 8080
        assert settings.api_base_url == "http://localhost:8000"
        assert settings.network_name == "MeshCore Network"
        assert settings.members_file == "members.json"
