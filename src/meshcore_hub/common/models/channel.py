"""Channel model for database-backed decrypt keys."""

import hashlib
from enum import Enum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin


class ChannelVisibility(str, Enum):
    """Channel visibility/permission levels."""

    COMMUNITY = "community"
    MEMBER = "member"
    OPERATOR = "operator"
    ADMIN = "admin"


class Channel(Base, UUIDMixin, TimestampMixin):
    """Channel model for database-backed decrypt keys with permission-based visibility.

    Attributes:
        id: UUID primary key
        name: Channel display name (unique, non-empty)
        key_hex: Secret key as uppercase hex (supports AES-128 and AES-256)
        channel_hash: First byte of SHA-256 of key_hex (2-char uppercase hex)
        visibility: Permission level (community, member, operator, admin)
        enabled: Whether the channel is active
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "channels"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    key_hex: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    channel_hash: Mapped[str] = mapped_column(String(2), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20), default=ChannelVisibility.COMMUNITY.value, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Channel(name={self.name}, hash={self.channel_hash}, visibility={self.visibility})>"

    @staticmethod
    def compute_channel_hash(key_hex: str) -> str:
        """Compute channel hash (first byte of SHA-256 of key_hex)."""
        return hashlib.sha256(bytes.fromhex(key_hex)).digest()[:1].hex().upper()

    @property
    def masked_key(self) -> str:
        """Return masked key showing first/last 4 chars."""
        if len(self.key_hex) <= 8:
            return self.key_hex
        return f"{self.key_hex[:4]}...{self.key_hex[-4:]}"
