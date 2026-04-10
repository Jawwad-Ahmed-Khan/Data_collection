"""
Unit tests for USGSCollector — API query building, collection cycle, error handling.

Tests cover:
  - Query parameter building (bounding box, time window, magnitude)
  - Collection cycle execution
  - Cycle tracking (start, complete, counters)
  - Error handling (API errors, parsing errors)
"""

import pytest
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, Mock

import httpx

from app.collectors.usgs_collector import USGSCollector
from app.models.reference_models import ApiRegistry
from app.repositories.cycle_repository import CycleRepository
from app.repositories.reference_repository import ReferenceRepository
from app.services.usgs_service import USGSService
from app.core.exceptions import ApiResponseError

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
def mock_cycle_repo(mocker):
    """Mock CycleRepository."""
    repo = mocker.Mock(spec=CycleRepository)
    repo.start_cycle = mocker.AsyncMock(return_value=str(uuid4()))
    repo.complete_cycle = mocker.AsyncMock()
    return repo


@pytest.fixture
def mock_usgs_service(mocker):
    """Mock USGSService."""
    service = mocker.Mock(spec=USGSService)
    service.parse_usgs_response = mocker.Mock(return_value=[])
    service.process_events = mocker.AsyncMock(return_value={
        "events_processed": 0,
        "events_upserted": 0,
        "breaches_detected": 0,
        "errors": 0,
    })
    return service


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
def usgs_collector(
    mock_http_client,
    mock_reference_repo,
    mock_cycle_repo,
    mock_usgs_service,
    sample_api_config,
):
    """Create USGSCollector instance with mocked dependencies."""
    mock_reference_repo.get_api_by_name.return_value = sample_api_config
    
    collector = USGSCollector(
        http_client=mock_http_client,
        reference_repo=mock_reference_repo,
        cycle_repo=mock_cycle_repo,
        usgs_service=mock_usgs_service,
    )
    
    return collector


@pytest.fixture
def sample_usgs_response() -> dict:
    """Sample USGS API response."""
    return {
        "type": "FeatureCollection",
        "metadata": {
            "generated": 1704067200000,
            "url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
            "title": "USGS Earthquakes",
            "status": 200,
            "api": "1.10.3",
            "count": 3,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "mag": 4.5,
                    "place": "Pakistan",
                    "time": 1704067200000,
                    "magType": "mb",
                    "status": "reviewed",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [74.5, 31.7, 25.0],
                },
                "id": "us7000test1",
            },
        ],
    }


# ── Test: Query Building ──────────────────────────────────────────


def test_build_query_params(usgs_collector):
    """Test USGS query parameter building."""
    params = usgs_collector._build_query_params()
    
    # Check required parameters
    assert params["format"] == "geojson"
    assert params["minmagnitude"] == 2.5
    assert "starttime" in params
    assert "endtime" in params
    assert "minlatitude" in params
    assert "maxlatitude" in params
    assert "minlongitude" in params
    assert "maxlongitude" in params
    assert params["orderby"] == "time"
    
    # Check Pakistan bounding box
    assert params["minlatitude"] == 23.0
    assert params["maxlatitude"] == 38.0
    assert params["minlongitude"] == 60.0
    assert params["maxlongitude"] == 78.0


# ── Test: Collection Cycle ────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_success(
    usgs_collector,
    mock_http_client,
    mock_cycle_repo,
    mock_usgs_service,
    sample_usgs_response,
):
    """Test successful collection cycle."""
    # Mock HTTP response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_usgs_response
    mock_response.raise_for_status = Mock()
    mock_response.content = b'{}'
    mock_http_client.get.return_value = mock_response
    
    # Mock service processing
    mock_usgs_service.parse_usgs_response.return_value = []  # Parsed events
    mock_usgs_service.process_events.return_value = {
        "events_processed": 3,
        "events_upserted": 3,
        "breaches_detected": 1,
        "errors": 0,
    }
    
    # Execute collection
    result = await usgs_collector.collect()
    
    # Check result
    assert result["status"] == "completed"
    assert result["events_fetched"] == 3
    assert result["events_upserted"] == 3
    assert result["breaches_detected"] == 1
    assert result["error"] is None
    
    # Check cycle tracking
    mock_cycle_repo.start_cycle.assert_called_once()
    mock_cycle_repo.complete_cycle.assert_called_once()
    
    # Check HTTP request
    mock_http_client.get.assert_called_once()
    call_args = mock_http_client.get.call_args
    assert "params" in call_args.kwargs
    assert call_args.kwargs["params"]["format"] == "geojson"


