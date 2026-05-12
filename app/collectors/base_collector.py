"""
ClimaSync Collection Service — Base Collector

Base class for all three collectors (USGS, Open-Meteo, Flood Hub).
Provides shared HTTP client, retry logic, rate limit handling, and backoff management.

Key features:
  - Tenacity retry with exponential backoff (3 attempts)
  - Rate limit detection and backoff enforcement
  - Cycle counter tracking (locations_targeted, locations_success, etc.)
  - Shared httpx.AsyncClient for connection pooling
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
    before_sleep_log,
)
import logging

from app.core.config import get_settings
from app.core.exceptions import ApiResponseError, ApiRateLimitError, ApiTimeoutError
from app.core.logger import get_logger
from app.models.reference_models import ApiRegistry
from app.repositories.reference_repository import ReferenceRepository

logger = get_logger(__name__)
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class BaseCollector:
    """Base class for all API collectors.
    
    Provides:
      - HTTP client with retry logic
      - Rate limit detection and backoff enforcement
      - Cycle counter tracking
      - Shared error handling
    
    All three collectors (USGS, Open-Meteo, Flood Hub) inherit from this.
    """

    def __init__(
        self,
        api_name: str,
        http_client: httpx.AsyncClient,
        reference_repo: ReferenceRepository,
    ) -> None:
        """Initialize base collector.
        
        Args:
            api_name: Name of the API (e.g., 'usgs', 'open_meteo', 'google_flood_hub').
            http_client: Shared async HTTP client for connection pooling.
            reference_repo: Repository for reading API config and updating backoff.
        """
        self.api_name = api_name
        self.http_client = http_client
        self.reference_repo = reference_repo
        
        # Cycle counters (reset at start of each collection cycle)
        self.locations_targeted = 0
        self.locations_success = 0
        self.locations_failed = 0
        self.rate_limit_hits = 0
        
        # Cached API config (loaded once per cycle)
        self._api_config: ApiRegistry | None = None
        
        logger.info("BaseCollector initialized for API: %s", api_name)

    # ── API Configuration ─────────────────────────────────────────

    async def _load_api_config(self) -> ApiRegistry:
        """Load API configuration from database.
        
        Returns:
            ApiRegistry configuration object.
        
        Raises:
            ApiResponseError: If API config not found or inactive.
        """
        if self._api_config is None:
            self._api_config = await self.reference_repo.get_api_by_name(self.api_name)
            
            if self._api_config is None:
                raise ApiResponseError(
                    self.api_name,
                    404,
                    f"API '{self.api_name}' not found in api_registry"
                )
            
            if not self._api_config.is_active:
                raise ApiResponseError(
                    self.api_name,
                    403,
                    f"API '{self.api_name}' is marked inactive"
                )
            
            logger.debug(
                "Loaded API config: %s (max_rpm=%d, backoff_until=%s)",
                self.api_name,
                self._api_config.max_requests_per_minute,
                self._api_config.backoff_until,
            )
        
        return self._api_config

    # ── Backoff Management ────────────────────────────────────────

    async def _check_backoff(self) -> bool:
        """Check if API is currently in backoff period.
        
        Returns:
            True if in backoff (should skip this call), False otherwise.
        """
        api_config = await self._load_api_config()
        
        if api_config.backoff_until is None:
            return False
        
        now = datetime.now(_PKT)
        
        if now < api_config.backoff_until:
            remaining_seconds = (api_config.backoff_until - now).total_seconds()
            logger.warning(
                "API '%s' is in backoff period. Remaining: %.1f seconds",
                self.api_name,
                remaining_seconds,
            )
            return True
        
        # Backoff period expired — clear it
        logger.info("API '%s' backoff period expired, resuming calls", self.api_name)
        await self.reference_repo.update_api_backoff(self.api_name, None)  # type: ignore
        self._api_config = None  # Force reload on next call
        
        return False

    async def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Handle rate limit response (HTTP 429).
        
        Reads Retry-After header and sets backoff_until in database.
        
        Args:
            response: HTTP response with status 429.
        """
        self.rate_limit_hits += 1
        
        # Try to read Retry-After header (seconds or HTTP date)
        retry_after = response.headers.get("Retry-After")
        
        retry_seconds = 0
        if retry_after:
            try:
                # Try parsing as integer (seconds)
                retry_seconds = int(retry_after)
            except ValueError:
                # Try parsing as HTTP date (not common, but spec-compliant)
                try:
                    retry_date = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT")
                    retry_seconds = int((retry_date - datetime.utcnow()).total_seconds())
                except ValueError:
                    pass
                    
        # Compute exponential backoff based on consecutive failures
        api_config = await self.reference_repo.get_api_by_name(self.api_name)
        consec_failures = api_config.consecutive_failures if api_config else 0
        
        computed_backoff = min(
            settings.api_backoff_initial_s * (settings.api_backoff_multiplier ** consec_failures),
            settings.api_backoff_max_s
        )
        final_backoff = int(max(computed_backoff, retry_seconds))
        
        backoff_until = datetime.now(_PKT) + timedelta(seconds=final_backoff)
        
        logger.warning(
            "%s rate limited. Backoff %ds until %s",
            self.api_name,
            final_backoff,
            backoff_until.isoformat(),
        )
        
        # Update database
        await self.reference_repo.update_api_backoff(self.api_name, backoff_until)
        
        # Clear cached config to force reload
        self._api_config = None
        
        raise ApiRateLimitError(
            self.api_name,
            final_backoff,
        )

    # ── HTTP Request with Retry ───────────────────────────────────

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make HTTP GET request with retry logic and rate limit handling.
        
        Retry behavior:
          - 3 attempts with exponential backoff (1s min, 30s max)
          - Retry on: httpx.TimeoutException, httpx.ConnectError, HTTP 5xx
          - Do NOT retry on: HTTP 429 (rate limit) — go straight to backoff
        
        Args:
            url: Full URL to request.
            params: Query parameters.
            headers: HTTP headers.
        
        Returns:
            HTTP response object.
        
        Raises:
            ApiRateLimitError: If HTTP 429 received.
            ApiResponseError: If request fails after all retries.
        """
        # Check if in backoff period
        if await self._check_backoff():
            raise ApiRateLimitError(self.api_name, None)
        
        # Load API config for timeout
        api_config = await self._load_api_config()
        timeout = httpx.Timeout(30.0, connect=10.0)  # 10s connect, 30s read/overall timeout
        
        # Define retry logic
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.HTTPStatusError,  # Retry on 5xx errors
            )),
            reraise=True,
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        async def _make_request() -> httpx.Response:
            """Inner function with retry decorator."""
            try:
                response = await self.http_client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                
                # Check for rate limit (HTTP 429)
                if response.status_code == 429:
                    await self._handle_rate_limit(response)
                    # _handle_rate_limit raises ApiRateLimitError, so this line won't execute
                
                # Check for server errors (5xx) — these should be retried
                if 500 <= response.status_code < 600:
                    logger.warning(
                        "Server error %d from %s, will retry",
                        response.status_code,
                        url,
                    )
                    raise httpx.HTTPStatusError(
                        f"Server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                
                # Raise for other HTTP errors (4xx except 429)
                response.raise_for_status()
                
                return response
                
            except httpx.HTTPStatusError as e:
                # Check if it's a 5xx error (retriable)
                if hasattr(e, 'response') and 500 <= e.response.status_code < 600:
                    # Re-raise to trigger retry
                    raise
                # Other HTTP errors (4xx) are not retriable
                logger.error(
                    "HTTP error %d from %s: %s",
                    e.response.status_code,
                    url,
                    e.response.text[:200],
                )
                raise ApiResponseError(
                    self.api_name,
                    e.response.status_code,
                    e.response.text[:200]
                )
        
        try:
            response = await _make_request()
            logger.debug("GET %s → %d (%d bytes)", url, response.status_code, len(response.content))
            return response
            
        except RetryError as e:
            # All retries exhausted
            logger.error("All retries exhausted for %s: %s", url, str(e))
            raise ApiResponseError(
                self.api_name,
                500,
                f"Request failed after 3 retries: {url}"
            )
        
        except ApiRateLimitError:
            # Rate limit error — already logged and backoff set
            raise
        
        except Exception as e:
            logger.error("Unexpected error during GET %s: %s", url, str(e))
            raise ApiResponseError(
                self.api_name,
                500,
                f"Unexpected error: {str(e)}"
            )

    # ── Rate Limit Delay ──────────────────────────────────────────

    async def rate_limit_delay(self, delay_ms: int) -> None:
        """Sleep for rate limit delay between API calls.
        
        Args:
            delay_ms: Delay in milliseconds.
        """
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)
            logger.debug("Rate limit delay: %d ms", delay_ms)

    # ── Cycle Counter Management ──────────────────────────────────

    def reset_counters(self) -> None:
        """Reset cycle counters at the start of a new collection cycle."""
        self.locations_targeted = 0
        self.locations_success = 0
        self.locations_failed = 0
        self.rate_limit_hits = 0
        logger.debug("Cycle counters reset for API: %s", self.api_name)

    def increment_success(self) -> None:
        """Increment success counter after successful location poll."""
        self.locations_success += 1

    def increment_failure(self) -> None:
        """Increment failure counter after failed location poll."""
        self.locations_failed += 1

    def get_cycle_stats(self) -> dict[str, int]:
        """Get current cycle statistics.
        
        Returns:
            Dictionary with cycle counters.
        """
        return {
            "locations_targeted": self.locations_targeted,
            "locations_success": self.locations_success,
            "locations_failed": self.locations_failed,
            "rate_limit_hits": self.rate_limit_hits,
        }
