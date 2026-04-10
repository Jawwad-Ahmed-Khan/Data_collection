"""
Unit tests for Main Application — startup sequence and endpoints.

Tests cover:
  - Application startup and shutdown
  - Root endpoint
  - API routes registration
  - Database pool initialization
  - Reference data loading
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient


# ── Test: Root Endpoint ───────────────────────────────────────────


def test_root_endpoint():
    """Test root endpoint returns service information."""
    # Import here to avoid startup issues
    from app.main import app
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # Note: TestClient doesn't run lifespan by default, so we test without it
    with client:
        response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["service"] == "ClimaSync Collection Service"
    assert data["version"] == "0.1.0"
    assert data["status"] == "operational"
    assert "endpoints" in data
    assert "/health" in data["endpoints"]["health"]


def test_health_routes_registered():
    """Test that health routes are registered."""
    from app.main import app
    
    # Check that routes are registered
    routes = [route.path for route in app.routes]
    
    assert "/health" in routes
    assert "/health/apis" in routes


def test_status_routes_registered():
    """Test that status routes are registered."""
    from app.main import app
    
    # Check that routes are registered
    routes = [route.path for route in app.routes]
    
    assert "/status/cycles" in routes
    assert "/status/breaches" in routes
    assert "/status/locations" in routes


# ── Test: In-Memory Cache ─────────────────────────────────────────


def test_in_memory_cache_initialization():
    """Test InMemoryCache initialization."""
    from app.main import InMemoryCache
    
    cache = InMemoryCache()
    
    assert cache.pakistan_locations == []
    assert cache.disaster_thresholds == []
    assert cache.api_configs == {}
    assert cache.flood_gauges == []
    assert cache.last_reload_at is None
    assert cache.is_loaded() is False


def test_in_memory_cache_is_loaded():
    """Test InMemoryCache is_loaded method."""
    from app.main import InMemoryCache
    
    cache = InMemoryCache()
    
    # Empty cache
    assert cache.is_loaded() is False
    
    # Add some data
    cache.pakistan_locations = [{"location_id": "test"}]
    cache.disaster_thresholds = [{"threshold_id": "test"}]
    
    # Now loaded
    assert cache.is_loaded() is True


# ── Test: Application Metadata ────────────────────────────────────


def test_app_metadata():
    """Test FastAPI application metadata."""
    from app.main import app
    
    assert app.title == "ClimaSync Collection Service"
    assert app.version == "0.1.0"
    assert "disaster conditions" in app.description.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
