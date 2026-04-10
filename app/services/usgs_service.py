"""
ClimaSync Collection Service — USGS Earthquake Service

Parses USGS GeoJSON earthquake data and processes it for storage.

Key responsibilities:
  - Parse USGS GeoJSON response into SeismicEventBase objects
  - Convert USGS unix milliseconds to PKT datetime
  - Resolve nearest Pakistan location using coordinate distance
  - Classify magnitude and depth
  - Check for threshold breaches
  - UPSERT events to database
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.logger import get_logger
from app.models.seismic_models import SeismicEventBase
from app.models.reference_models import PakistanLocation
from app.repositories.seismic_repository import SeismicRepository
from app.services.breach_service import BreachService

logger = get_logger(__name__)

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class USGSService:
    """Processes USGS earthquake data.
    
    Parses GeoJSON responses, resolves locations, checks breaches,
    and stores events in the database.
    """

    def __init__(
        self,
        seismic_repo: SeismicRepository,
        breach_service: BreachService,
        pakistan_locations: list[PakistanLocation],
    ) -> None:
        """Initialize USGS service.
        
        Args:
            seismic_repo: Repository for storing seismic events.
            breach_service: Service for checking threshold breaches.
            pakistan_locations: List of all Pakistan monitoring locations.
        """
        self.seismic_repo = seismic_repo
        self.breach_service = breach_service
        self.pakistan_locations = pakistan_locations
        
        logger.info(
            "USGSService initialized with %d Pakistan locations",
            len(pakistan_locations),
        )

    # ── GeoJSON Parsing ───────────────────────────────────────────

    def parse_usgs_response(self, geojson: dict[str, Any]) -> list[SeismicEventBase]:
        """Parse USGS GeoJSON response into SeismicEventBase objects.
        
        Args:
            geojson: USGS GeoJSON response with 'features' array.
        
        Returns:
            List of parsed seismic events.
        """
        features = geojson.get("features", [])
        
        if not features:
            logger.info("No earthquake features in USGS response")
            return []
        
        events: list[SeismicEventBase] = []
        
        for feature in features:
            try:
                event = self._parse_feature(feature)
                if event:
                    events.append(event)
            except Exception as e:
                logger.error(
                    "Failed to parse USGS feature %s: %s",
                    feature.get("id", "unknown"),
                    str(e),
                )
                continue
        
        logger.info("Parsed %d earthquake events from USGS", len(events))
        return events

    def _parse_feature(self, feature: dict[str, Any]) -> SeismicEventBase | None:
        """Parse a single GeoJSON feature into SeismicEventBase.
        
        Args:
            feature: Single feature from USGS GeoJSON.
        
        Returns:
            Parsed seismic event or None if invalid.
        """
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        
        # Extract required fields
        usgs_event_id = feature.get("id")
        if not usgs_event_id:
            logger.warning("Feature missing 'id', skipping")
            return None
        
        magnitude = properties.get("mag")
        if magnitude is None:
            logger.warning("Event %s missing magnitude, skipping", usgs_event_id)
            return None
        
        # Extract coordinates (GeoJSON format: [longitude, latitude, depth])
        if len(coordinates) < 3:
            logger.warning("Event %s missing coordinates, skipping", usgs_event_id)
            return None
        
        longitude = coordinates[0]
        latitude = coordinates[1]
        depth_km = coordinates[2]  # USGS provides depth in km
        
        # Convert USGS unix milliseconds to datetime
        earthquake_time_ms = properties.get("time")
        if earthquake_time_ms is None:
            logger.warning("Event %s missing time, skipping", usgs_event_id)
            return None
        
        earthquake_time = self._convert_usgs_time(earthquake_time_ms)
        
        # Extract optional fields
        magnitude_type = properties.get("magType")
        usgs_place = properties.get("place")
        felt_reports = properties.get("felt")
        cdi = properties.get("cdi")
        mmi = properties.get("mmi")
        tsunami_flag = properties.get("tsunami", 0) == 1
        usgs_alert_level = properties.get("alert")
        significance = properties.get("sig")
        data_quality = self._map_status_to_quality(properties.get("status", "automatic"))
        
        # Classify magnitude and depth
        magnitude_class = self._classify_magnitude(magnitude)
        depth_class = self._classify_depth(depth_km)
        
        # Resolve nearest Pakistan location
        nearest_location, distance_km = self._find_nearest_location(latitude, longitude)
        
        resolved_district = nearest_location.district if nearest_location else None
        resolved_province = nearest_location.province if nearest_location else None
        nearest_location_id = nearest_location.location_id if nearest_location else None
        
        # Create event object
        event = SeismicEventBase(
            usgs_event_id=usgs_event_id,
            magnitude=magnitude,
            magnitude_type=magnitude_type,
            magnitude_class=magnitude_class,
            depth_km=depth_km,
            depth_class=depth_class,
            latitude=latitude,
            longitude=longitude,
            usgs_place=usgs_place,
            resolved_district=resolved_district,
            resolved_province=resolved_province,
            nearest_location_id=nearest_location_id,
            distance_to_nearest_km=distance_km,
            felt_reports=felt_reports,
            cdi=cdi,
            mmi=mmi,
            tsunami_flag=tsunami_flag,
            usgs_alert_level=usgs_alert_level,
            significance=significance,
            data_quality=data_quality,
            earthquake_time=earthquake_time,
            has_breach=False,  # Will be set by breach check
            breach_severity=None,
        )
        
        return event

    # ── Time Conversion ───────────────────────────────────────────

    def _convert_usgs_time(self, unix_ms: int) -> datetime:
        """Convert USGS unix milliseconds to PKT datetime.
        
        Args:
            unix_ms: Unix timestamp in milliseconds.
        
        Returns:
            Datetime in PKT timezone.
        """
        # Convert milliseconds to seconds
        unix_seconds = unix_ms / 1000.0
        
        # Create UTC datetime
        dt_utc = datetime.fromtimestamp(unix_seconds, tz=timezone.utc)
        
        # Convert to PKT
        dt_pkt = dt_utc.astimezone(_PKT)
        
        return dt_pkt

    # ── Classification ────────────────────────────────────────────

    def _classify_magnitude(self, magnitude: float) -> str:
        """Classify earthquake magnitude.
        
        Args:
            magnitude: Earthquake magnitude.
        
        Returns:
            Magnitude class: micro, minor, light, moderate, strong, major, great.
        """
        if magnitude < 2.0:
            return "micro"
        elif magnitude < 4.0:
            return "minor"
        elif magnitude < 5.0:
            return "light"
        elif magnitude < 6.0:
            return "moderate"
        elif magnitude < 7.0:
            return "strong"
        elif magnitude < 8.0:
            return "major"
        else:
            return "great"

    def _classify_depth(self, depth_km: float) -> str:
        """Classify earthquake depth.
        
        Args:
            depth_km: Earthquake depth in kilometers.
        
        Returns:
            Depth class: shallow, intermediate, deep.
        """
        if depth_km < 70:
            return "shallow"
        elif depth_km < 300:
            return "intermediate"
        else:
            return "deep"

    def _map_status_to_quality(self, status: str) -> str:
        """Map USGS status to data quality enum.
        
        Args:
            status: USGS status (automatic, reviewed, deleted).
        
        Returns:
            Data quality: automatic, reviewed, deleted.
        """
        status_lower = status.lower()
        if status_lower in ("automatic", "reviewed", "deleted"):
            return status_lower
        return "automatic"

    # ── Location Resolution ───────────────────────────────────────

    def _find_nearest_location(
        self,
        latitude: float,
        longitude: float,
    ) -> tuple[PakistanLocation | None, float | None]:
        """Find nearest Pakistan location to earthquake coordinates.
        
        Uses Haversine formula to calculate great-circle distance.
        
        Args:
            latitude: Earthquake latitude.
            longitude: Earthquake longitude.
        
        Returns:
            Tuple of (nearest_location, distance_km) or (None, None).
        """
        if not self.pakistan_locations:
            return None, None
        
        nearest_location = None
        min_distance = float("inf")
        
        for location in self.pakistan_locations:
            distance = self._haversine_distance(
                latitude,
                longitude,
                location.latitude,
                location.longitude,
            )
            
            if distance < min_distance:
                min_distance = distance
                nearest_location = location
        
        return nearest_location, round(min_distance, 2)

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate great-circle distance between two points using Haversine formula.
        
        Args:
            lat1: Latitude of point 1.
            lon1: Longitude of point 1.
            lat2: Latitude of point 2.
            lon2: Longitude of point 2.
        
        Returns:
            Distance in kilometers.
        """
        # Earth radius in kilometers
        R = 6371.0
        
        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        distance = R * c
        
        return distance

    # ── Breach Detection ──────────────────────────────────────────

    async def check_breach(self, event: SeismicEventBase) -> tuple[bool, str | None]:
        """Check if earthquake magnitude crosses threshold.
        
        Args:
            event: Seismic event to check.
        
        Returns:
            Tuple of (has_breach, breach_severity).
        """
        # Find applicable threshold for earthquake magnitude
        threshold = self.breach_service.find_applicable_threshold(
            metric_name="magnitude",
            disaster_kind="earthquake",
            province=event.resolved_province,
            district=event.resolved_district,
        )
        
        if not threshold:
            logger.debug(
                "No earthquake threshold found for %s, %s",
                event.resolved_district,
                event.resolved_province,
            )
            return False, None
        
        # Check if magnitude breaches threshold
        severity = self.breach_service.check_breach(
            value=event.magnitude,
            threshold=threshold,
        )
        
        if not severity:
            return False, None
        
        # Create breach record
        await self.breach_service.create_breach(
            source_api="usgs",
            disaster_kind="earthquake",
            metric_name="magnitude",
            observed_value=event.magnitude,
            threshold=threshold,
            severity=severity,
            observation_time=event.earthquake_time,
            location_name=event.usgs_place,
            district=event.resolved_district,
            province=event.resolved_province,
            latitude=event.latitude,
            longitude=event.longitude,
            seismic_event_id=None,  # Will be set after UPSERT
        )
        
        logger.info(
            "Earthquake breach detected: M%.1f at %s (severity: %s)",
            event.magnitude,
            event.usgs_place or "unknown location",
            severity,
        )
        
        return True, severity

    # ── Event Processing ──────────────────────────────────────────

    async def process_events(self, events: list[SeismicEventBase]) -> dict[str, int]:
        """Process parsed events: check breaches and UPSERT to database.
        
        Args:
            events: List of parsed seismic events.
        
        Returns:
            Dictionary with processing statistics.
        """
        stats = {
            "events_processed": 0,
            "events_upserted": 0,
            "breaches_detected": 0,
            "errors": 0,
        }
        
        for event in events:
            try:
                # Check for breach
                has_breach, breach_severity = await self.check_breach(event)
                event.has_breach = has_breach
                event.breach_severity = breach_severity
                
                if has_breach:
                    stats["breaches_detected"] += 1
                
                # UPSERT event to database
                event_id = await self.seismic_repo.upsert_event(event)
                stats["events_upserted"] += 1
                
                logger.debug(
                    "Upserted earthquake: %s (M%.1f, %s, breach=%s)",
                    event.usgs_event_id,
                    event.magnitude,
                    event.usgs_place,
                    has_breach,
                )
                
                stats["events_processed"] += 1
                
            except Exception as e:
                logger.error(
                    "Failed to process event %s: %s",
                    event.usgs_event_id,
                    str(e),
                )
                stats["errors"] += 1
                continue
        
        logger.info(
            "Processed %d events: %d upserted, %d breaches, %d errors",
            stats["events_processed"],
            stats["events_upserted"],
            stats["breaches_detected"],
            stats["errors"],
        )
        
        return stats
