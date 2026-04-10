"""
Unit tests for USGSService — GeoJSON parsing, location resolution, breach detection.

Tests cover:
  - GeoJSON parsing and field extraction
  - Unix milliseconds to PKT datetime conversion
  - Magnitude and depth classification
  - Nearest location resolution using Haversine distance
  - Breach detection and creation
  - Event processing workflow
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.usgs_service import USGSService
from app.models.seismic_models import SeismicEventBase
from app.models.reference_models import PakistanLocation, DisasterThreshold
from app.repositories.seismic_repository import SeismicRepository
from app.services.breach_service import BreachService

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
def mock_seismic_repo(mocker):
    """Mock SeismicRepository."""
    repo = mocker.Mock(spec=SeismicRepository)
    repo.upsert_event = mocker.AsyncMock(return_value=str(uuid4()))
    return repo


@pytest.fixture
def mock_breach_service(mocker):
    """Mock BreachService."""
    service = mocker.Mock(spec=BreachService)
    service.find_applicable_threshold = mocker.Mock(return_value=None)
    service.check_breach = mocker.Mock(return_value=None)
    service.create_breach = mocker.AsyncMock(return_value=str(uuid4()))
    return service


@pytest.fixture
def usgs_service(mock_seismic_repo, mock_breach_service, sample_pakistan_locations):
    """Create USGSService instance."""
    return USGSService(
        seismic_repo=mock_seismic_repo,
        breach_service=mock_breach_service,
        pakistan_locations=sample_pakistan_locations,
    )


@pytest.fixture
def sample_usgs_geojson() -> dict:
    """Sample USGS GeoJSON response."""
    return {
        "type": "FeatureCollection",
        "metadata": {
            "generated": 1704067200000,
            "url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
            "title": "USGS Earthquakes",
            "status": 200,
            "api": "1.10.3",
            "count": 2,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "mag": 4.5,
                    "place": "15 km NE of Lahore, Pakistan",
                    "time": 1704067200000,  # 2024-01-01 00:00:00 UTC
                    "updated": 1704067200000,
                    "tz": None,
                    "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000test1",
                    "detail": "https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us7000test1",
                    "felt": 150,
                    "cdi": 5.2,
                    "mmi": 4.8,
                    "alert": "green",
                    "status": "reviewed",
                    "tsunami": 0,
                    "sig": 312,
                    "net": "us",
                    "code": "7000test1",
                    "ids": ",us7000test1,",
                    "sources": ",us,",
                    "types": ",origin,phase-data,",
                    "nst": None,
                    "dmin": 0.123,
                    "rms": 0.45,
                    "gap": 89,
                    "magType": "mb",
                    "type": "earthquake",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [74.5, 31.7, 25.0],  # [lon, lat, depth_km]
                },
                "id": "us7000test1",
            },
            {
                "type": "Feature",
                "properties": {
                    "mag": 3.2,
                    "place": "Pakistan",
                    "time": 1704070800000,  # 2024-01-01 01:00:00 UTC
                    "magType": "ml",
                    "status": "automatic",
                    "tsunami": 0,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [73.0, 33.7, 10.0],
                },
                "id": "us7000test2",
            },
        ],
    }


# ── Test: GeoJSON Parsing ─────────────────────────────────────────


def test_parse_usgs_response_success(usgs_service, sample_usgs_geojson):
    """Test successful parsing of USGS GeoJSON response."""
    events = usgs_service.parse_usgs_response(sample_usgs_geojson)
    
    assert len(events) == 2
    
    # Check first event
    event1 = events[0]
    assert event1.usgs_event_id == "us7000test1"
    assert event1.magnitude == 4.5
    assert event1.magnitude_type == "mb"
    assert event1.depth_km == 25.0
    assert event1.latitude == 31.7
    assert event1.longitude == 74.5
    assert event1.usgs_place == "15 km NE of Lahore, Pakistan"
    assert event1.felt_reports == 150
    assert event1.cdi == 5.2
    assert event1.mmi == 4.8
    assert event1.usgs_alert_level == "green"
    assert event1.data_quality == "reviewed"
    assert event1.tsunami_flag is False
    
    # Check second event
    event2 = events[1]
    assert event2.usgs_event_id == "us7000test2"
    assert event2.magnitude == 3.2
    assert event2.depth_km == 10.0


def test_parse_usgs_response_empty(usgs_service):
    """Test parsing empty USGS response."""
    geojson = {"type": "FeatureCollection", "features": []}
    
    events = usgs_service.parse_usgs_response(geojson)
    
    assert len(events) == 0


def test_parse_feature_missing_id(usgs_service):
    """Test that feature without ID is skipped."""
    feature = {
        "type": "Feature",
        "properties": {"mag": 4.0, "time": 1704067200000},
        "geometry": {"type": "Point", "coordinates": [74.0, 31.0, 10.0]},
        # Missing "id" field
    }
    
    event = usgs_service._parse_feature(feature)
    
    assert event is None


def test_parse_feature_missing_magnitude(usgs_service):
    """Test that feature without magnitude is skipped."""
    feature = {
        "type": "Feature",
        "properties": {"time": 1704067200000},  # Missing "mag"
        "geometry": {"type": "Point", "coordinates": [74.0, 31.0, 10.0]},
        "id": "us7000test",
    }
    
    event = usgs_service._parse_feature(feature)
    
    assert event is None


# ── Test: Time Conversion ─────────────────────────────────────────


def test_convert_usgs_time(usgs_service):
    """Test conversion of USGS unix milliseconds to PKT datetime."""
    # 2024-01-01 00:00:00 UTC = 1704067200000 ms
    unix_ms = 1704067200000
    
    dt_pkt = usgs_service._convert_usgs_time(unix_ms)
    
    # Should be in PKT timezone (UTC+5)
    assert dt_pkt.tzinfo == PKT
    # 2024-01-01 00:00:00 UTC = 2024-01-01 05:00:00 PKT
    assert dt_pkt.year == 2024
    assert dt_pkt.month == 1
    assert dt_pkt.day == 1
    assert dt_pkt.hour == 5  # UTC+5


# ── Test: Classification ──────────────────────────────────────────


def test_classify_magnitude(usgs_service):
    """Test magnitude classification."""
    assert usgs_service._classify_magnitude(1.5) == "micro"
    assert usgs_service._classify_magnitude(3.0) == "minor"
    assert usgs_service._classify_magnitude(4.5) == "light"
    assert usgs_service._classify_magnitude(5.5) == "moderate"
    assert usgs_service._classify_magnitude(6.5) == "strong"
    assert usgs_service._classify_magnitude(7.5) == "major"
    assert usgs_service._classify_magnitude(8.5) == "great"


def test_classify_depth(usgs_service):
    """Test depth classification."""
    assert usgs_service._classify_depth(50.0) == "shallow"
    assert usgs_service._classify_depth(150.0) == "intermediate"
    assert usgs_service._classify_depth(400.0) == "deep"


def test_map_status_to_quality(usgs_service):
    """Test USGS status to quality mapping."""
    assert usgs_service._map_status_to_quality("automatic") == "automatic"
    assert usgs_service._map_status_to_quality("reviewed") == "reviewed"
    assert usgs_service._map_status_to_quality("deleted") == "deleted"
    assert usgs_service._map_status_to_quality("AUTOMATIC") == "automatic"
    assert usgs_service._map_status_to_quality("unknown") == "automatic"


# ── Test: Location Resolution ─────────────────────────────────────


def test_find_nearest_location_lahore(usgs_service, sample_pakistan_locations):
    """Test finding nearest location to Lahore coordinates."""
    # Coordinates near Lahore
    latitude = 31.55
    longitude = 74.35
    
    nearest, distance = usgs_service._find_nearest_location(latitude, longitude)
    
    assert nearest is not None
    assert nearest.location_name == "Lahore"
    assert distance is not None
    assert distance < 5.0  # Should be very close


def test_find_nearest_location_karachi(usgs_service, sample_pakistan_locations):
    """Test finding nearest location to Karachi coordinates."""
    # Coordinates near Karachi
    latitude = 24.86
    longitude = 67.00
    
    nearest, distance = usgs_service._find_nearest_location(latitude, longitude)
    
    assert nearest is not None
    assert nearest.location_name == "Karachi"
    assert distance is not None
    assert distance < 5.0


def test_find_nearest_location_no_locations(usgs_service):
    """Test location resolution with empty location list."""
    usgs_service.pakistan_locations = []
    
    nearest, distance = usgs_service._find_nearest_location(31.5, 74.3)
    
    assert nearest is None
    assert distance is None


def test_haversine_distance(usgs_service):
    """Test Haversine distance calculation."""
    # Distance between Lahore and Karachi
    lahore_lat, lahore_lon = 31.5497, 74.3436
    karachi_lat, karachi_lon = 24.8607, 67.0011
    
    distance = usgs_service._haversine_distance(
        lahore_lat, lahore_lon,
        karachi_lat, karachi_lon,
    )
    
    # Actual distance is ~1034 km
    assert 1000 < distance < 1070


# ── Test: Breach Detection ────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_breach_no_threshold(usgs_service, mock_breach_service):
    """Test breach check when no threshold exists."""
    event = SeismicEventBase(
        usgs_event_id="test123",
        magnitude=4.5,
        magnitude_type="mb",
        magnitude_class="light",
        depth_km=25.0,
        depth_class="shallow",
        latitude=31.5,
        longitude=74.3,
        earthquake_time=datetime.now(PKT),
        has_breach=False,
        breach_severity=None,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = None
    
    has_breach, severity = await usgs_service.check_breach(event)
    
    assert has_breach is False
    assert severity is None


@pytest.mark.asyncio
async def test_check_breach_no_breach(usgs_service, mock_breach_service):
    """Test breach check when magnitude is below threshold."""
    event = SeismicEventBase(
        usgs_event_id="test123",
        magnitude=3.5,
        magnitude_type="mb",
        magnitude_class="minor",
        depth_km=25.0,
        depth_class="shallow",
        latitude=31.5,
        longitude=74.3,
        earthquake_time=datetime.now(PKT),
        has_breach=False,
        breach_severity=None,
    )
    
    # Mock threshold exists but no breach
    mock_threshold = DisasterThreshold(
        threshold_id=uuid4(),
        disaster_kind="earthquake",
        metric_name="magnitude",
        unit="richter",
        breach_direction="above",
        watch_threshold=4.0,
        warning_threshold=5.0,
        emergency_threshold=6.0,
        extreme_threshold=7.0,
        is_active=True,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = mock_threshold
    mock_breach_service.check_breach.return_value = None  # No breach
    
    has_breach, severity = await usgs_service.check_breach(event)
    
    assert has_breach is False
    assert severity is None


@pytest.mark.asyncio
async def test_check_breach_warning_level(usgs_service, mock_breach_service):
    """Test breach check when magnitude crosses warning threshold."""
    event = SeismicEventBase(
        usgs_event_id="test123",
        magnitude=5.2,
        magnitude_type="mb",
        magnitude_class="moderate",
        depth_km=25.0,
        depth_class="shallow",
        latitude=31.5,
        longitude=74.3,
        resolved_district="Lahore",
        resolved_province="punjab",
        usgs_place="Lahore, Pakistan",
        earthquake_time=datetime.now(PKT),
        has_breach=False,
        breach_severity=None,
    )
    
    # Mock threshold and breach
    mock_threshold = DisasterThreshold(
        threshold_id=uuid4(),
        disaster_kind="earthquake",
        metric_name="magnitude",
        unit="richter",
        breach_direction="above",
        watch_threshold=4.0,
        warning_threshold=5.0,
        emergency_threshold=6.0,
        extreme_threshold=7.0,
        is_active=True,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = mock_threshold
    mock_breach_service.check_breach.return_value = "warning"
    
    has_breach, severity = await usgs_service.check_breach(event)
    
    assert has_breach is True
    assert severity == "warning"
    
    # Should create breach record
    mock_breach_service.create_breach.assert_called_once()


# ── Test: Event Processing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_events_success(usgs_service, mock_seismic_repo, mock_breach_service):
    """Test successful event processing."""
    events = [
        SeismicEventBase(
            usgs_event_id="test1",
            magnitude=4.5,
            magnitude_type="mb",
            magnitude_class="light",
            depth_km=25.0,
            depth_class="shallow",
            latitude=31.5,
            longitude=74.3,
            earthquake_time=datetime.now(PKT),
            has_breach=False,
            breach_severity=None,
        ),
        SeismicEventBase(
            usgs_event_id="test2",
            magnitude=3.2,
            magnitude_type="ml",
            magnitude_class="minor",
            depth_km=10.0,
            depth_class="shallow",
            latitude=33.7,
            longitude=73.0,
            earthquake_time=datetime.now(PKT),
            has_breach=False,
            breach_severity=None,
        ),
    ]
    
    # Mock no breaches
    mock_breach_service.find_applicable_threshold.return_value = None
    
    stats = await usgs_service.process_events(events)
    
    assert stats["events_processed"] == 2
    assert stats["events_upserted"] == 2
    assert stats["breaches_detected"] == 0
    assert stats["errors"] == 0
    
    # Should upsert both events
    assert mock_seismic_repo.upsert_event.call_count == 2


@pytest.mark.asyncio
async def test_process_events_with_breach(usgs_service, mock_seismic_repo, mock_breach_service):
    """Test event processing with breach detection."""
    events = [
        SeismicEventBase(
            usgs_event_id="test1",
            magnitude=5.5,
            magnitude_type="mb",
            magnitude_class="moderate",
            depth_km=25.0,
            depth_class="shallow",
            latitude=31.5,
            longitude=74.3,
            earthquake_time=datetime.now(PKT),
            has_breach=False,
            breach_severity=None,
        ),
    ]
    
    # Mock breach detected
    mock_threshold = DisasterThreshold(
        threshold_id=uuid4(),
        disaster_kind="earthquake",
        metric_name="magnitude",
        unit="richter",
        breach_direction="above",
        watch_threshold=4.0,
        warning_threshold=5.0,
        emergency_threshold=6.0,
        extreme_threshold=7.0,
        is_active=True,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = mock_threshold
    mock_breach_service.check_breach.return_value = "warning"
    
    stats = await usgs_service.process_events(events)
    
    assert stats["events_processed"] == 1
    assert stats["events_upserted"] == 1
    assert stats["breaches_detected"] == 1
    assert stats["errors"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
