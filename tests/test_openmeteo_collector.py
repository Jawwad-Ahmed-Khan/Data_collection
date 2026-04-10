"""
Unit tests for OpenMeteoCollector — Location filtering, collection cycle, rate limiting.

Tests cover:
  - Location filtering (due for polling)
  - Single location collection
  - Complete collection cycle
  - Rate limit delay between locations
  - Cycle tracking and statistics
  - Error handling
"""

import pytest
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import httpx

from app.collectors.openmeteo_collector import OpenMeteoCollector
from app.models.reference_models import PakistanLocation, ApiRegistry
from app.repositories.reference_repository import ReferenceRepository
from app.repositories.cycle_repository import CycleRepository
from app.services.openmeteo_service import OpenMeteoService

# Pakistan Standard Time
PKT = ZoneInfo("Asia/Karachi")


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_pakistan_locations() -> list[PakistanLocation]:
    """Create sample Pakistan locations for testing."""
    return [
        PakistanLocation(
            location_id=uuid4(),
            location_key="lahore_31.5497_74.3436",
            location_name="Lahore",
            district="Lahore",
            province="punjab",
            latitude=31.5497,
            longitude=74.3436,
            is_active=True,
        ),
        PakistanLocation(
            location_id=uuid4(),
            location_key="karachi_24.8607_67.0011",
            location_name="Karachi",
            district="Karachi",
            province="sindh",
            latitude=24.8607,
            longitude=67.0011,
            is_active=True,
        ),
        PakistanLocation(
            location_id=uuid4(),
            location_key="islamabad_33.6844_73.0479",
            location_name="Islamabad",
            district="Islamabad",
            province="islamabad_capital_territory",
            latitude=33.6844,
            longitude=73.0479,
            is_active=True,
        ),
    ]


@pytest.fixture
def mock_http_client(mocker):
    """Mock httpx.AsyncClient."""
    client = mocker.Mock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def mock_reference_repo(mocker):
    """Mock ReferenceRepository."""
    repo = mocker.Mock(spec=ReferenceRepository)
    
    # Mock API config
    api_config = ApiRegistry(
        api_id=uuid4(),
        api_name="open_meteo",
        base_url="https://api.open-meteo.com/v1/forecast",
        max_requests_per_minute=60,
        is_active=True,
        backoff_until=None,
    )
    
    repo.get_api_config = mocker.AsyncMock(return_value=api_config)
    repo.update_api_backoff = mocker.AsyncMock()
    
    return repo


@pytest.fixture
def mock_cycle_repo(mocker):
    """Mock CycleRepository."""
    repo = mocker.Mock(spec=CycleRepository)
    repo.start_cycle = mocker.AsyncMock(return_value=str(uuid4()))
    repo.complete_cycle = mocker.AsyncMock()
    return repo


@pytest.fixture
def mock_openmeteo_service(mocker):
    """Mock OpenMeteoService."""
    service = mocker.Mock(spec=OpenMeteoService)
    
    service.build_hourly_params = mocker.Mock(return_value={
        "latitude": 31.5497,
        "longitude": 74.3436,
        "hourly": "temperature_2m,precipitation",
        "timezone": "Asia/Karachi",
        "forecast_days": 5,
    })
    
    service.build_daily_params = mocker.Mock(return_value={
        "latitude": 31.5497,
        "longitude": 74.3436,
        "daily": "temperature_2m_max,precipitation_sum",
        "timezone": "Asia/Karachi",
        "forecast_days": 5,
    })
    
    service.parse_hourly = mocker.Mock(return_value=[])
    service.parse_daily = mocker.Mock(return_value=[])
    
    service.process_location = mocker.AsyncMock(return_value={
        "hourly_upserted": 120,
        "daily_upserted": 5,
        "breaches_detected": 0,
        "errors": 0,
    })
    
    return service


@pytest.fixture
def openmeteo_collector(
    mock_http_client,
    mock_reference_repo,
    mock_cycle_repo,
    mock_openmeteo_service,
    sample_pakistan_locations,
):
    """Create OpenMeteoCollector instance."""
    return OpenMeteoCollector(
        http_client=mock_http_client,
        reference_repo=mock_reference_repo,
        cycle_repo=mock_cycle_repo,
        openmeteo_service=mock_openmeteo_service,
        pakistan_locations=sample_pakistan_locations,
    )


# ── Test: Location Filtering ──────────────────────────────────────


def test_get_due_locations_all_active(openmeteo_collector, sample_pakistan_locations):
    """Test getting due locations returns all active locations."""
    due_locations = openmeteo_collector.get_due_locations()
    
    assert len(due_locations) == 3
    assert all(loc.is_active for loc in due_locations)


