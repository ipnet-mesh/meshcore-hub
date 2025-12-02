"""Logging configuration for MeshCore Hub."""

import logging
import sys
from typing import Optional

from meshcore_hub.common.config import LogLevel


# Default log format
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Structured log format (more suitable for production/parsing)
STRUCTURED_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)


def configure_logging(
    level: LogLevel | str = LogLevel.INFO,
    format_string: Optional[str] = None,
    structured: bool = False,
) -> None:
    """Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom log format string (optional)
        structured: Use structured logging format
    """
    # Convert LogLevel enum to string if necessary
    if isinstance(level, LogLevel):
        level_str = level.value
    else:
        level_str = level.upper()

    # Get numeric log level
    numeric_level = getattr(logging, level_str, logging.INFO)

    # Determine format
    if format_string:
        log_format = format_string
    elif structured:
        log_format = STRUCTURED_FORMAT
    else:
        log_format = DEFAULT_FORMAT

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Set levels for noisy third-party loggers
    logging.getLogger("paho").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Set our loggers to the configured level
    logging.getLogger("meshcore_hub").setLevel(numeric_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class ComponentLogger:
    """Logger wrapper for a specific component."""

    def __init__(self, component: str):
        """Initialize component logger.

        Args:
            component: Component name (e.g., 'interface', 'collector')
        """
        self.component = component
        self._logger = logging.getLogger(f"meshcore_hub.{component}")

    def debug(self, message: str, **kwargs: object) -> None:
        """Log a debug message."""
        self._logger.debug(message, extra=kwargs)

    def info(self, message: str, **kwargs: object) -> None:
        """Log an info message."""
        self._logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs: object) -> None:
        """Log a warning message."""
        self._logger.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs: object) -> None:
        """Log an error message."""
        self._logger.error(message, extra=kwargs)

    def critical(self, message: str, **kwargs: object) -> None:
        """Log a critical message."""
        self._logger.critical(message, extra=kwargs)

    def exception(self, message: str, **kwargs: object) -> None:
        """Log an exception with traceback."""
        self._logger.exception(message, extra=kwargs)


def get_component_logger(component: str) -> ComponentLogger:
    """Get a component-specific logger.

    Args:
        component: Component name

    Returns:
        ComponentLogger instance
    """
    return ComponentLogger(component)
