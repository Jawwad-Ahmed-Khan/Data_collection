"""
Unit tests for OpenMeteoService — Weather data parsing, rolling sums, flags, breach detection.

Tests cover:
  - Query parameter building (hourly and daily)
  - Hourly data parsing and field extraction
  - Daily data parsing and field extraction
  - Rolling precipitation sums (24h, 72h)
  - Weather flag setting (extreme heat, heatwave, heavy rain, storm, cold wave)
  - Wind direction conversion (degrees to cardinal)
  - WMO weather code decoding
  - Breach detection and creation
  - Location data processing workflow
"""

import pytest
from datetime import datetime, date, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.openmeteo_service import OpenMeteoService
from app.models.weather_models import WeatherHourlyWindowBase, WeatherDailySummaryBase
from app.models.reference_models import PakistanLocation, DisasterThreshold
from app.repositories.weather_repository import WeatherRepository
from app.services.breach_service import BreachService

# Pakistan Standard Time
PKT = ZoneInfo("Asia/Karachi")


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_location() -> PakistanLocation:
    """Create sample Pakistan location for testing."""
    return PakistanLocation(
        location_id=uuid4(),
        location_key="lahore_31.5497_74.3436",
        location_name="Lahore",
        district="Lahore",
        province="punjab",
        latitude=31.5497,
        longitude=74.3436,
        is_active=True,
    )


@pytest.fixture
def mock_weather_repo(mocker):
    """Mock WeatherRepository."""
    repo = mocker.Mock(spec=WeatherRepository)
    repo.upsert_hourly = mocker.AsyncMock()
    repo.upsert_daily = mocker.AsyncMock()
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
def openmeteo_service(mock_weather_repo, mock_breach_service):
    """Create OpenMeteoService instance."""
    return OpenMeteoService(
        weather_repo=mock_weather_repo,
        breach_service=mock_breach_service,
    )


@pytest.fixture
def sample_hourly_response() -> dict:
    """Sample Open-Meteo hourly API response."""
    base_time = datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)
    times = [(base_time + timedelta(hours=i)).isoformat() for i in range(5)]
    
    return {
        "latitude": 31.5497,
        "longitude": 74.3436,
        "timezone": "Asia/Karachi",
        "hourly": {
            "time": times,
            "temperature_2m": [25.0, 26.5, 28.0, 30.0, 32.0],
            "apparent_temperature": [24.0, 25.5, 27.0, 29.0, 31.0],
            "dew_point_2m": [15.0, 16.0, 17.0, 18.0, 19.0],
            "precipitation": [0.0, 0.5, 1.0, 2.0, 0.0],
            "precipitation_probability": [10, 20, 30, 40, 10],
            "wind_speed_10m": [10.0, 15.0, 20.0, 25.0, 12.0],
            "wind_gusts_10m": [20.0, 30.0, 40.0, 50.0, 25.0],
            "wind_direction_10m": [0, 45, 90, 180, 270],
            "relative_humidity_2m": [60, 65, 70, 75, 60],
            "surface_pressure": [1013.0, 1012.5, 1012.0, 1011.5, 1013.0],
            "visibility": [10000.0, 9000.0, 8000.0, 7000.0, 10000.0],
            "uv_index": [5.0, 6.0, 7.0, 8.0, 5.0],
            "weather_code": [0, 1, 2, 61, 95],
            "is_day": [1, 1, 1, 1, 0],
        },
    }