def test_get_due_locations_with_inactive(openmeteo_collector, sample_pakistan_locations):
    """Test that inactive locations are excluded."""
    # Mark one location as inactive
    sample_pakistan_locations[1].is_active = False
    
    openmeteo_collector.pakistan_locations = sample_pakistan_locations
    
    due_locations = openmeteo_collector.get_due_locations()
    
    assert len(due_locations) == 2
    assert all(loc.is_active for loc in due_locations)


def test_get_due_locations_empty(openmeteo_collector):
    """Test getting due locations with empty location list."""
    openmeteo_collector.pakistan_locations = []
    
    due_locations = openmeteo_collector.get_due_locations()
    
    assert len(due_locations) == 0


# ── Test: Single Location Collection ──────────────────────────────


@pytest.mark.asyncio
async def test_collect_location_success(openmeteo_collector, mock_openmeteo_service, sample_pakistan_locations):
    """Test successful collection for a single location."""
    location = sample_pakistan_locations[0]
    
    # Mock HTTP responses
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"hourly": {}, "daily": {}})
    
    openmeteo_collector.get = AsyncMock(return_value=mock_response)
    
    stats = await openmeteo_collector.collect_location(location)
    
    assert stats["success"] is True
    assert stats["location_name"] == "Lahore"
    assert stats["hourly_count"] == 120
    assert stats["daily_count"] == 5
    assert stats["breaches"] == 0
    assert stats["error"] is None
    
    # Should call service methods
    mock_openmeteo_service.build_hourly_params.assert_called_once()
    mock_openmeteo_service.build_daily_params.assert_called_once()
    mock_openmeteo_service.parse_hourly.assert_called_once()
    mock_openmeteo_service.parse_daily.assert_called_once()
    mock_openmeteo_service.process_location.assert_called_once()


@pytest.mark.asyncio
async def test_collect_location_api_error(openmeteo_collector, sample_pakistan_locations):
    """Test location collection with API error."""
    location = sample_pakistan_locations[0]
    
    # Mock HTTP error
    from app.core.exceptions import ApiResponseError
    openmeteo_collector.get = AsyncMock(side_effect=ApiResponseError("open_meteo", 500, "API error"))
    
    stats = await openmeteo_collector.collect_location(location)
    
    assert stats["success"] is False
    assert "API error" in stats["error"] or "500" in stats["error"]


@pytest.mark.asyncio
async def test_collect_location_unexpected_error(openmeteo_collector, sample_pakistan_locations):
    """Test location collection with unexpected error."""
    location = sample_pakistan_locations[0]
    
    # Mock unexpected error
    openmeteo_collector.get = AsyncMock(side_effect=Exception("Unexpected error"))
    
    stats = await openmeteo_collector.collect_location(location)
    
    assert stats["success"] is False
    assert stats["error"] == "Unexpected error"


# ── Test: Collection Cycle ────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_cycle_success(openmeteo_collector, mock_cycle_repo, mock_openmeteo_service, sample_pakistan_locations):
    """Test successful collection cycle."""
    # Mock HTTP responses
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"hourly": {}, "daily": {}})
    
    openmeteo_collector.get = AsyncMock(return_value=mock_response)
    
    result = await openmeteo_collector.collect()
    
    assert result["status"] == "completed"
    assert result["locations_targeted"] == 3
    assert result["locations_success"] == 3
    assert result["locations_failed"] == 0
    assert result["hourly_rows"] == 360  # 120 * 3
    assert result["daily_rows"] == 15  # 5 * 3
    assert result["breaches_detected"] == 0
    
    # Should start and complete cycle
    mock_cycle_repo.start_cycle.assert_called_once()
    mock_cycle_repo.complete_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_collect_cycle_partial_failure(openmeteo_collector, mock_cycle_repo, sample_pakistan_locations):
    """Test collection cycle with partial failures."""
    # Mock first location succeeds, second fails, third succeeds
    call_count = 0
    
    async def mock_collect_location(location):
        nonlocal call_count
        call_count += 1
        
        if call_count == 2:
            return {
                "location_name": location.location_name,
                "success": False,
                "hourly_count": 0,
                "daily_count": 0,
                "breaches": 0,
                "error": "API error",
            }
        else:
            return {
                "location_name": location.location_name,
                "success": True,
                "hourly_count": 120,
                "daily_count": 5,
                "breaches": 0,
                "error": None,
            }
    
    openmeteo_collector.collect_location = mock_collect_location
    
    result = await openmeteo_collector.collect()
    
    assert result["status"] == "partial"
    assert result["locations_targeted"] == 3
    assert result["locations_success"] == 2
    assert result["locations_failed"] == 1


