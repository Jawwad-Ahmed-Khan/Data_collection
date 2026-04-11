"""
Unit tests for BreachService — threshold lookup and breach detection logic.

Tests cover:
  - Priority-based threshold lookup (district > province > national)
  - Season-aware threshold selection
  - Breach level determination (watch/warning/emergency/extreme)
  - Duplicate suppression logic
  - Metric categorization
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.breach_service import BreachService
from app.models.reference_models import DisasterThreshold
from app.repositories.breach_repository import BreachRepository

# Pakistan Standard Time
PKT = ZoneInfo("Asia/Karachi")


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_thresholds() -> list[DisasterThreshold]:
    """Create sample thresholds for testing priority lookup."""
    return [
        # National default heatwave (year-round)
        DisasterThreshold(
            threshold_id=uuid4(),
            disaster_kind="heatwave",
            metric_name="temp_max_c",
            province=None,
            district=None,
            unit="celsius",
            breach_direction="above",
            watch_threshold=40.0,
            warning_threshold=44.0,
            emergency_threshold=47.0,
            extreme_threshold=50.0,
            applies_season=None,
            description="National default heatwave threshold",
            is_active=True,
        ),
        # Sindh province heatwave (year-round) — higher thresholds
        DisasterThreshold(
            threshold_id=uuid4(),
            disaster_kind="heatwave",
            metric_name="temp_max_c",
            province="sindh",
            district=None,
            unit="celsius",
            breach_direction="above",
            watch_threshold=42.0,
            warning_threshold=46.0,
            emergency_threshold=49.0,
            extreme_threshold=52.0,
            applies_season=None,
            description="Sindh province heatwave threshold",
            is_active=True,
        ),
        # Karachi district heatwave (summer only) — even higher
        DisasterThreshold(
            threshold_id=uuid4(),
            disaster_kind="heatwave",
            metric_name="temp_max_c",
            province="sindh",
            district="Karachi",
            unit="celsius",
            breach_direction="above",
            watch_threshold=43.0,
            warning_threshold=47.0,
            emergency_threshold=50.0,
            extreme_threshold=53.0,
            applies_season="summer",
            description="Karachi summer heatwave threshold",
            is_active=True,
        ),
        # Earthquake national threshold
        DisasterThreshold(
            threshold_id=uuid4(),
            disaster_kind="earthquake",
            metric_name="magnitude",
            province=None,
            district=None,
            unit="richter",
            breach_direction="above",
            watch_threshold=4.0,
            warning_threshold=5.0,
            emergency_threshold=6.0,
            extreme_threshold=7.0,
            applies_season=None,
            description="National earthquake threshold",
            is_active=True,
        ),
        # Heavy rain monsoon threshold (national)
        DisasterThreshold(
            threshold_id=uuid4(),
            disaster_kind="heavy_rain",
            metric_name="precip_24h_mm",
            province=None,
            district=None,
            unit="mm",
            breach_direction="above",
            watch_threshold=50.0,
            warning_threshold=100.0,
            emergency_threshold=150.0,
            extreme_threshold=200.0,
            applies_season="monsoon",
            description="Monsoon heavy rain threshold",
            is_active=True,
        ),
    ]


@pytest.fixture
def mock_breach_repo(mocker):
    """Mock BreachRepository for testing."""
    repo = mocker.Mock(spec=BreachRepository)
    repo.find_recent_breach = mocker.AsyncMock(return_value=None)
    repo.insert_breach = mocker.AsyncMock(return_value=str(uuid4()))
    return repo


@pytest.fixture
def breach_service(sample_thresholds, mock_breach_repo) -> BreachService:
    """Create BreachService with sample thresholds."""
    return BreachService(
        thresholds=sample_thresholds,
        breach_repository=mock_breach_repo,
    )


# ── Test: Season Detection ────────────────────────────────────────


def test_season_detection_monsoon(breach_service, mocker):
    """Test season detection during monsoon (July-September)."""
    # Mock current time to August 15
    mock_now = datetime(2025, 8, 15, 12, 0, 0, tzinfo=PKT)
    mocker.patch("app.services.breach_service.datetime")
    breach_service._get_current_season = lambda: "monsoon"
    
    season = breach_service._get_current_season()
    assert season == "monsoon"


def test_season_detection_summer(breach_service, mocker):
    """Test season detection during summer (March-June)."""
    mock_now = datetime(2025, 5, 20, 12, 0, 0, tzinfo=PKT)
    mocker.patch("app.services.breach_service.datetime")
    breach_service._get_current_season = lambda: "summer"
    
    season = breach_service._get_current_season()
    assert season == "summer"


# ── Test: Threshold Priority Lookup ───────────────────────────────


def test_threshold_lookup_national_default(breach_service):
    """Test that national default is selected when no specific match."""
    threshold = breach_service.find_applicable_threshold(
        metric_name="temp_max_c",
        disaster_kind="heatwave",
        province="punjab",  # No Punjab-specific threshold exists
        district="Lahore",
    )
    
    assert threshold is not None
    assert threshold.province is None  # National default
    assert threshold.district is None
    assert threshold.watch_threshold == 40.0


def test_threshold_lookup_province_specific(breach_service):
    """Test that province-specific threshold overrides national."""
    threshold = breach_service.find_applicable_threshold(
        metric_name="temp_max_c",
        disaster_kind="heatwave",
        province="sindh",
        district="Hyderabad",  # No Hyderabad-specific, but Sindh exists
    )
    
    assert threshold is not None
    assert threshold.province == "sindh"
    assert threshold.district is None
    assert threshold.watch_threshold == 42.0  # Sindh threshold


def test_threshold_lookup_district_specific(breach_service, mocker):
    """Test that district-specific threshold has highest priority."""
    # Mock season to be summer
    mocker.patch.object(breach_service, "_get_current_season", return_value="summer")
    
    threshold = breach_service.find_applicable_threshold(
        metric_name="temp_max_c",
        disaster_kind="heatwave",
        province="sindh",
        district="Karachi",
    )
    
    assert threshold is not None
    assert threshold.district == "Karachi"
    assert threshold.applies_season == "summer"
    assert threshold.watch_threshold == 43.0  # Karachi summer threshold


def test_threshold_lookup_season_mismatch(breach_service, mocker):
    """Test that season-specific threshold is skipped if season doesn't match."""
    # Mock season to be winter (not summer)
    mocker.patch.object(breach_service, "_get_current_season", return_value="winter")
    
    threshold = breach_service.find_applicable_threshold(
        metric_name="temp_max_c",
        disaster_kind="heatwave",
        province="sindh",
        district="Karachi",
    )
    
    # Should fall back to Sindh year-round threshold (not Karachi summer)
    assert threshold is not None
    assert threshold.province == "sindh"
    assert threshold.district is None  # Not Karachi
    assert threshold.applies_season is None  # Year-round
    assert threshold.watch_threshold == 42.0


