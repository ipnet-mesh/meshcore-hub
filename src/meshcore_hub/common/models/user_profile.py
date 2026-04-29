"""UserProfile model for authenticated user profiles."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from meshcore_hub.common.models.user_profile_node import UserProfileNode


class UserProfile(Base, UUIDMixin, TimestampMixin):
    """UserProfile model for authenticated OIDC users.

    Stores profile information for users who authenticate via OIDC.
    Profiles are auto-created lazily on first access.

    Attributes:
        id: UUID primary key
        user_id: OIDC subject identifier (unique, from IdP 'sub' claim)
        name: User's display name or preferred name (blank initially)
        callsign: Amateur radio callsign (blank initially)
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    callsign: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    node_associations: Mapped[list["UserProfileNode"]] = relationship(
        "UserProfileNode",
        back_populates="user_profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, user_id={self.user_id}, name={self.name})>"
