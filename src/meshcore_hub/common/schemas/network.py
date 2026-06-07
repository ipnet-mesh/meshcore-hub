"""Pydantic schemas for network configuration."""

from typing import Any, Optional

from pydantic import BaseModel


class RadioConfig(BaseModel):
    """Radio configuration with individual fields.

    Frequency, bandwidth, and TX power are stored as raw floats.
    Use ``format_for_display()`` to produce formatted strings with units
    (e.g. ``"869.618MHz"``, ``"62.5kHz"``, ``"22dBm"``).
    """

    profile: Optional[str] = None
    frequency: Optional[float] = None
    bandwidth: Optional[float] = None
    spreading_factor: Optional[int] = None
    coding_rate: Optional[int] = None
    tx_power: Optional[float] = None

    def format_for_display(self) -> dict[str, Any]:
        """Return a dict with formatted strings for display.

        Numeric fields are formatted with ``:g`` to strip trailing zeros.
        ``None`` values are preserved as ``None``.
        """
        return {
            "profile": self.profile,
            "frequency": (
                f"{self.frequency:g}MHz" if self.frequency is not None else None
            ),
            "bandwidth": (
                f"{self.bandwidth:g}kHz" if self.bandwidth is not None else None
            ),
            "spreading_factor": self.spreading_factor,
            "coding_rate": self.coding_rate,
            "tx_power": f"{self.tx_power:g}dBm" if self.tx_power is not None else None,
        }
