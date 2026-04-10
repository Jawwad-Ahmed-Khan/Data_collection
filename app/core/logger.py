"""
ClimaSync Collection Service — Logging Configuration

One centralized logging setup. Every module calls get_logger(__name__)
instead of configuring its own logger.

Every log line includes:
  timestamp (PKT / Asia/Karachi), level, module, function, message
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Pakistan Standard Time — used for every timestamp
_PKT = ZoneInfo("Asia/Karachi")


class PKTFormatter(logging.Formatter):
    """Logging formatter that renders timestamps in Asia/Karachi (PKT)."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=_PKT)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(sep=" ", timespec="milliseconds")


def setup_logger(
    name: str = "climasync_collection",
    level: str = "INFO",
    *,
    include_traceback: bool = True,
) -> logging.Logger:
    """Create and configure the root application logger.

    Args:
        name: Logger name (default: "climasync_collection").
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        include_traceback: Whether to include traceback in error/exception logs.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if called more than once
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(funcName)-25s | %(message)s"
    handler.setFormatter(PKTFormatter(fmt=fmt))

    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the climasync_collection namespace.

    Usage in any module:
        from app.core.logger import get_logger
        logger = get_logger(__name__)

    Note: setup_logger() should be called during app startup to attach
    handlers to the root logger. Without it, child loggers will propagate
    to the root logger which may have no handlers configured.
    """
    return logging.getLogger(f"climasync_collection.{name}")