def test_threshold_lookup_no_match(breach_service):
    """Test that None is returned when no threshold matches."""
    threshold = breach_service.find_applicable_threshold(
        metric_name="nonexistent_metric",
        disaster_kind="heatwave",
        province="punjab",
        district="Lahore",
    )
    
    assert threshold is None


# ── Test: Breach Level Detection ──────────────────────────────────


def test_breach_detection_no_breach(breach_service, sample_thresholds):
    """Test that no breach is detected when value is below watch threshold."""
    threshold = sample_thresholds[0]  # National heatwave
    
    severity = breach_service.check_breach(value=38.0, threshold=threshold)
    
    assert severity is None


def test_breach_detection_watch_level(breach_service, sample_thresholds):
    """Test watch level breach detection."""
    threshold = sample_thresholds[0]  # National heatwave
    
    severity = breach_service.check_breach(value=41.0, threshold=threshold)
    
    assert severity == "watch"


def test_breach_detection_warning_level(breach_service, sample_thresholds):
    """Test warning level breach detection."""
    threshold = sample_thresholds[0]  # National heatwave
    
    severity = breach_service.check_breach(value=45.0, threshold=threshold)
    
    assert severity == "warning"


def test_breach_detection_emergency_level(breach_service, sample_thresholds):
    """Test emergency level breach detection."""
    threshold = sample_thresholds[0]  # National heatwave
    
    severity = breach_service.check_breach(value=48.0, threshold=threshold)
    
    assert severity == "emergency"


