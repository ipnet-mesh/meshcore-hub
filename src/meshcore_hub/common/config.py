"""Pydantic Settings for MeshCore Hub configuration."""

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    """Log level enumeration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class InterfaceMode(str, Enum):
    """Interface component mode."""

    RECEIVER = "RECEIVER"
    SENDER = "SENDER"


class CommonSettings(BaseSettings):
    """Common settings shared by all components."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Logging
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")

    # MQTT Broker
    mqtt_host: str = Field(default="localhost", description="MQTT broker host")
    mqtt_port: int = Field(default=1883, description="MQTT broker port")
    mqtt_username: Optional[str] = Field(
        default=None, description="MQTT username (optional)"
    )
    mqtt_password: Optional[str] = Field(
        default=None, description="MQTT password (optional)"
    )
    mqtt_prefix: str = Field(
        default="meshcore", description="MQTT topic prefix"
    )


class InterfaceSettings(CommonSettings):
    """Settings for the Interface component."""

    # Mode
    interface_mode: InterfaceMode = Field(
        default=InterfaceMode.RECEIVER,
        description="Interface mode: RECEIVER or SENDER",
    )

    # Serial connection
    serial_port: str = Field(
        default="/dev/ttyUSB0", description="Serial port path"
    )
    serial_baud: int = Field(default=115200, description="Serial baud rate")

    # Mock device
    mock_device: bool = Field(
        default=False, description="Use mock device for testing"
    )


class CollectorSettings(CommonSettings):
    """Settings for the Collector component."""

    # Database
    database_url: str = Field(
        default="sqlite:///./meshcore.db",
        description="SQLAlchemy database URL",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            raise ValueError("Database URL cannot be empty")
        return v


class APISettings(CommonSettings):
    """Settings for the API component."""

    # Server binding
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")

    # Database
    database_url: str = Field(
        default="sqlite:///./meshcore.db",
        description="SQLAlchemy database URL",
    )

    # Authentication
    api_read_key: Optional[str] = Field(
        default=None, description="Read-only API key"
    )
    api_admin_key: Optional[str] = Field(
        default=None, description="Admin API key (full access)"
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            raise ValueError("Database URL cannot be empty")
        return v


class WebSettings(CommonSettings):
    """Settings for the Web Dashboard component."""

    # Server binding
    web_host: str = Field(default="0.0.0.0", description="Web server host")
    web_port: int = Field(default=8080, description="Web server port")

    # API connection
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="API server base URL",
    )
    api_key: Optional[str] = Field(
        default=None, description="API key for queries"
    )

    # Network information
    network_domain: Optional[str] = Field(
        default=None, description="Network domain name"
    )
    network_name: str = Field(
        default="MeshCore Network", description="Network display name"
    )
    network_city: Optional[str] = Field(
        default=None, description="Network city location"
    )
    network_country: Optional[str] = Field(
        default=None, description="Network country (ISO 3166-1 alpha-2)"
    )
    network_location: Optional[str] = Field(
        default=None, description="Network location (lat,lon)"
    )
    network_radio_config: Optional[str] = Field(
        default=None, description="Radio configuration details"
    )
    network_contact_email: Optional[str] = Field(
        default=None, description="Contact email address"
    )
    network_contact_discord: Optional[str] = Field(
        default=None, description="Discord server link"
    )

    # Members file
    members_file: str = Field(
        default="members.json", description="Path to members JSON file"
    )


def get_common_settings() -> CommonSettings:
    """Get common settings instance."""
    return CommonSettings()


def get_interface_settings() -> InterfaceSettings:
    """Get interface settings instance."""
    return InterfaceSettings()


def get_collector_settings() -> CollectorSettings:
    """Get collector settings instance."""
    return CollectorSettings()


def get_api_settings() -> APISettings:
    """Get API settings instance."""
    return APISettings()


def get_web_settings() -> WebSettings:
    """Get web settings instance."""
    return WebSettings()
