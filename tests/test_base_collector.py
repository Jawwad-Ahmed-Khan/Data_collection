"""
Unit tests for BaseCollector — HTTP retry, rate limit handling, backoff management.

Tests cover:
  - Retry logic (3 attempts with exponential backoff)
  - Rate limit detection (HTTP 429) and backoff enforcement
  - Backoff period checking and expiration
  - Cycle counter tracking
  - Error handling for various HTTP status codes
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from unittest.mock import AsyncMock, Mock, patch

from app.collectors.base_collector import BaseCollector
from app.core.exceptions import ApiResponseError, ApiRateLimitError
from app.models.reference_models import ApiRegistry
from app.repositories.reference_repository import ReferenceRepository

# Pakistan Standard Time
PKT = ZoneInfo("Asia/Karachi")


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_http_client(mocker):
    """Mock httpx.AsyncClient."""
    client = mocker.Mock(spec=httpx.AsyncClient)
    client.get = mocker.AsyncMock()
    return client


@pytest.fixture
def mock_reference_repo(mocker):
    """Mock ReferenceRepository."""
    repo = mocker.Mock(spec=ReferenceRepository)
    repo.get_api_by_name = mocker.AsyncMock()
    repo.update_api_backoff = mocker.AsyncMock()
    return repo


@pytest.fixture
def sample_api_config() -> ApiRegistry:
    """Create sample API configuration."""
    return ApiRegistry(
        api_id=uuid4(),
        api_name="usgs",
        display_name="USGS Earthquake API",
        base_url="https://earthquake.usgs.gov/fdsnws/event/1/query",
        max_requests_per_minute=60,
        timeout_seconds=30.0,
        is_active=True,
        current_health="healthy",
        consecutive_failures=0,
        backoff_until=None,
    )


@pytest.fixture
def base_collector(mock_http_client, mock_reference_repo, sample_api_config):
    """Create BaseCollector instance with mocked dependencies."""
    mock_reference_repo.get_api_by_name.return_value = sample_api_config
    
    collector = BaseCollector(
        api_name="usgs",
        http_client=mock_http_client,
        reference_repo=mock_reference_repo,
    )
    
    return collector


# ── Test: API Configuration Loading ───────────────────────────────


@pytest.mark.asyncio
async def test_load_api_config_success(base_collector, mock_reference_repo, sample_api_config):
    """Test successful API config loading."""
    config = await base_collector._load_api_config()
    
    assert config.api_name == "usgs"
    assert config.is_active is True
    assert config.max_requests_per_minute == 60
    mock_reference_repo.get_api_by_name.assert_called_once_with("usgs")


@pytest.mark.asyncio
async def test_load_api_config_not_found(base_collector, mock_reference_repo):
    """Test error when API config not found."""
    mock_reference_repo.get_api_by_name.return_value = None
    base_collector._api_config = None  # Force reload
    
    with pytest.raises(ApiResponseError, match="not found in api_registry"):
        await base_collector._load_api_config()


@pytest.mark.asyncio
async def test_load_api_config_inactive(base_collector, mock_reference_repo, sample_api_config):
    """Test error when API is marked inactive."""
    sample_api_config.is_active = False
    base_collector._api_config = None  # Force reload
    
    with pytest.raises(ApiResponseError, match="is marked inactive"):
        await base_collector._load_api_config()


@pytest.mark.asyncio
async def test_load_api_config_cached(base_collector, mock_reference_repo):
    """Test that API config is cached after first load."""
    # First call
    await base_collector._load_api_config()
    # Second call
    await base_collector._load_api_config()
    
    # Should only call repository once
    assert mock_reference_repo.get_api_by_name.call_count == 1


# ── Test: Backoff Management ──────────────────────────────────────


@pytest.mark.asyncio
async def test_check_backoff_not_in_backoff(base_collector):
    """Test that check_backoff returns False when not in backoff."""
    is_in_backoff = await base_collector._check_backoff()
    
    assert is_in_backoff is False


@pytest.mark.asyncio
async def test_check_backoff_in_backoff_period(base_collector, sample_api_config):
    """Test that check_backoff returns True when in backoff period."""
    # Set backoff_until to 5 minutes in the future
    sample_api_config.backoff_until = datetime.now(PKT) + timedelta(minutes=5)
    base_collector._api_config = None  # Force reload
    
    is_in_backoff = await base_collector._check_backoff()
    
    assert is_in_backoff is True


@pytest.mark.asyncio
async def test_check_backoff_expired(base_collector, mock_reference_repo, sample_api_config):
    """Test that expired backoff is cleared."""
    # Set backoff_until to 5 minutes in the past
    sample_api_config.backoff_until = datetime.now(PKT) - timedelta(minutes=5)
    base_collector._api_config = None  # Force reload
    
    is_in_backoff = await base_collector._check_backoff()
    
    assert is_in_backoff is False
    # Should clear backoff in database
    mock_reference_repo.update_api_backoff.assert_called_once_with("usgs", None)


# ── Test: Rate Limit Handling ─────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_rate_limit_with_retry_after_header(base_collector, mock_reference_repo):
    """Test rate limit handling with Retry-After header (seconds)."""
    # Mock HTTP 429 response with Retry-After header
    response = Mock(spec=httpx.Response)
    response.status_code = 429
    response.headers = {"Retry-After": "120"}  # 2 minutes
    
    with pytest.raises(ApiRateLimitError):
        await base_collector._handle_rate_limit(response)
    
    # Should update backoff in database
    mock_reference_repo.update_api_backoff.assert_called_once()
    call_args = mock_reference_repo.update_api_backoff.call_args
    assert call_args[0][0] == "usgs"
    
    # Backoff should be ~120 seconds from now
    backoff_until = call_args[0][1]
    expected_backoff = datetime.now(PKT) + timedelta(seconds=120)
    assert abs((backoff_until - expected_backoff).total_seconds()) < 5
    
    # Should increment rate_limit_hits counter
    assert base_collector.rate_limit_hits == 1


@pytest.mark.asyncio
async def test_handle_rate_limit_without_retry_after_header(base_collector, mock_reference_repo):
    """Test rate limit handling without Retry-After header (uses default)."""
    response = Mock(spec=httpx.Response)
    response.status_code = 429
    response.headers = {}  # No Retry-After header
    
    with pytest.raises(ApiRateLimitError):
        await base_collector._handle_rate_limit(response)
    
    # Should use default backoff (10 seconds from settings)
    mock_reference_repo.update_api_backoff.assert_called_once()
    call_args = mock_reference_repo.update_api_backoff.call_args
    backoff_until = call_args[0][1]
    expected_backoff = datetime.now(PKT) + timedelta(seconds=10)
    assert abs((backoff_until - expected_backoff).total_seconds()) < 5


@pytest.mark.asyncio
async def test_handle_rate_limit_respects_max_backoff(base_collector, mock_reference_repo):
    """Test that rate limit backoff respects max_backoff_s setting."""
    response = Mock(spec=httpx.Response)
    response.status_code = 429
    response.headers = {"Retry-After": "9999"}  # Very long backoff
    
    with pytest.raises(ApiRateLimitError):
        await base_collector._handle_rate_limit(response)
    
    # Should cap at max_backoff_s (600 seconds from settings)
    call_args = mock_reference_repo.update_api_backoff.call_args
    backoff_until = call_args[0][1]
    expected_backoff = datetime.now(PKT) + timedelta(seconds=600)
    assert abs((backoff_until - expected_backoff).total_seconds()) < 5


# ── Test: HTTP GET with Retry ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_success(base_collector, mock_http_client):
    """Test successful HTTP GET request."""
    # Mock successful response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{"data": "test"}'
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    response = await base_collector.get("https://api.example.com/data")
    
    assert response.status_code == 200
    assert response.content == b'{"data": "test"}'
    mock_http_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_with_params_and_headers(base_collector, mock_http_client):
    """Test GET request with query params and headers."""
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{"data": "test"}'
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response
    
    params = {"lat": "31.5", "lon": "74.3"}
    headers = {"Authorization": "Bearer token123"}
    
    response = await base_collector.get(
        "https://api.example.com/data",
        params=params,
        headers=headers,
    )
    
    assert response.status_code == 200
    call_args = mock_http_client.get.call_args
    assert call_args.kwargs["params"] == params
    assert call_args.kwargs["headers"] == headers


@pytest.mark.asyncio
async def test_get_rate_limit_429(base_collector, mock_http_client, mock_reference_repo):
    """Test that HTTP 429 triggers rate limit handling."""
    # Mock 429 response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "60"}
    mock_http_client.get.return_value = mock_response
    
    with pytest.raises(ApiRateLimitError):
        await base_collector.get("https://api.example.com/data")
    
    # Should update backoff
    mock_reference_repo.update_api_backoff.assert_called_once()
    assert base_collector.rate_limit_hits == 1


@pytest.mark.asyncio
async def test_get_server_error_5xx_retries(base_collector, mock_http_client):
    """Test that 5xx errors trigger retry logic."""
    # Mock 503 response (server error)
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.request = Mock()
    mock_response.text = "Service Unavailable"
    mock_http_client.get.return_value = mock_response
    
    with pytest.raises(ApiResponseError):
        await base_collector.get("https://api.example.com/data")
    
    # Should retry 3 times
    assert mock_http_client.get.call_count == 3


@pytest.mark.asyncio
async def test_get_client_error_4xx_no_retry(base_collector, mock_http_client):
    """Test that 4xx errors (except 429) do not retry."""
    # Mock 404 response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.request = Mock()
    mock_response.text = "Not Found"
    
    def raise_http_error():
        raise httpx.HTTPStatusError(
            "Client error",
            request=mock_response.request,
            response=mock_response,
        )
    
    mock_response.raise_for_status = raise_http_error
    mock_http_client.get.return_value = mock_response
    
    with pytest.raises(ApiResponseError):
        await base_collector.get("https://api.example.com/data")
    
    # Should NOT retry (only 1 attempt)
    assert mock_http_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_timeout_retries(base_collector, mock_http_client):
    """Test that timeout errors trigger retry logic."""
    # Mock timeout exception
    mock_http_client.get.side_effect = httpx.TimeoutException("Request timeout")
    
    with pytest.raises(ApiResponseError):
        await base_collector.get("https://api.example.com/data")
    
    # Should retry 3 times
    assert mock_http_client.get.call_count == 3


@pytest.mark.asyncio
async def test_get_connect_error_retries(base_collector, mock_http_client):
    """Test that connection errors trigger retry logic."""
    # Mock connection error
    mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")
    
    with pytest.raises(ApiResponseError):
        await base_collector.get("https://api.example.com/data")
    
    # Should retry 3 times
    assert mock_http_client.get.call_count == 3


@pytest.mark.asyncio
async def test_get_skips_if_in_backoff(base_collector, sample_api_config):
    """Test that GET request is skipped if API is in backoff period."""
    # Set backoff_until to future
    sample_api_config.backoff_until = datetime.now(PKT) + timedelta(minutes=5)
    base_collector._api_config = None  # Force reload
    
    with pytest.raises(ApiRateLimitError):
        await base_collector.get("https://api.example.com/data")


# ── Test: Cycle Counter Management ───────────────────────────────


def test_reset_counters(base_collector):
    """Test that reset_counters clears all counters."""
    # Set some values
    base_collector.locations_targeted = 10
    base_collector.locations_success = 7
    base_collector.locations_failed = 3
    base_collector.rate_limit_hits = 2
    
    # Reset
    base_collector.reset_counters()
    
    assert base_collector.locations_targeted == 0
    assert base_collector.locations_success == 0
    assert base_collector.locations_failed == 0
    assert base_collector.rate_limit_hits == 0


def test_increment_success(base_collector):
    """Test success counter increment."""
    assert base_collector.locations_success == 0
    
    base_collector.increment_success()
    assert base_collector.locations_success == 1
    
    base_collector.increment_success()
    assert base_collector.locations_success == 2


def test_increment_failure(base_collector):
    """Test failure counter increment."""
    assert base_collector.locations_failed == 0
    
    base_collector.increment_failure()
    assert base_collector.locations_failed == 1
    
    base_collector.increment_failure()
    assert base_collector.locations_failed == 2


def test_get_cycle_stats(base_collector):
    """Test getting cycle statistics."""
    base_collector.locations_targeted = 10
    base_collector.locations_success = 7
    base_collector.locations_failed = 3
    base_collector.rate_limit_hits = 1
    
    stats = base_collector.get_cycle_stats()
    
    assert stats == {
        "locations_targeted": 10,
        "locations_success": 7,
        "locations_failed": 3,
        "rate_limit_hits": 1,
    }


# ── Test: Rate Limit Delay ────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_delay(base_collector):
    """Test rate limit delay sleeps for correct duration."""
    import time
    
    start = time.time()
    await base_collector.rate_limit_delay(100)  # 100ms
    elapsed = time.time() - start
    
    # Should sleep for ~0.1 seconds
    assert 0.09 < elapsed < 0.15


@pytest.mark.asyncio
async def test_rate_limit_delay_zero(base_collector):
    """Test that zero delay does not sleep."""
    import time
    
    start = time.time()
    await base_collector.rate_limit_delay(0)
    elapsed = time.time() - start
    
    # Should not sleep
    assert elapsed < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