@pytest.fixture
def sample_daily_response() -> dict:
    """Sample Open-Meteo daily API response."""
    base_date = datetime.now(PKT).date()
    dates = [(base_date + timedelta(days=i)).isoformat() for i in range(5)]
    
    base_time = datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)
    sunrises = [(base_time + timedelta(days=i, hours=6)).isoformat() for i in range(5)]
    sunsets = [(base_time + timedelta(days=i, hours=18)).isoformat() for i in range(5)]
    
    return {
        "latitude": 31.5497,
        "longitude": 74.3436,
        "timezone": "Asia/Karachi",
        "daily": {
            "time": dates,
            "temperature_2m_max": [35.0, 36.0, 37.0, 38.0, 39.0],
            "temperature_2m_min": [20.0, 21.0, 22.0, 23.0, 24.0],
            "apparent_temperature_max": [34.0, 35.0, 36.0, 37.0, 38.0],
            "apparent_temperature_min": [19.0, 20.0, 21.0, 22.0, 23.0],
            "precipitation_sum": [0.0, 5.0, 10.0, 15.0, 0.0],
            "precipitation_probability_max": [10, 30, 50, 70, 10],
            "wind_speed_10m_max": [25.0, 30.0, 35.0, 40.0, 25.0],
            "wind_gusts_10m_max": [45.0, 50.0, 55.0, 60.0, 45.0],
            "uv_index_max": [8.0, 9.0, 10.0, 11.0, 8.0],
            "sunrise": sunrises,
            "sunset": sunsets,
        },
    }


# ── Test: Query Parameter Building ────────────────────────────────


def test_build_hourly_params(openmeteo_service):
    """Test building hourly query parameters."""
    params = openmeteo_service.build_hourly_params(
        latitude=31.5497,
        longitude=74.3436,
    )
    
    assert params["latitude"] == 31.5497
    assert params["longitude"] == 74.3436
    assert params["timezone"] == "Asia/Karachi"
    assert params["forecast_days"] == 5
    assert "hourly" in params
    
    # Check core variables are included
    hourly_vars = params["hourly"].split(",")
    assert "temperature_2m" in hourly_vars
    assert "precipitation" in hourly_vars
    assert "wind_speed_10m" in hourly_vars
    assert "weather_code" in hourly_vars


def test_build_daily_params(openmeteo_service):
    """Test building daily query parameters."""
    params = openmeteo_service.build_daily_params(
        latitude=31.5497,
        longitude=74.3436,
    )
    
    assert params["latitude"] == 31.5497
    assert params["longitude"] == 74.3436
    assert params["timezone"] == "Asia/Karachi"
    assert params["forecast_days"] == 5
    assert "daily" in params
    
    # Check core variables are included
    daily_vars = params["daily"].split(",")
    assert "temperature_2m_max" in daily_vars
    assert "precipitation_sum" in daily_vars
    assert "wind_speed_10m_max" in daily_vars
    assert "sunrise" in daily_vars


# ── Test: Hourly Data Parsing ─────────────────────────────────────


def test_parse_hourly_success(openmeteo_service, sample_hourly_response, sample_location):
    """Test successful parsing of hourly weather data."""
    records = openmeteo_service.parse_hourly(sample_hourly_response, sample_location)
    
    assert len(records) == 5
    
    # Check first record
    record = records[0]
    assert record.location_id == sample_location.location_id
    assert record.location_name == "Lahore"
    assert record.district == "Lahore"
    assert record.province == "punjab"
    assert record.temp_c == 25.0
    assert record.temp_apparent_c == 24.0
    assert record.precip_mm == 0.0
    assert record.wind_speed_kmh == 10.0
    assert record.wind_direction_deg == 0
    assert record.wind_direction_cardinal == "N"
    assert record.weather_code == 0
    assert record.weather_condition == "clear"
    assert record.is_daytime is True


def test_parse_hourly_empty_response(openmeteo_service, sample_location):
    """Test parsing empty hourly response."""
    response = {"hourly": {}}
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert len(records) == 0


def test_parse_hourly_missing_hourly_key(openmeteo_service, sample_location):
    """Test parsing response without hourly key."""
    response = {}
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert len(records) == 0


# ── Test: Rolling Precipitation Sums ──────────────────────────────