@pytest.mark.asyncio
async def test_collect_no_events(
    usgs_collector,
    mock_http_client,
    mock_cycle_repo,
    mock_usgs_service,
):
    """Test collection cycle with no events returned."""
    # Mock empty response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "type": "FeatureCollection",
        "metadata": {"count": 0},
        "features": [],
    }
    mock_response.raise_for_status = Mock()
    mock_response.content = b'{}'
    mock_http_client.get.return_value = mock_response
    
    # Mock service processing
    mock_usgs_service.parse_usgs_response.return_value = []
    mock_usgs_service.process_events.return_value = {
        "events_processed": 0,
        "events_upserted": 0,
        "breaches_detected": 0,
        "errors": 0,
    }
    
    # Execute collection
    result = await usgs_collector.collect()
    
    # Check result
    assert result["status"] == "completed"
    assert result["events_fetched"] == 0
    assert result["events_upserted"] == 0
    assert result["breaches_detected"] == 0


@pytest.mark.asyncio
async def test_collect_partial_errors(
    usgs_collector,
    mock_http_client,
    mock_cycle_repo,
    mock_usgs_service,
    sample_usgs_response,
):
    """Test collection cycle with partial processing errors."""
    # Mock HTTP response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_usgs_response
    mock_response.raise_for_status = Mock()
    mock_response.content = b'{}'
    mock_http_client.get.return_value = mock_response
    
    # Mock service processing with errors
    mock_usgs_service.parse_usgs_response.return_value = []
    mock_usgs_service.process_events.return_value = {
        "events_processed": 2,
        "events_upserted": 2,
        "breaches_detected": 0,
        "errors": 1,  # One event failed
    }
    
    # Execute collection
    result = await usgs_collector.collect()
    
    # Check result
    assert result["status"] == "partial"
    assert result["events_fetched"] == 3
    assert result["events_upserted"] == 2


@pytest.mark.asyncio
async def test_collect_api_error(
    usgs_collector,
    mock_http_client,
    mock_cycle_repo,
):
    """Test collection cycle with API error."""
    # Mock API error
    mock_http_client.get.side_effect = ApiResponseError(
        "usgs",
        503,
        "Service Unavailable",
    )
    
    # Execute collection
    result = await usgs_collector.collect()
    
    # Check result
    assert result["status"] == "failed"
    assert result["events_fetched"] == 0
    assert result["events_upserted"] == 0
    assert result["error"] is not None
    
    # Cycle should still be completed
    mock_cycle_repo.complete_cycle.assert_called_once()
    call_args = mock_cycle_repo.complete_cycle.call_args
    assert call_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_collect_unexpected_error(
    usgs_collector,
    mock_http_client,
    mock_cycle_repo,
):
    """Test collection cycle with unexpected error."""
    # Mock unexpected error
    mock_http_client.get.side_effect = Exception("Unexpected error")
    
    # Execute collection
    result = await usgs_collector.collect()
    
    # Check result
    assert result["status"] == "failed"
    assert result["error"] is not None
    
    # Cycle should still be completed
    mock_cycle_repo.complete_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_collect_cycle_counters(
    usgs_collector,
    mock_http_client,
    mock_cycle_repo,
    mock_usgs_service,
    sample_usgs_response,
):
    """Test that cycle counters are properly tracked."""
    # Mock HTTP response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_usgs_response
    mock_response.raise_for_status = Mock()
    mock_response.content = b'{}'
    mock_http_client.get.return_value = mock_response
    
    # Mock service processing
    mock_usgs_service.parse_usgs_response.return_value = []
    mock_usgs_service.process_events.return_value = {
        "events_processed": 3,
        "events_upserted": 3,
        "breaches_detected": 2,
        "errors": 0,
    }
    
    # Execute collection
    await usgs_collector.collect()
    
    # Check cycle completion call
    mock_cycle_repo.complete_cycle.assert_called_once()
    call_args = mock_cycle_repo.complete_cycle.call_args
    
    assert call_args.kwargs["locations_targeted"] == 3
    assert call_args.kwargs["locations_success"] == 3
    assert call_args.kwargs["locations_failed"] == 0
    assert call_args.kwargs["rows_upserted"] == 3
    assert call_args.kwargs["breaches_triggered"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
