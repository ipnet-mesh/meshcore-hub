"""Member model for network member information."""

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin


class Member(Base, UUIDMixin, TimestampMixin):
    """Member model for network member information.

    Stores information about network members/operators.

    Attributes:
        id: UUID primary key
        name: Member's display name
        callsign: Amateur radio callsign (optional)
        role: Member's role in the network (optional)
        description: Additional description (optional)
        contact: Contact information (optional)
        public_key: Associated node public key (optional, 64-char hex)
        created_at: Record creation timestamp
        updated_at: Record update timestamp
    """

    __tablename__ = "members"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    callsign: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    role: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    contact: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    public_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Member(id={self.id}, name={self.name}, callsign={self.callsign})>"
