"""
ClimaSync Collection Service — Core Module

Things every other layer uses. Centralized so they are only defined once.
"""

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ApiRateLimitError,
    ApiTimeoutError,
    ApiResponseError,
    BreachDetectionError,
    CollectionServiceError,
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    DispatchError,
)
from app.core.logger import PKTFormatter, get_logger, setup_logger
from app.core.security import generate_api_key, validate_api_key

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Exceptions
    "ApiRateLimitError",
    "ApiTimeoutError",
    "ApiResponseError",
    "BreachDetectionError",
    "CollectionServiceError",
    "ConfigurationError",
    "DatabaseConnectionError",
    "DatabaseError",
    "DispatchError",
    # Logger
    "PKTFormatter",
    "get_logger",
    "setup_logger",
    # Security
    "generate_api_key",
    "validate_api_key",
]
