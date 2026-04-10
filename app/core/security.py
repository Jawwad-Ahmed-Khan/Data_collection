"""
ClimaSync Collection Service — Security Utilities

Protects all HTTP endpoints exposed by the collection service.
The main ClimaSync system must prove its identity via X-API-Key
header when calling our health and status endpoints.
"""

from __future__ import annotations

import secrets

# Header name the client must send
_API_KEY_HEADER = "X-API-Key"


def validate_api_key(provided_key: str | None, expected_key: str) -> bool:
    """Check if the provided API key matches the expected key.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        provided_key: The key sent in the X-API-Key header (None if missing).
        expected_key: The correct key from configuration.

    Returns:
        True if keys match, False otherwise.
    """
    if provided_key is None:
        return False
    return secrets.compare_digest(provided_key, expected_key)


def generate_api_key(length: int = 48) -> str:
    """Generate a cryptographically secure random API key.

    Args:
        length: Number of random bytes to generate (default 48).

    Returns:
        A hex-encoded API key string suitable for storage in .env.
    """
    return secrets.token_hex(length)
