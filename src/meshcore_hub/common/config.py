"""Pydantic Settings for MeshCore Hub configuration."""

from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    """Log level enumeration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MQTTTransport(str, Enum):
    """MQTT transport type."""

    TCP = "tcp"
    WEBSOCKETS = "websockets"


class DatabaseBackend(str, Enum):
    """Database backend selector."""

    SQLITE = "sqlite"
    POSTGRES = "postgres"


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

    # Database backend selection and connection components.
    # SQLite is the zero-config default; set DATABASE_BACKEND=postgres (plus the
    # DATABASE_* component vars) to use Postgres. An explicit DATABASE_URL overrides
    # everything (managed/external Postgres, tests).
    database_backend: DatabaseBackend = Field(
        default=DatabaseBackend.SQLITE,
        description="Database backend: 'sqlite' (default) or 'postgres'",
    )
    database_url: Optional[str] = Field(
        default=None,
        description=(
            "Explicit SQLAlchemy database URL; overrides DATABASE_BACKEND/component vars. "
            "Default: sqlite:///{data_home}/collector/meshcore.db"
        ),
    )
    database_host: Optional[str] = Field(
        default=None,
        description="Postgres host (required when DATABASE_BACKEND=postgres)",
    )
    database_port: int = Field(default=5432, description="Postgres port")
    database_name: str = Field(
        default="meshcorehub", description="Postgres database name"
    )
    database_schema: str = Field(
        default="meshcorehub",
        description="Postgres schema (namespace); override per instance on a shared cluster",
    )
    database_user: str = Field(default="meshcorehub", description="Postgres role/user")
    database_password: Optional[str] = Field(
        default=None,
        description="Postgres password (required when DATABASE_BACKEND=postgres)",
    )

    @property
    def effective_database_url(self) -> str:
        """Resolve the SQLAlchemy database URL.

        Precedence: explicit DATABASE_URL > postgres (assembled from components) >
        SQLite default under DATA_HOME. Fails fast for a misconfigured postgres backend
        rather than silently falling back to SQLite.
        """
        if self.database_url:
            return self.database_url
        if self.database_backend == DatabaseBackend.POSTGRES:
            missing = [
                name
                for name, value in (
                    ("DATABASE_HOST", self.database_host),
                    ("DATABASE_NAME", self.database_name),
                    ("DATABASE_USER", self.database_user),
                    ("DATABASE_PASSWORD", self.database_password),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "DATABASE_BACKEND=postgres requires: " + ", ".join(missing)
                )
            from urllib.parse import quote_plus

            user = quote_plus(self.database_user)
            password = quote_plus(self.database_password or "")
            return (
                f"postgresql+psycopg2://{user}:{password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        from pathlib import Path

        db_path = Path(self.data_home) / "collector" / "meshcore.db"
        return f"sqlite:///{db_path}"

    @property
    def effective_database_schema(self) -> Optional[str]:
        """Postgres schema to scope connections to, or None for SQLite.

        Returns the schema only when the effective URL is Postgres; SQLite has no
        schema concept, so callers leave search_path untouched.
        """
        if self.effective_database_url.startswith(("postgresql", "postgres")):
            return self.database_schema
        return None

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
    mqtt_transport: MQTTTransport = Field(
        default=MQTTTransport.WEBSOCKETS,
        description="MQTT transport protocol (tcp or websockets)",
    )
    mqtt_ws_path: str = Field(
        default="/",
        description="WebSocket path for MQTT transport (used when MQTT_TRANSPORT=websockets)",
    )


class CollectorSettings(CommonSettings):
    """Settings for the Collector component."""

    # Database config (backend selector + connection) is inherited from CommonSettings.

    # Seed home directory - contains initial data files (node_tags.yaml)
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
        default=30,
        description="Remove nodes not seen for this many days (last_seen)",
        ge=1,
    )
    channel_refresh_interval_seconds: int = Field(
        default=300,
        description="Seconds between channel key refresh from database",
        ge=10,
    )

    # Raw packet capture settings
    raw_packet_capture_enabled: bool = Field(
        default=False,
        description="Capture every inbound packets-feed packet into raw_packets",
    )
    raw_packet_retention_days: Optional[int] = Field(
        default=7,
        description=(
            "Days to retain raw packets before cleanup (default 7, independent of "
            "DATA_RETENTION_DAYS)"
        ),
        ge=1,
    )

    @property
    def effective_raw_packet_retention_days(self) -> int:
        """Resolve raw-packet retention, falling back to the global default."""
        if self.raw_packet_retention_days is not None:
            return self.raw_packet_retention_days
        return self.data_retention_days

    @property
    def collector_data_dir(self) -> str:
        """Get the collector data directory path."""
        from pathlib import Path

        return str(Path(self.data_home) / "collector")

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
    def channels_file(self) -> str:
        """Get the path to channels.yaml in seed_home."""
        from pathlib import Path

        return str(Path(self.effective_seed_home) / "channels.yaml")


class APISettings(CommonSettings):
    """Settings for the API component."""

    # Server binding
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")

    # Database config (backend selector + connection) is inherited from CommonSettings.

    # Authentication
    api_read_key: Optional[str] = Field(default=None, description="Read-only API key")
    api_admin_key: Optional[str] = Field(
        default=None, description="Admin API key (full access)"
    )

    # Redis cache
    redis_enabled: bool = Field(
        default=False, description="Enable Redis API response caching"
    )
    redis_host: str = Field(default="localhost", description="Redis server host")
    redis_port: int = Field(default=6379, description="Redis server port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(
        default=None, description="Redis password (optional)"
    )
    redis_key_prefix: str = Field(
        default="hub",
        description="Prefix for all cache keys (isolates multi-instance setups)",
    )
    redis_cache_ttl: int = Field(
        default=30,
        description="Default cache TTL in seconds",
    )
    redis_cache_ttl_dashboard: int = Field(
        default=30,
        description="Cache TTL for dashboard endpoints (seconds)",
    )


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

    # Locale / language (default: English)
    web_locale: str = Field(
        default="en",
        description="Locale/language for the web dashboard (e.g. 'en')",
    )
    web_datetime_locale: str = Field(
        default="en-US",
        description=(
            "Locale used for date/time formatting in the web dashboard "
            "(e.g. 'en-US', 'en-GB')."
        ),
    )

    # Auto-refresh interval for list pages
    web_auto_refresh_seconds: int = Field(
        default=30,
        description="Auto-refresh interval in seconds for list pages (0 to disable)",
    )
    web_debug: bool = Field(
        default=False,
        description="Enable debug mode in the web dashboard",
    )

    # OIDC / OAuth2 authentication
    oidc_enabled: bool = Field(default=False, description="Enable OIDC authentication")
    oidc_client_id: Optional[str] = Field(default=None, description="OIDC client ID")
    oidc_client_secret: Optional[str] = Field(
        default=None, description="OIDC client secret"
    )
    oidc_discovery_url: Optional[str] = Field(
        default=None, description="OIDC discovery URL"
    )
    oidc_redirect_uri: Optional[str] = Field(
        default=None,
        description="OIDC callback URL (overrides auto-derivation)",
    )
    oidc_post_logout_redirect_uri: Optional[str] = Field(
        default=None,
        description=(
            "OIDC post-logout redirect URI (must match Sign-out redirect URIs "
            "in IdP config). Falls back to OIDC_REDIRECT_URI base or request.base_url."
        ),
    )
    oidc_scopes: str = Field(
        default="openid email profile", description="OAuth scopes to request"
    )
    oidc_roles_claim: str = Field(
        default="roles", description="ID token claim containing user roles"
    )
    oidc_role_admin: str = Field(
        default="admin", description="IdP role name for admin access"
    )
    oidc_role_operator: str = Field(
        default="operator", description="IdP role name for operator access"
    )
    oidc_role_member: str = Field(
        default="member", description="IdP role name for member access"
    )
    oidc_role_test: str = Field(
        default="test",
        description="IdP role name for test users (excluded from public views)",
    )
    oidc_session_secret: Optional[str] = Field(
        default=None, description="Secret key for signing session cookies"
    )
    oidc_session_max_age: int = Field(
        default=86400, description="Session cookie lifetime in seconds"
    )
    oidc_cookie_secure: bool = Field(
        default=False, description="HTTPS-only session cookies (enable in production)"
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
    network_radio_profile: str = Field(
        default="EU/UK Narrow", description="Radio profile name"
    )
    network_radio_frequency: float = Field(
        default=869.618, description="Radio frequency (MHz)"
    )
    network_radio_bandwidth: float = Field(
        default=62.5, description="Radio bandwidth (kHz)"
    )
    network_radio_spreading_factor: int = Field(
        default=8, description="Radio spreading factor"
    )
    network_radio_coding_rate: int = Field(default=8, description="Radio coding rate")
    network_radio_tx_power: float = Field(
        default=22.0, description="Radio TX power (dBm)"
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
    network_announcement: Optional[str] = Field(
        default=None,
        description="Markdown announcement text for flash banner (empty = no banner)",
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
    feature_channels: bool = Field(
        default=True, description="Enable the /channels page"
    )
    feature_packets: bool = Field(
        default=True, description="Enable the /packets page (on by default)"
    )
    feature_pages: bool = Field(
        default=True, description="Enable custom markdown pages"
    )
    feature_radio_config: bool = Field(
        default=True, description="Enable radio config panel on home page"
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
        - Members requires OIDC to be enabled (honours OIDC_ENABLED).
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
            "members": self.feature_members and self.oidc_enabled,
            "channels": self.feature_channels,
            "packets": self.feature_packets,
            "pages": self.feature_pages,
            "radio_config": self.feature_radio_config,
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


def get_collector_settings() -> CollectorSettings:
    """Get collector settings instance."""
    return CollectorSettings()


def get_api_settings() -> APISettings:
    """Get API settings instance."""
    return APISettings()


def get_web_settings() -> WebSettings:
    """Get web settings instance."""
    return WebSettings()
