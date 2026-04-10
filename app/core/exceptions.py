"""
ClimaSync Collection Service — Custom Exception Classes

Every layer uses specific exception types so error handling
is precise and meaningful. No generic Exception catches.
"""

from __future__ import annotations


class CollectionServiceError(Exception):
    """Base exception for all ClimaSync Collection Service errors."""

    pass


# ── External API Errors ───────────────────────────────────────────


class ApiRateLimitError(CollectionServiceError):
    """Raised when an external API returns HTTP 429 (Too Many Requests).

    Attributes:
        api_name: Which API rate-limited us (usgs, open_meteo, google_flood_hub).
        retry_after: Seconds the API asked us to wait (None if not provided).
    """

    def __init__(self, api_name: str, retry_after: int | None = None) -> None:
        self.api_name = api_name
        self.retry_after = retry_after
        msg = f"{api_name} rate limited"
        if retry_after is not None:
            msg += f", retry after {retry_after}s"
        super().__init__(msg)


class ApiTimeoutError(CollectionServiceError):
    """Raised when an external API does not respond within the timeout window.

    Attributes:
        api_name: Which API timed out.
        timeout_seconds: The timeout that was exceeded.
    """

    def __init__(self, api_name: str, timeout_seconds: float) -> None:
        self.api_name = api_name
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{api_name} timed out after {timeout_seconds}s")


class ApiResponseError(CollectionServiceError):
    """Raised when an external API returns an unexpected HTTP status (not 2xx, not 429).

    Attributes:
        api_name: Which API returned the error.
        status_code: The HTTP status code received.
        response_text: The raw response body for debugging.
    """

    def __init__(self, api_name: str, status_code: int, response_text: str = "") -> None:
        self.api_name = api_name
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"{api_name} returned HTTP {status_code}: {response_text[:200]}")


# ── Database Errors ───────────────────────────────────────────────


class DatabaseError(CollectionServiceError):
    """Raised when a database operation fails.

    Wraps asyncpg errors so upper layers do not depend on asyncpg directly.
    """

    def __init__(self, message: str, query: str = "", original_error: Exception | None = None) -> None:
        self.query = query
        self.original_error = original_error
        super().__init__(message)


class DatabaseConnectionError(DatabaseError):
    """Raised when the database connection pool cannot be created or is lost."""

    pass


# ── Business Logic Errors ─────────────────────────────────────────


class BreachDetectionError(CollectionServiceError):
    """Raised when threshold breach detection encounters an unexpected condition.

    Examples: threshold not found for a metric, invalid comparison direction.
    """

    pass


class DispatchError(CollectionServiceError):
    """Raised when sending a breach alert to the main ClimaSync system fails.

    Attributes:
        breach_id: The UUID of the breach that failed to dispatch.
        attempt: Which attempt number this is (1-based).
    """

    def __init__(self, message: str, breach_id: str = "", attempt: int = 1) -> None:
        self.breach_id = breach_id
        self.attempt = attempt
        super().__init__(message)


class ConfigurationError(CollectionServiceError):
    """Raised when required configuration is missing or invalid.

    Used during startup to refuse to start if critical env vars are missing.
    """

    pass
