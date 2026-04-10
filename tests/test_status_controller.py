"""
Unit tests for Status Controller — operational status endpoints.

Tests cover:
  - Collection cycles endpoint
  - Breach statistics endpoint
  - Location polling status endpoint
  - API key authentication
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.status_controller import router
from app.database.connection import DatabasePool

# Pakistan Standard Time
PKT = ZoneInfo("Asia/Karachi")

# Valid API key for testing
VALID_API_KEY = "test-api-key-12345"


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_db(mocker):
    """Mock DatabasePool."""
    db = mocker.Mock(spec=DatabasePool)
    db.fetch_many = mocker.AsyncMock(return_value=[])
    db.fetch_one = mocker.AsyncMock(return_value=None)
    return db


@pytest.fixture
def app(mock_db):
    """Create FastAPI test app."""
    test_app = FastAPI()
    test_app.include_router(router)
    
    # Override database dependency
    from app.api.routes import status_controller
    status_controller._db_pool = mock_db
    
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_settings(mocker):
    """Mock settings with test API key."""
    with patch("app.api.routes.status_controller.settings") as mock:
        mock.main_system_api_key = VALID_API_KEY
        yield mock


# ── Test: Collection Cycles ───────────────────────────────────────


def test_get_cycles_success(client, mock_settings, mock_db):
    """Test successful cycles retrieval."""
    now = datetime.now(PKT)
    cycle_id = uuid4()
    
    mock_db.fetch_many.return_value = [
        {
            "cycle_id": cycle_id,
            "api_name": "usgs",
            "cycle_type": "scheduled",
            "status": "completed",
            "locations_targeted": 10,
            "locations_success": 10,
            "locations_failed": 0,
            "rows_upserted": 5,
            "breaches_triggered": 1,
            "rate_limit_hits": 0,
            "started_at": now - timedelta(minutes=5),
            "completed_at": now - timedelta(minutes=4),
            "duration_ms": 60000,
        },
    ]
    
    response = client.get(
        "/status/cycles",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "cycles" in data
    assert len(data["cycles"]) == 1
    
    cycle = data["cycles"][0]
    assert cycle["api_name"] == "usgs"
    assert cycle["status"] == "completed"
    assert cycle["locations_targeted"] == 10
    assert cycle["locations_success"] == 10
    assert cycle["breaches_triggered"] == 1


def test_get_cycles_multiple_apis(client, mock_settings, mock_db):
    """Test cycles retrieval with multiple APIs."""
    now = datetime.now(PKT)
    
    mock_db.fetch_many.return_value = [
        {
            "cycle_id": uuid4(),
            "api_name": "usgs",
            "cycle_type": "scheduled",
            "status": "completed",
            "locations_targeted": 5,
            "locations_success": 5,
            "locations_failed": 0,
            "rows_upserted": 3,
            "breaches_triggered": 0,
            "rate_limit_hits": 0,
            "started_at": now - timedelta(minutes=2),
            "completed_at": now - timedelta(minutes=1),
            "duration_ms": 30000,
        },
        {
            "cycle_id": uuid4(),
            "api_name": "open_meteo",
            "cycle_type": "scheduled",
            "status": "completed",
            "locations_targeted": 270,
            "locations_success": 270,
            "locations_failed": 0,
            "rows_upserted": 32400,
            "breaches_triggered": 2,
            "rate_limit_hits": 0,
            "started_at": now - timedelta(minutes=10),
            "completed_at": now - timedelta(minutes=5),
            "duration_ms": 300000,
        },
    ]
    
    response = client.get(
        "/status/cycles",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["cycles"]) == 2
    assert data["cycles"][0]["api_name"] == "usgs"
    assert data["cycles"][1]["api_name"] == "open_meteo"


def test_get_cycles_no_cycles(client, mock_settings, mock_db):
    """Test cycles retrieval when no cycles exist."""
    mock_db.fetch_many.return_value = []
    
    response = client.get(
        "/status/cycles",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["cycles"] == []


def test_get_cycles_missing_api_key(client, mock_settings):
    """Test cycles endpoint without API key."""
    response = client.get("/status/cycles")
    
    assert response.status_code == 403


# ── Test: Breach Statistics ───────────────────────────────────────


def test_get_breaches_success(client, mock_settings, mock_db):
    """Test successful breach statistics retrieval."""
    now = datetime.now(PKT)
    
    mock_db.fetch_one.return_value = {
        "pending_count": 5,
        "dispatched_count": 20,
        "failed_count": 2,
        "last_breach_at": now - timedelta(minutes=10),
    }
    
    response = client.get(
        "/status/breaches",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "summary" in data
    summary = data["summary"]
    assert summary["pending_count"] == 5
    assert summary["dispatched_count"] == 20
    assert summary["failed_count"] == 2
    assert summary["last_breach_at"] is not None


def test_get_breaches_no_breaches(client, mock_settings, mock_db):
    """Test breach statistics when no breaches exist."""
    mock_db.fetch_one.return_value = {
        "pending_count": 0,
        "dispatched_count": 0,
        "failed_count": 0,
        "last_breach_at": None,
    }
    
    response = client.get(
        "/status/breaches",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    summary = data["summary"]
    assert summary["pending_count"] == 0
    assert summary["dispatched_count"] == 0
    assert summary["failed_count"] == 0
    assert summary["last_breach_at"] is None


def test_get_breaches_missing_api_key(client, mock_settings):
    """Test breaches endpoint without API key."""
    response = client.get("/status/breaches")
    
    assert response.status_code == 403


# ── Test: Location Polling Status ─────────────────────────────────


def test_get_locations_success(client, mock_settings, mock_db):
    """Test successful location status retrieval."""
    now = datetime.now(PKT)
    
    mock_db.fetch_many.return_value = [
        {
            "location_id": uuid4(),
            "location_name": "Lahore",
            "district": "Lahore",
            "province": "punjab",
            "last_polled_at": now - timedelta(minutes=15),
            "next_poll_due_at": now + timedelta(minutes=165),
            "consecutive_failures": 0,
            "poll_priority": "high",
        },
        {
            "location_id": uuid4(),
            "location_name": "Karachi",
            "district": "Karachi",
            "province": "sindh",
            "last_polled_at": now - timedelta(minutes=20),
            "next_poll_due_at": now + timedelta(minutes=160),
            "consecutive_failures": 0,
            "poll_priority": "high",
        },
    ]
    
    response = client.get(
        "/status/locations",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "locations" in data
    assert data["total_locations"] == 2
    assert len(data["locations"]) == 2
    
    lahore = data["locations"][0]
    assert lahore["location_name"] == "Lahore"
    assert lahore["district"] == "Lahore"
    assert lahore["province"] == "punjab"
    assert lahore["consecutive_failures"] == 0
    assert lahore["poll_priority"] == "high"


def test_get_locations_with_failures(client, mock_settings, mock_db):
    """Test location status with consecutive failures."""
    now = datetime.now(PKT)
    
    mock_db.fetch_many.return_value = [
        {
            "location_id": uuid4(),
            "location_name": "Quetta",
            "district": "Quetta",
            "province": "balochistan",
            "last_polled_at": now - timedelta(hours=2),
            "next_poll_due_at": now - timedelta(hours=1),  # Overdue
            "consecutive_failures": 3,
            "poll_priority": "medium",
        },
    ]
    
    response = client.get(
        "/status/locations",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    location = data["locations"][0]
    assert location["consecutive_failures"] == 3
    assert location["location_name"] == "Quetta"


def test_get_locations_never_polled(client, mock_settings, mock_db):
    """Test location status for locations never polled."""
    mock_db.fetch_many.return_value = [
        {
            "location_id": uuid4(),
            "location_name": "New Location",
            "district": "Test District",
            "province": "punjab",
            "last_polled_at": None,
            "next_poll_due_at": None,
            "consecutive_failures": 0,
            "poll_priority": "low",
        },
    ]
    
    response = client.get(
        "/status/locations",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    location = data["locations"][0]
    assert location["last_polled_at"] is None
    assert location["next_poll_due_at"] is None


def test_get_locations_no_locations(client, mock_settings, mock_db):
    """Test location status when no locations exist."""
    mock_db.fetch_many.return_value = []
    
    response = client.get(
        "/status/locations",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["locations"] == []
    assert data["total_locations"] == 0


def test_get_locations_missing_api_key(client, mock_settings):
    """Test locations endpoint without API key."""
    response = client.get("/status/locations")
    
    assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
