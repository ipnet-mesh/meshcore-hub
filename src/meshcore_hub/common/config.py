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

    # Data home directory (base for all service data directories)
    data_home: str = Field(
        default="./data",
        description="Base directory for service data (e.g., ./data or /data)",
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
    mqtt_prefix: str = Field(default="meshcore", description="MQTT topic prefix")
    mqtt_tls: bool = Field(
        default=False, description="Enable TLS/SSL for MQTT connection"
    )


class InterfaceSettings(CommonSettings):
    """Settings for the Interface component."""

    # Mode
    interface_mode: InterfaceMode = Field(
        default=InterfaceMode.RECEIVER,
        description="Interface mode: RECEIVER or SENDER",
    )

    # Serial connection
    serial_port: str = Field(default="/dev/ttyUSB0", description="Serial port path")
    serial_baud: int = Field(default=115200, description="Serial baud rate")

    # Mock device
    mock_device: bool = Field(default=False, description="Use mock device for testing")

    # Device name
    meshcore_device_name: Optional[str] = Field(
        default=None, description="Device/node name (optional)"
    )

    # Contact cleanup settings
    contact_cleanup_enabled: bool = Field(
        default=True,
        description="Enable automatic removal of stale contacts from companion node",
    )
    contact_cleanup_days: int = Field(
        default=7,
        description="Remove contacts not advertised for this many days",
        ge=1,
    )


class CollectorSettings(CommonSettings):
    """Settings for the Collector component."""

    # Database - default uses data_home/collector/meshcore.db
    database_url: Optional[str] = Field(
        default=None,
        description="SQLAlchemy database URL (default: sqlite:///{data_home}/collector/meshcore.db)",
    )

    # Seed home directory - contains initial data files (node_tags.yaml, members.yaml)
    seed_home: str = Field(
        default="./seed",
        description="Directory containing seed data files (default: ./seed)",
    )

    # Webhook URLs (empty = disabled)
    webhook_advertisement_url: Optional[str] = Field(
        default=None, description="Webhook URL for advertisement events"
    )
    webhook_advertisement_secret: Optional[str] = Field(
        default=None, description="Secret/API key for advertisement webhook"
    )
    webhook_message_url: Optional[str] = Field(
        default=None, description="Webhook URL for all message events"
    )
    webhook_message_secret: Optional[str] = Field(
        default=None, description="Secret/API key for message webhook"
    )
    webhook_channel_message_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for channel messages (overrides message_url)",
    )
    webhook_channel_message_secret: Optional[str] = Field(
        default=None, description="Secret for channel message webhook"
    )
    webhook_direct_message_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for direct messages (overrides message_url)",
    )
    webhook_direct_message_secret: Optional[str] = Field(
        default=None, description="Secret for direct message webhook"
    )

    # Global webhook settings
    webhook_timeout: float = Field(default=10.0, description="Webhook request timeout")
    webhook_max_retries: int = Field(default=3, description="Max retry attempts")
    webhook_retry_backoff: float = Field(
        default=2.0, description="Retry backoff multiplier"
    )

    # Data retention / cleanup settings
    data_retention_enabled: bool = Field(
        default=True, description="Enable automatic event data cleanup"
    )
    data_retention_days: int = Field(
        default=30, description="Number of days to retain event data", ge=1
    )
    data_retention_interval_hours: int = Field(
        default=24,
        description="Hours between automatic cleanup runs (applies to both events and nodes)",
        ge=1,
    )

    # Node cleanup settings
    node_cleanup_enabled: bool = Field(
        default=True, description="Enable automatic cleanup of inactive nodes"
    )
    node_cleanup_days: int = Field(
        default=7,
        description="Remove nodes not seen for this many days (last_seen)",
        ge=1,
    )

    @property
    def collector_data_dir(self) -> str:
        """Get the collector data directory path."""
        from pathlib import Path

        return str(Path(self.data_home) / "collector")

    @property
    def effective_database_url(self) -> str:
        """Get the effective database URL, using default if not set."""
        if self.database_url:
            return self.database_url
        from pathlib import Path

        db_path = Path(self.data_home) / "collector" / "meshcore.db"
        return f"sqlite:///{db_path}"

    @property
    def effective_seed_home(self) -> str:
        """Get the effective seed home directory."""
        from pathlib import Path

        return str(Path(self.seed_home))

    @property
    def node_tags_file(self) -> str:
        """Get the path to node_tags.yaml in seed_home."""
        from pathlib import Path

        return str(Path(self.effective_seed_home) / "node_tags.yaml")

    @property
    def members_file(self) -> str:
        """Get the path to members.yaml in seed_home."""
        from pathlib import Path

        return str(Path(self.effective_seed_home) / "members.yaml")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate database URL format."""
        # None is allowed - will use default
        return v


class APISettings(CommonSettings):
    """Settings for the API component."""

    # Server binding
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")

    # Database - default uses data_home/collector/meshcore.db (same as collector)
    database_url: Optional[str] = Field(
        default=None,
        description="SQLAlchemy database URL (default: sqlite:///{data_home}/collector/meshcore.db)",
    )

    # Authentication
    api_read_key: Optional[str] = Field(default=None, description="Read-only API key")
    api_admin_key: Optional[str] = Field(
        default=None, description="Admin API key (full access)"
    )

    @property
    def effective_database_url(self) -> str:
        """Get the effective database URL, using default if not set."""
        if self.database_url:
            return self.database_url
        from pathlib import Path

        db_path = Path(self.data_home) / "collector" / "meshcore.db"
        return f"sqlite:///{db_path}"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate database URL format."""
        # None is allowed - will use default
        return v