def test_compute_rolling_sums_24h(openmeteo_service, sample_location):
    """Test 24-hour rolling precipitation sum calculation."""
    # Create 25 hourly records with 1mm precipitation each
    base_time = datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)
    
    response = {
        "hourly": {
            "time": [(base_time + timedelta(hours=i)).isoformat() for i in range(25)],
            "temperature_2m": [25.0] * 25,
            "apparent_temperature": [24.0] * 25,
            "precipitation": [1.0] * 25,
            "wind_speed_10m": [10.0] * 25,
            "relative_humidity_2m": [60] * 25,
            "weather_code": [0] * 25,
            "is_day": [1] * 25,
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    # First record should have 1mm (only itself)
    assert records[0].precip_24h_mm == 1.0
    
    # 24th record should have 24mm (24 hours)
    assert records[23].precip_24h_mm == 24.0
    
    # 25th record should have 24mm (rolling window of 24 hours)
    assert records[24].precip_24h_mm == 24.0


def test_compute_rolling_sums_72h(openmeteo_service, sample_location):
    """Test 72-hour rolling precipitation sum calculation."""
    # Create 73 hourly records with 1mm precipitation each
    base_time = datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)
    
    response = {
        "hourly": {
            "time": [(base_time + timedelta(hours=i)).isoformat() for i in range(73)],
            "temperature_2m": [25.0] * 73,
            "apparent_temperature": [24.0] * 73,
            "precipitation": [1.0] * 73,
            "wind_speed_10m": [10.0] * 73,
            "relative_humidity_2m": [60] * 73,
            "weather_code": [0] * 73,
            "is_day": [1] * 73,
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    # First record should have 1mm
    assert records[0].precip_72h_mm == 1.0
    
    # 72nd record should have 72mm
    assert records[71].precip_72h_mm == 72.0
    
    # 73rd record should have 72mm (rolling window)
    assert records[72].precip_72h_mm == 72.0


# ── Test: Weather Flags ───────────────────────────────────────────


def test_set_weather_flags_extreme_heat(openmeteo_service, sample_location):
    """Test extreme heat flag (>45°C)."""
    response = {
        "hourly": {
            "time": [datetime.now(PKT).isoformat()],
            "temperature_2m": [46.0],
            "apparent_temperature": [45.0],
            "precipitation": [0.0],
            "wind_speed_10m": [10.0],
            "relative_humidity_2m": [30],
            "weather_code": [0],
            "is_day": [1],
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert records[0].flag_extreme_heat is True
    assert records[0].flag_heatwave is True  # Also triggers heatwave


def test_set_weather_flags_heatwave(openmeteo_service, sample_location):
    """Test heatwave flag (>40°C)."""
    response = {
        "hourly": {
            "time": [datetime.now(PKT).isoformat()],
            "temperature_2m": [42.0],
            "apparent_temperature": [41.0],
            "precipitation": [0.0],
            "wind_speed_10m": [10.0],
            "relative_humidity_2m": [30],
            "weather_code": [0],
            "is_day": [1],
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert records[0].flag_heatwave is True
    assert records[0].flag_extreme_heat is False


def test_set_weather_flags_heavy_rain(openmeteo_service, sample_location):
    """Test heavy rain flag (>50mm in 24h)."""
    # Create 24 records with 3mm each = 72mm total
    base_time = datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)
    
    response = {
        "hourly": {
            "time": [(base_time + timedelta(hours=i)).isoformat() for i in range(24)],
            "temperature_2m": [25.0] * 24,
            "apparent_temperature": [24.0] * 24,
            "precipitation": [3.0] * 24,
            "wind_speed_10m": [10.0] * 24,
            "relative_humidity_2m": [80] * 24,
            "weather_code": [61] * 24,
            "is_day": [1] * 24,
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    # Last record should have 72mm in 24h
    assert records[-1].precip_24h_mm == 72.0
    assert records[-1].flag_heavy_rain is True
    assert records[-1].flag_very_heavy_rain is False  # 72mm is not >100mm


def test_set_weather_flags_very_heavy_rain(openmeteo_service, sample_location):
    """Test very heavy rain flag (>100mm in 24h)."""
    # Create 24 records with 5mm each = 120mm total
    base_time = datetime.now(PKT).replace(hour=0, minute=0, second=0, microsecond=0)
    
    response = {
        "hourly": {
            "time": [(base_time + timedelta(hours=i)).isoformat() for i in range(24)],
            "temperature_2m": [25.0] * 24,
            "apparent_temperature": [24.0] * 24,
            "precipitation": [5.0] * 24,
            "wind_speed_10m": [10.0] * 24,
            "relative_humidity_2m": [80] * 24,
            "weather_code": [65] * 24,
            "is_day": [1] * 24,
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    # Last record should have 120mm in 24h
    assert records[-1].precip_24h_mm == 120.0
    assert records[-1].flag_heavy_rain is True
    assert records[-1].flag_very_heavy_rain is True


def test_set_weather_flags_storm(openmeteo_service, sample_location):
    """Test storm flag (wind gusts >60 km/h)."""
    response = {
        "hourly": {
            "time": [datetime.now(PKT).isoformat()],
            "temperature_2m": [25.0],
            "apparent_temperature": [24.0],
            "precipitation": [0.0],
            "wind_speed_10m": [40.0],
            "wind_gusts_10m": [70.0],
            "relative_humidity_2m": [60],
            "weather_code": [95],
            "is_day": [1],
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert records[0].flag_storm is True
    assert records[0].flag_severe_storm is False


def test_set_weather_flags_severe_storm(openmeteo_service, sample_location):
    """Test severe storm flag (wind gusts >90 km/h)."""
    response = {
        "hourly": {
            "time": [datetime.now(PKT).isoformat()],
            "temperature_2m": [25.0],
            "apparent_temperature": [24.0],
            "precipitation": [0.0],
            "wind_speed_10m": [60.0],
            "wind_gusts_10m": [100.0],
            "relative_humidity_2m": [60],
            "weather_code": [95],
            "is_day": [1],
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert records[0].flag_storm is True
    assert records[0].flag_severe_storm is True


def test_set_weather_flags_cold_wave(openmeteo_service, sample_location):
    """Test cold wave flag (<5°C)."""
    response = {
        "hourly": {
            "time": [datetime.now(PKT).isoformat()],
            "temperature_2m": [3.0],
            "apparent_temperature": [1.0],
            "precipitation": [0.0],
            "wind_speed_10m": [10.0],
            "relative_humidity_2m": [60],
            "weather_code": [0],
            "is_day": [1],
        },
    }
    
    records = openmeteo_service.parse_hourly(response, sample_location)
    
    assert records[0].flag_cold_wave is True


# ── Test: Wind Direction Conversion ───────────────────────────────


def test_wind_to_cardinal(openmeteo_service):
    """Test wind direction degree to cardinal conversion."""
    assert openmeteo_service._wind_to_cardinal(0) == "N"
    assert openmeteo_service._wind_to_cardinal(45) == "NE"
    assert openmeteo_service._wind_to_cardinal(90) == "E"
    assert openmeteo_service._wind_to_cardinal(135) == "SE"
    assert openmeteo_service._wind_to_cardinal(180) == "S"
    assert openmeteo_service._wind_to_cardinal(225) == "SW"
    assert openmeteo_service._wind_to_cardinal(270) == "W"
    assert openmeteo_service._wind_to_cardinal(315) == "NW"
    assert openmeteo_service._wind_to_cardinal(360) == "N"


# ── Test: Weather Code Decoding ───────────────────────────────────


def test_decode_weather_code(openmeteo_service):
    """Test WMO weather code decoding."""
    assert openmeteo_service._decode_weather_code(0) == ("clear", "Clear sky")
    assert openmeteo_service._decode_weather_code(1) == ("partly_cloudy", "Mainly clear")
    assert openmeteo_service._decode_weather_code(3) == ("overcast", "Overcast")
    assert openmeteo_service._decode_weather_code(45) == ("fog", "Fog")
    assert openmeteo_service._decode_weather_code(61) == ("rain", "Slight rain")
    assert openmeteo_service._decode_weather_code(65) == ("heavy_rain", "Heavy rain")
    assert openmeteo_service._decode_weather_code(95) == ("thunderstorm", "Thunderstorm")
    
    # Unknown code
    condition, description = openmeteo_service._decode_weather_code(999)
    assert condition == "unknown"
    assert "999" in description


def test_decode_weather_code_none(openmeteo_service):
    """Test weather code decoding with None."""
    condition, description = openmeteo_service._decode_weather_code(None)
    assert condition is None
    assert description is None


# ── Test: Daily Data Parsing ──────────────────────────────────────


def test_parse_daily_success(openmeteo_service, sample_daily_response, sample_location):
    """Test successful parsing of daily weather summaries."""
    summaries = openmeteo_service.parse_daily(sample_daily_response, sample_location)
    
    assert len(summaries) == 5
    
    # Check first summary
    summary = summaries[0]
    assert summary.location_id == sample_location.location_id
    assert summary.location_name == "Lahore"
    assert summary.temp_max_c == 35.0
    assert summary.temp_min_c == 20.0
    assert summary.precip_total_mm == 0.0
    assert summary.wind_speed_max_kmh == 25.0
    assert summary.uv_index_max == 8.0
    assert summary.sunrise_at is not None
    assert summary.sunset_at is not None


def test_parse_daily_empty_response(openmeteo_service, sample_location):
    """Test parsing empty daily response."""
    response = {"daily": {}}
    
    summaries = openmeteo_service.parse_daily(response, sample_location)
    
    assert len(summaries) == 0


def test_set_daily_flags_extreme_heat(openmeteo_service, sample_location):
    """Test daily extreme heat flag (>45°C)."""
    response = {
        "daily": {
            "time": [datetime.now(PKT).date().isoformat()],
            "temperature_2m_max": [46.0],
            "temperature_2m_min": [30.0],
            "precipitation_sum": [0.0],
            "wind_speed_10m_max": [20.0],
        },
    }
    
    summaries = openmeteo_service.parse_daily(response, sample_location)
    
    assert summaries[0].flag_extreme_heat_day is True
    assert summaries[0].flag_heatwave_day is True


def test_set_daily_flags_heavy_rain(openmeteo_service, sample_location):
    """Test daily heavy rain flag (>50mm)."""
    response = {
        "daily": {
            "time": [datetime.now(PKT).date().isoformat()],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [20.0],
            "precipitation_sum": [60.0],
            "wind_speed_10m_max": [20.0],
        },
    }
    
    summaries = openmeteo_service.parse_daily(response, sample_location)
    
    assert summaries[0].flag_heavy_rain_day is True


# ── Test: Breach Detection ────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_breach_no_threshold(openmeteo_service, mock_breach_service, sample_location):
    """Test breach check when no threshold exists."""
    record = WeatherHourlyWindowBase(
        location_id=sample_location.location_id,
        location_key=sample_location.location_key,
        location_name=sample_location.location_name,
        district=sample_location.district,
        province=sample_location.province,
        latitude=sample_location.latitude,
        longitude=sample_location.longitude,
        forecast_for_datetime=datetime.now(PKT),
        forecast_date=datetime.now(PKT).date(),
        day_offset=0,
        temp_c=35.0,
        temp_apparent_c=34.0,
        precip_mm=0.0,
        has_breach=False,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = None
    
    has_breach, severity, metric, value = await openmeteo_service.check_breach(record)
    
    assert has_breach is False
    assert severity is None


@pytest.mark.asyncio
async def test_check_breach_warning_level(openmeteo_service, mock_breach_service, sample_location):
    """Test breach check when temperature crosses warning threshold."""
    record = WeatherHourlyWindowBase(
        location_id=sample_location.location_id,
        location_key=sample_location.location_key,
        location_name=sample_location.location_name,
        district=sample_location.district,
        province=sample_location.province,
        latitude=sample_location.latitude,
        longitude=sample_location.longitude,
        forecast_for_datetime=datetime.now(PKT),
        forecast_date=datetime.now(PKT).date(),
        day_offset=0,
        temp_c=42.0,
        temp_apparent_c=41.0,
        precip_mm=0.0,
        has_breach=False,
    )
    
    # Mock threshold and breach
    mock_threshold = DisasterThreshold(
        threshold_id=uuid4(),
        disaster_kind="heatwave",
        metric_name="temp_max_c",
        unit="celsius",
        breach_direction="above",
        watch_threshold=38.0,
        warning_threshold=40.0,
        emergency_threshold=45.0,
        extreme_threshold=50.0,
        is_active=True,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = mock_threshold
    mock_breach_service.check_breach.return_value = "warning"
    
    has_breach, severity, metric, value = await openmeteo_service.check_breach(record)
    
    assert has_breach is True
    assert severity == "warning"
    assert metric == "temp_max_c"
    assert value == 42.0
    
    # Should create breach record
    mock_breach_service.create_breach.assert_called_once()


# ── Test: Location Processing ─────────────────────────────────────


@pytest.mark.asyncio
async def test_process_location_success(openmeteo_service, mock_weather_repo, mock_breach_service, sample_location):
    """Test successful location data processing."""
    hourly_records = [
        WeatherHourlyWindowBase(
            location_id=sample_location.location_id,
            location_key=sample_location.location_key,
            location_name=sample_location.location_name,
            district=sample_location.district,
            province=sample_location.province,
            latitude=sample_location.latitude,
            longitude=sample_location.longitude,
            forecast_for_datetime=datetime.now(PKT),
            forecast_date=datetime.now(PKT).date(),
            day_offset=0,
            temp_c=35.0,
            temp_apparent_c=34.0,
            precip_mm=0.0,
            has_breach=False,
        ),
    ]
    
    daily_summaries = [
        WeatherDailySummaryBase(
            location_id=sample_location.location_id,
            location_key=sample_location.location_key,
            location_name=sample_location.location_name,
            district=sample_location.district,
            province=sample_location.province,
            latitude=sample_location.latitude,
            longitude=sample_location.longitude,
            summary_date=datetime.now(PKT).date(),
            day_offset=0,
            temp_max_c=35.0,
            temp_min_c=20.0,
            precip_total_mm=0.0,
        ),
    ]
    
    # Mock no breaches
    mock_breach_service.find_applicable_threshold.return_value = None
    
    stats = await openmeteo_service.process_location(hourly_records, daily_summaries)
    
    assert stats["hourly_upserted"] == 1
    assert stats["daily_upserted"] == 1
    assert stats["breaches_detected"] == 0
    assert stats["errors"] == 0
    
    # Should upsert records
    mock_weather_repo.upsert_hourly.assert_called_once()
    mock_weather_repo.upsert_daily.assert_called_once()


@pytest.mark.asyncio
async def test_process_location_with_breach(openmeteo_service, mock_weather_repo, mock_breach_service, sample_location):
    """Test location processing with breach detection."""
    hourly_records = [
        WeatherHourlyWindowBase(
            location_id=sample_location.location_id,
            location_key=sample_location.location_key,
            location_name=sample_location.location_name,
            district=sample_location.district,
            province=sample_location.province,
            latitude=sample_location.latitude,
            longitude=sample_location.longitude,
            forecast_for_datetime=datetime.now(PKT),
            forecast_date=datetime.now(PKT).date(),
            day_offset=0,
            temp_c=42.0,
            temp_apparent_c=41.0,
            precip_mm=0.0,
            has_breach=False,
        ),
    ]
    
    # Mock breach detected
    mock_threshold = DisasterThreshold(
        threshold_id=uuid4(),
        disaster_kind="heatwave",
        metric_name="temp_max_c",
        unit="celsius",
        breach_direction="above",
        watch_threshold=38.0,
        warning_threshold=40.0,
        emergency_threshold=45.0,
        extreme_threshold=50.0,
        is_active=True,
    )
    
    mock_breach_service.find_applicable_threshold.return_value = mock_threshold
    mock_breach_service.check_breach.return_value = "warning"
    
    stats = await openmeteo_service.process_location(hourly_records, [])
    
    assert stats["hourly_upserted"] == 1
    assert stats["breaches_detected"] == 1
    assert stats["errors"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
