"""
Unit tests for Health Controller — health check endpoints.

Tests cover:
  - Basic health check endpoint
  - API health status endpoint
  - API key authentication (valid, invalid, missing)
  - Database connectivity status
  - Backoff period detection
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.health_controller import router, _SERVICE_START_TIME
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
    db.is_connected = True
    db.fetch_many = mocker.AsyncMock(return_value=[])
    return db


@pytest.fixture
def app(mock_db):
    """Create FastAPI test app."""
    test_app = FastAPI()
    test_app.include_router(router)
    
    # Override database dependency
    from app.api.routes import health_controller
    health_controller._db_pool = mock_db
    
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_settings(mocker):
    """Mock settings with test API key."""
    with patch("app.api.routes.health_controller.settings") as mock:
        mock.main_system_api_key = VALID_API_KEY
        yield mock


# ── Test: Basic Health Check ──────────────────────────────────────


def test_get_health_success(client, mock_settings):
    """Test successful health check."""
    response = client.get(
        "/health",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert data["database_connected"] is True
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0
    assert "timestamp_pkt" in data


def test_get_health_database_disconnected(client, mock_settings, mock_db):
    """Test health check when database is disconnected."""
    mock_db.is_connected = False
    
    response = client.get(
        "/health",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "degraded"
    assert data["database_connected"] is False


def test_get_health_missing_api_key(client, mock_settings):
    """Test health check without API key."""
    response = client.get("/health")
    
    assert response.status_code == 403
    assert "Invalid or missing X-API-Key" in response.json()["detail"]


def test_get_health_invalid_api_key(client, mock_settings):
    """Test health check with invalid API key."""
    response = client.get(
        "/health",
        headers={"X-API-Key": "wrong-key"},
    )
    
    assert response.status_code == 403
    assert "Invalid or missing X-API-Key" in response.json()["detail"]


# ── Test: API Health Status ───────────────────────────────────────


def test_get_api_health_success(client, mock_settings, mock_db):
    """Test successful API health status retrieval."""
    # Mock API registry data
    now = datetime.now(PKT)
    mock_db.fetch_many.return_value = [
        {
            "api_name": "usgs",
            "display_name": "USGS Earthquake API",
            "current_health": "healthy",
            "last_success_at": now - timedelta(minutes=1),
            "last_failure_at": None,
            "consecutive_failures": 0,
            "backoff_until": None,
        },
        {
            "api_name": "open_meteo",
            "display_name": "Open-Meteo Weather API",
            "current_health": "healthy",
            "last_success_at": now - timedelta(minutes=5),
            "last_failure_at": None,
            "consecutive_failures": 0,
            "backoff_until": None,
        },
    ]
    
    response = client.get(
        "/health/apis",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "apis" in data
    assert len(data["apis"]) == 2
    
    # Check first API
    usgs_api = data["apis"][0]
    assert usgs_api["api_name"] == "usgs"
    assert usgs_api["display_name"] == "USGS Earthquake API"
    assert usgs_api["current_health"] == "healthy"
    assert usgs_api["consecutive_failures"] == 0
    assert usgs_api["is_in_backoff"] is False
    assert usgs_api["backoff_remaining_seconds"] is None


def test_get_api_health_with_backoff(client, mock_settings, mock_db):
    """Test API health status when API is in backoff."""
    now = datetime.now(PKT)
    backoff_until = now + timedelta(minutes=5)
    
    mock_db.fetch_many.return_value = [
        {
            "api_name": "usgs",
            "display_name": "USGS Earthquake API",
            "current_health": "rate_limited",
            "last_success_at": now - timedelta(minutes=10),
            "last_failure_at": now - timedelta(minutes=1),
            "consecutive_failures": 3,
            "backoff_until": backoff_until,
        },
    ]
    
    response = client.get(
        "/health/apis",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    api = data["apis"][0]
    assert api["is_in_backoff"] is True
    assert api["backoff_remaining_seconds"] is not None
    assert 290 < api["backoff_remaining_seconds"] < 310  # ~5 minutes


def test_get_api_health_expired_backoff(client, mock_settings, mock_db):
    """Test API health status when backoff has expired."""
    now = datetime.now(PKT)
    backoff_until = now - timedelta(minutes=5)  # Expired
    
    mock_db.fetch_many.return_value = [
        {
            "api_name": "usgs",
            "display_name": "USGS Earthquake API",
            "current_health": "healthy",
            "last_success_at": now - timedelta(minutes=1),
            "last_failure_at": now - timedelta(minutes=10),
            "consecutive_failures": 0,
            "backoff_until": backoff_until,
        },
    ]
    
    response = client.get(
        "/health/apis",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    api = data["apis"][0]
    assert api["is_in_backoff"] is False
    assert api["backoff_remaining_seconds"] is None


def test_get_api_health_no_apis(client, mock_settings, mock_db):
    """Test API health status when no APIs are configured."""
    mock_db.fetch_many.return_value = []
    
    response = client.get(
        "/health/apis",
        headers={"X-API-Key": VALID_API_KEY},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["apis"] == []


def test_get_api_health_missing_api_key(client, mock_settings):
    """Test API health status without API key."""
    response = client.get("/health/apis")
    
    assert response.status_code == 403


def test_get_api_health_invalid_api_key(client, mock_settings):
    """Test API health status with invalid API key."""
    response = client.get(
        "/health/apis",
        headers={"X-API-Key": "wrong-key"},
    )
    
    assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
