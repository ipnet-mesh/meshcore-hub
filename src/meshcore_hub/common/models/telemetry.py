"""Telemetry model for storing sensor data."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from meshcore_hub.common.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class Telemetry(Base, UUIDMixin, TimestampMixin):
    """Telemetry model for storing sensor data from network nodes.

    Attributes:
        id: UUID primary key
        receiver_node_id: FK to nodes (receiving interface)
        node_id: FK to nodes (reporting node)
        node_public_key: Reporting node's public key
        lpp_data: Raw LPP-encoded sensor data
        parsed_data: Decoded sensor readings as JSON
        received_at: When received by interface
        created_at: Record creation timestamp
    """

    __tablename__ = "telemetry"

    receiver_node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_public_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    lpp_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    parsed_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    event_hash: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        unique=True,
    )

    __table_args__ = (Index("ix_telemetry_received_at", "received_at"),)

    def __repr__(self) -> str:
        return (
            f"<Telemetry(id={self.id}, node_public_key={self.node_public_key[:12]}...)>"
        )