class WebSettings(CommonSettings):
    """Settings for the Web Dashboard component."""

    # Server binding
    web_host: str = Field(default="0.0.0.0", description="Web server host")
    web_port: int = Field(default=8080, description="Web server port")

    # Timezone for date/time display (uses standard TZ environment variable)
    tz: str = Field(default="UTC", description="Timezone for displaying dates/times")

    # Theme (dark or light, default dark)
    web_theme: str = Field(
        default="dark",
        description="Default theme for the web dashboard (dark or light)",
    )

    # Admin interface (disabled by default for security)
    web_admin_enabled: bool = Field(
        default=False,
        description="Enable admin interface at /a/ (requires OAuth2Proxy in front)",
    )

    # API connection
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="API server base URL",
    )
    api_key: Optional[str] = Field(default=None, description="API key for queries")

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
    network_radio_config: Optional[str] = Field(
        default=None, description="Radio configuration details"
    )
    network_contact_email: Optional[str] = Field(
        default=None, description="Contact email address"
    )
    network_contact_discord: Optional[str] = Field(
        default=None, description="Discord server link"
    )
    network_contact_github: Optional[str] = Field(
        default=None, description="GitHub repository URL"
    )
    network_contact_youtube: Optional[str] = Field(
        default=None, description="YouTube channel URL"
    )
    network_welcome_text: Optional[str] = Field(
        default=None, description="Welcome text for homepage"
    )

    # Feature flags (control which pages are visible in the web dashboard)
    feature_dashboard: bool = Field(
        default=True, description="Enable the /dashboard page"
    )
    feature_nodes: bool = Field(default=True, description="Enable the /nodes pages")
    feature_advertisements: bool = Field(
        default=True, description="Enable the /advertisements page"
    )
    feature_messages: bool = Field(
        default=True, description="Enable the /messages page"
    )
    feature_map: bool = Field(
        default=True, description="Enable the /map page and /map/data endpoint"
    )
    feature_members: bool = Field(default=True, description="Enable the /members page")
    feature_pages: bool = Field(
        default=True, description="Enable custom markdown pages"
    )

    # Content directory (contains pages/ and media/ subdirectories)
    content_home: Optional[str] = Field(
        default=None,
        description="Directory containing custom content (pages/, media/) (default: ./content)",
    )

    @property
    def features(self) -> dict[str, bool]:
        """Get feature flags as a dictionary.

        Automatic dependencies:
        - Dashboard requires at least one of nodes/advertisements/messages.
        - Map requires nodes (map displays node locations).
        """
        has_dashboard_content = (
            self.feature_nodes or self.feature_advertisements or self.feature_messages
        )
        return {
            "dashboard": self.feature_dashboard and has_dashboard_content,
            "nodes": self.feature_nodes,
            "advertisements": self.feature_advertisements,
            "messages": self.feature_messages,
            "map": self.feature_map and self.feature_nodes,
            "members": self.feature_members,
            "pages": self.feature_pages,
        }

    @property
    def effective_content_home(self) -> str:
        """Get the effective content home directory."""
        from pathlib import Path

        return str(Path(self.content_home or "./content"))

    @property
    def effective_pages_home(self) -> str:
        """Get the effective pages directory (content_home/pages)."""
        from pathlib import Path

        return str(Path(self.effective_content_home) / "pages")

    @property
    def effective_media_home(self) -> str:
        """Get the effective media directory (content_home/media)."""
        from pathlib import Path

        return str(Path(self.effective_content_home) / "media")

    @property
    def web_data_dir(self) -> str:
        """Get the web data directory path."""
        from pathlib import Path

        return str(Path(self.data_home) / "web")


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