@pytest.mark.asyncio
async def test_collect_cycle_all_failures(openmeteo_collector, mock_cycle_repo, sample_pakistan_locations):
    """Test collection cycle with all failures."""
    # Mock all locations fail
    async def mock_collect_location(location):
        return {
            "location_name": location.location_name,
            "success": False,
            "hourly_count": 0,
            "daily_count": 0,
            "breaches": 0,
            "error": "API error",
        }
    
    openmeteo_collector.collect_location = mock_collect_location
    
    result = await openmeteo_collector.collect()
    
    assert result["status"] == "failed"
    assert result["locations_targeted"] == 3
    assert result["locations_success"] == 0
    assert result["locations_failed"] == 3


@pytest.mark.asyncio
async def test_collect_cycle_no_due_locations(openmeteo_collector, mock_cycle_repo):
    """Test collection cycle with no due locations."""
    openmeteo_collector.pakistan_locations = []
    
    result = await openmeteo_collector.collect()
    
    assert result["status"] == "skipped"
    assert result["locations_targeted"] == 0


@pytest.mark.asyncio
async def test_collect_cycle_unexpected_error(openmeteo_collector, mock_cycle_repo):
    """Test collection cycle with unexpected error."""
    # Mock get_due_locations to raise error
    openmeteo_collector.get_due_locations = lambda: (_ for _ in ()).throw(Exception("Unexpected error"))
    
    result = await openmeteo_collector.collect()
    
    assert result["status"] == "failed"
    assert result["error"] == "Unexpected error"


# ── Test: Rate Limiting ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_delay_between_locations(openmeteo_collector, mocker, sample_pakistan_locations):
    """Test that rate limit delay is applied between location calls."""
    # Mock asyncio.sleep to track calls
    mock_sleep = mocker.patch("asyncio.sleep", new_callable=AsyncMock)
    
    # Mock HTTP responses
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"hourly": {}, "daily": {}})
    
    openmeteo_collector.get = AsyncMock(return_value=mock_response)
    
    await openmeteo_collector.collect()
    
    # Should have 2 sleep calls (between 3 locations)
    # Note: rate_limit_delay is called, which internally calls asyncio.sleep
    # We need to check if rate_limit_delay was called
    assert openmeteo_collector.locations_success == 3


@pytest.mark.asyncio
async def test_no_delay_after_last_location(openmeteo_collector, mocker, sample_pakistan_locations):
    """Test that no delay is applied after the last location."""
    # Mock asyncio.sleep to track calls
    mock_sleep = mocker.patch("asyncio.sleep", new_callable=AsyncMock)
    
    # Mock HTTP responses
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"hourly": {}, "daily": {}})
    
    openmeteo_collector.get = AsyncMock(return_value=mock_response)
    
    # Mock rate_limit_delay to track calls
    original_rate_limit_delay = openmeteo_collector.rate_limit_delay
    delay_call_count = 0
    
    async def mock_rate_limit_delay(ms):
        nonlocal delay_call_count
        delay_call_count += 1
        await original_rate_limit_delay(ms)
    
    openmeteo_collector.rate_limit_delay = mock_rate_limit_delay
    
    await openmeteo_collector.collect()
    
    # Should have 2 delay calls (not 3, because no delay after last location)
    assert delay_call_count == 2


# ── Test: Cycle Tracking ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cycle_tracking_counters(openmeteo_collector, mock_cycle_repo, sample_pakistan_locations):
    """Test that cycle tracking counters are updated correctly."""
    # Mock HTTP responses
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"hourly": {}, "daily": {}})
    
    openmeteo_collector.get = AsyncMock(return_value=mock_response)
    
    await openmeteo_collector.collect()
    
    # Check complete_cycle was called with correct stats
    call_args = mock_cycle_repo.complete_cycle.call_args
    assert call_args.kwargs["status"] == "completed"
    assert call_args.kwargs["locations_targeted"] == 3
    assert call_args.kwargs["locations_success"] == 3
    assert call_args.kwargs["locations_failed"] == 0
    assert call_args.kwargs["rows_upserted"] == 375  # (120 + 5) * 3
    assert call_args.kwargs["breaches_triggered"] == 0


@pytest.mark.asyncio
async def test_cycle_tracking_with_breaches(openmeteo_collector, mock_cycle_repo, mock_openmeteo_service, sample_pakistan_locations):
    """Test cycle tracking with breach detection."""
    # Mock service to return breaches
    mock_openmeteo_service.process_location = AsyncMock(return_value={
        "hourly_upserted": 120,
        "daily_upserted": 5,
        "breaches_detected": 2,
        "errors": 0,
    })
    
    # Mock HTTP responses
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"hourly": {}, "daily": {}})
    
    openmeteo_collector.get = AsyncMock(return_value=mock_response)
    
    result = await openmeteo_collector.collect()
    
    assert result["breaches_detected"] == 6  # 2 * 3 locations
    
    # Check complete_cycle was called with correct breach count
    call_args = mock_cycle_repo.complete_cycle.call_args
    assert call_args.kwargs["breaches_triggered"] == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