def test_breach_detection_extreme_level(breach_service, sample_thresholds):
    """Test extreme level breach detection."""
    threshold = sample_thresholds[0]  # National heatwave
    
    severity = breach_service.check_breach(value=51.0, threshold=threshold)
    
    assert severity == "extreme"


def test_breach_detection_below_direction(breach_service):
    """Test breach detection with 'below' direction (cold wave)."""
    # Create a cold wave threshold
    cold_threshold = DisasterThreshold(
        threshold_id=uuid4(),
        disaster_kind="cold_wave",
        metric_name="temp_min_c",
        province=None,
        district=None,
        unit="celsius",
        breach_direction="below",
        watch_threshold=-5.0,
        warning_threshold=-10.0,
        emergency_threshold=-15.0,
        extreme_threshold=-20.0,
        applies_season=None,
        description="Cold wave threshold",
        is_active=True,
    )
    
    # Value below warning threshold should trigger warning
    severity = breach_service.check_breach(value=-12.0, threshold=cold_threshold)
    assert severity == "warning"
    
    # Value above watch threshold should not trigger
    severity = breach_service.check_breach(value=-3.0, threshold=cold_threshold)
    assert severity is None


# ── Test: Metric Categorization ───────────────────────────────────


def test_metric_categorization_earthquake(breach_service):
    """Test earthquake metric categorization."""
    category = breach_service._categorize_metric("magnitude")
    assert category == "earthquake"


def test_metric_categorization_temperature(breach_service):
    """Test temperature metric categorization."""
    assert breach_service._categorize_metric("temp_max_c") == "temperature"
    assert breach_service._categorize_metric("temp_min_c") == "temperature"
    assert breach_service._categorize_metric("feels_like_max_c") == "temperature"


def test_metric_categorization_rainfall(breach_service):
    """Test rainfall metric categorization."""
    assert breach_service._categorize_metric("precip_24h_mm") == "rainfall"
    assert breach_service._categorize_metric("precip_72h_mm") == "rainfall"
    assert breach_service._categorize_metric("rain_mm") == "rainfall"


def test_metric_categorization_wind(breach_service):
    """Test wind metric categorization."""
    assert breach_service._categorize_metric("wind_speed_kmh") == "wind"
    assert breach_service._categorize_metric("wind_gusts_kmh") == "wind"


def test_metric_categorization_flood_gauge(breach_service):
    """Test flood gauge metric categorization."""
    assert breach_service._categorize_metric("gauge_level_m") == "flood_gauge"
    assert breach_service._categorize_metric("pct_of_danger") == "flood_gauge"


