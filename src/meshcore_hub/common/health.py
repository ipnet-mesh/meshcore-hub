"""Health check utilities for MeshCore Hub components.

This module provides utilities for:
1. Writing health status to a file (for Docker HEALTHCHECK)
2. Reading health status from a file (for health check commands)
3. Running periodic health updates
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Default health file locations
DEFAULT_HEALTH_DIR = "/tmp/meshcore-hub"
DEFAULT_HEALTH_FILE_INTERFACE = "interface-health.json"
DEFAULT_HEALTH_FILE_COLLECTOR = "collector-health.json"

# Health status is considered stale after this many seconds
HEALTH_STALE_THRESHOLD = 60


@dataclass
class HealthStatus:
    """Health status data structure."""

    healthy: bool
    component: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "component": self.component,
            "timestamp": self.timestamp,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HealthStatus":
        """Create from dictionary."""
        return cls(
            healthy=data.get("healthy", False),
            component=data.get("component", "unknown"),
            timestamp=data.get("timestamp", ""),
            details=data.get("details", {}),
        )

    def is_stale(self, threshold_seconds: int = HEALTH_STALE_THRESHOLD) -> bool:
        """Check if this health status is stale.

        Args:
            threshold_seconds: Maximum age in seconds

        Returns:
            True if the status is older than threshold
        """
        try:
            status_time = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - status_time).total_seconds()
            return age > threshold_seconds
        except (ValueError, TypeError):
            return True


def get_health_dir() -> Path:
    """Get the health directory path.

    Returns:
        Path to health directory
    """
    health_dir = os.environ.get("HEALTH_DIR", DEFAULT_HEALTH_DIR)
    return Path(health_dir)


def get_health_file(component: str) -> Path:
    """Get the health file path for a component.

    Args:
        component: Component name (interface, collector)

    Returns:
        Path to health file
    """
    health_dir = get_health_dir()
    if component == "interface":
        return health_dir / DEFAULT_HEALTH_FILE_INTERFACE
    elif component == "collector":
        return health_dir / DEFAULT_HEALTH_FILE_COLLECTOR
    else:
        return health_dir / f"{component}-health.json"


def write_health_status(status: HealthStatus) -> bool:
    """Write health status to file.

    Args:
        status: Health status to write

    Returns:
        True if write was successful
    """
    health_file = get_health_file(status.component)

    try:
        # Ensure directory exists
        health_file.parent.mkdir(parents=True, exist_ok=True)

        # Write status atomically
        temp_file = health_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(status.to_dict(), f)

        temp_file.replace(health_file)
        return True

    except Exception as e:
        logger.error(f"Failed to write health status: {e}")
        return False


def read_health_status(component: str) -> Optional[HealthStatus]:
    """Read health status from file.

    Args:
        component: Component name

    Returns:
        Health status or None if not available
    """
    health_file = get_health_file(component)

    try:
        if not health_file.exists():
            return None

        with open(health_file) as f:
            data = json.load(f)

        return HealthStatus.from_dict(data)

    except Exception as e:
        logger.error(f"Failed to read health status: {e}")
        return None


def check_health(
    component: str, stale_threshold: int = HEALTH_STALE_THRESHOLD
) -> tuple[bool, str]:
    """Check health status for a component.

    Args:
        component: Component name
        stale_threshold: Maximum age of health status in seconds

    Returns:
        Tuple of (is_healthy, message)
    """
    status = read_health_status(component)

    if status is None:
        return False, f"No health status found for {component}"

    if status.is_stale(stale_threshold):
        return False, f"Health status is stale (older than {stale_threshold}s)"

    if not status.healthy:
        details = status.details
        reasons = []
        for key, value in details.items():
            if key.endswith("_connected") and value is False:
                reasons.append(f"{key.replace('_', ' ')}")
            elif key == "running" and value is False:
                reasons.append("not running")
        reason_str = ", ".join(reasons) if reasons else "unhealthy"
        return False, f"Component is {reason_str}"

    return True, "healthy"


def clear_health_status(component: str) -> bool:
    """Remove health status file.

    Args:
        component: Component name

    Returns:
        True if file was removed or didn't exist
    """
    health_file = get_health_file(component)

    try:
        if health_file.exists():
            health_file.unlink()
        return True
    except Exception as e:
        logger.error(f"Failed to clear health status: {e}")
        return False


class HealthReporter:
    """Background health reporter that periodically updates health status."""

    def __init__(
        self,
        component: str,
        status_fn: Callable[[], dict[str, Any]],
        interval: float = 10.0,
    ):
        """Initialize health reporter.

        Args:
            component: Component name
            status_fn: Function that returns health status dict
                       Should return a dict with at least 'healthy' key
            interval: Update interval in seconds
        """
        self.component = component
        self.status_fn = status_fn
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the health reporter background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._report_loop,
            daemon=True,
            name=f"{self.component}-health-reporter",
        )
        self._thread.start()
        logger.info(f"Started health reporter for {self.component}")

    def stop(self) -> None:
        """Stop the health reporter."""
        if not self._running:
            return

        self._running = False
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
            self._thread = None

        # Clear health status on shutdown
        clear_health_status(self.component)
        logger.info(f"Stopped health reporter for {self.component}")

    def _report_loop(self) -> None:
        """Background loop that reports health status."""
        while self._running:
            try:
                status_dict = self.status_fn()
                status = HealthStatus(
                    healthy=status_dict.get("healthy", False),
                    component=self.component,
                    details=status_dict,
                )
                write_health_status(status)
            except Exception as e:
                logger.error(f"Health report error: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(int(self.interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def report_now(self) -> None:
        """Report health status immediately."""
        try:
            status_dict = self.status_fn()
            status = HealthStatus(
                healthy=status_dict.get("healthy", False),
                component=self.component,
                details=status_dict,
            )
            write_health_status(status)
        except Exception as e:
            logger.error(f"Health report error: {e}")