# ── Test: Duplicate Suppression ───────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_suppression_earthquake_never_suppressed(breach_service, mock_breach_repo):
    """Test that earthquake breaches are never suppressed (each event is unique)."""
    location_id = uuid4()
    
    duplicate_id = await breach_service.check_duplicate(
        location_id=location_id,
        metric_name="magnitude",
        metric_category="earthquake",
    )
    
    assert duplicate_id is None
    # Should not even query the database
    mock_breach_repo.find_recent_breach.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_suppression_temperature_found(breach_service, mock_breach_repo):
    """Test that duplicate temperature breach is detected."""
    location_id = uuid4()
    existing_breach_id = uuid4()
    
    # Mock that a recent breach exists
    mock_breach_repo.find_recent_breach.return_value = existing_breach_id
    
    duplicate_id = await breach_service.check_duplicate(
        location_id=location_id,
        metric_name="temp_max_c",
        metric_category="temperature",
    )
    
    assert duplicate_id == existing_breach_id
    mock_breach_repo.find_recent_breach.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_suppression_no_recent_breach(breach_service, mock_breach_repo):
    """Test that no duplicate is found when no recent breach exists."""
    location_id = uuid4()
    
    # Mock that no recent breach exists
    mock_breach_repo.find_recent_breach.return_value = None
    
    duplicate_id = await breach_service.check_duplicate(
        location_id=location_id,
        metric_name="temp_max_c",
        metric_category="temperature",
    )
    
    assert duplicate_id is None


# ── Test: Breach Creation ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_breach_success(breach_service, sample_thresholds, mock_breach_repo):
    """Test successful breach creation."""
    threshold = sample_thresholds[0]  # National heatwave
    location_id = uuid4()
    
    breach_id = await breach_service.create_breach(
        source_api="open_meteo",
        disaster_kind="heatwave",
        metric_name="temp_max_c",
        observed_value=48.0,
        threshold=threshold,
        severity="emergency",
        observation_time=datetime.now(PKT),
        location_name="Lahore",
        district="Lahore",
        province="punjab",
        latitude=31.5497,
        longitude=74.3436,
        weather_location_id=location_id,
    )
    
    assert breach_id is not None
    mock_breach_repo.insert_breach.assert_called_once()


@pytest.mark.asyncio
async def test_create_breach_suppressed_as_duplicate(breach_service, sample_thresholds, mock_breach_repo):
    """Test that duplicate breach is suppressed."""
    threshold = sample_thresholds[0]  # National heatwave
    location_id = uuid4()
    existing_breach_id = uuid4()
    
    # Mock that a recent breach exists
    mock_breach_repo.find_recent_breach.return_value = existing_breach_id
    
    breach_id = await breach_service.create_breach(
        source_api="open_meteo",
        disaster_kind="heatwave",
        metric_name="temp_max_c",
        observed_value=48.0,
        threshold=threshold,
        severity="emergency",
        observation_time=datetime.now(PKT),
        location_name="Lahore",
        district="Lahore",
        province="punjab",
        latitude=31.5497,
        longitude=74.3436,
        weather_location_id=location_id,
    )
    
    # Should return None because it's a duplicate
    assert breach_id is None
    
    # Should still insert the breach record (marked as duplicate)
    mock_breach_repo.insert_breach.assert_called_once()
    call_args = mock_breach_repo.insert_breach.call_args
    assert call_args.kwargs["is_duplicate"] is True
    assert call_args.kwargs["duplicate_of_breach_id"] == existing_breach_id


# ── Test: Integration ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_breach_detection_workflow(breach_service, sample_thresholds, mock_breach_repo):
    """Test complete workflow: threshold lookup → breach check → create breach."""
    # 1. Find applicable threshold
    threshold = breach_service.find_applicable_threshold(
        metric_name="temp_max_c",
        disaster_kind="heatwave",
        province="punjab",
        district="Lahore",
    )
    assert threshold is not None
    
    # 2. Check if value breaches threshold
    observed_value = 48.0
    severity = breach_service.check_breach(value=observed_value, threshold=threshold)
    assert severity == "emergency"
    
    # 3. Create breach record
    location_id = uuid4()
    breach_id = await breach_service.create_breach(
        source_api="open_meteo",
        disaster_kind="heatwave",
        metric_name="temp_max_c",
        observed_value=observed_value,
        threshold=threshold,
        severity=severity,
        observation_time=datetime.now(PKT),
        location_name="Lahore",
        district="Lahore",
        province="punjab",
        latitude=31.5497,
        longitude=74.3436,
        weather_location_id=location_id,
    )
    
    assert breach_id is not None
    mock_breach_repo.insert_breach.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
