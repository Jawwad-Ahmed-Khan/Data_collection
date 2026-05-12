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
from decimal import Decimal
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


def to_decimal(value: Any) -> Decimal | None:
    """
    Safely convert value to Decimal.
    
    Returns None if input is None or invalid.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


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

    async def parse_usgs_response(self, geojson: dict[str, Any]) -> list[SeismicEventBase]:
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
                event = await self._parse_feature(feature)
                if event:
                    events.append(event)
            except Exception as e:
                logger.warning(
                    "Failed to parse feature [usgs_event_id=%s]: %s",
                    feature.get("id", "unknown"),
                    str(e),
                )
                continue
        
        logger.info("Parsed %d earthquake events from USGS", len(events))
        return events

    async def _parse_feature(self, feature: dict[str, Any]) -> SeismicEventBase | None:
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
        if not usgs_event_id or not isinstance(usgs_event_id, str):
            logger.warning("Feature missing valid 'id', skipping")
            return None
            
        status = properties.get("status", "").lower()
        if status == "deleted":
            logger.debug("Skipping deleted event [usgs_event_id=%s]", usgs_event_id)
            return None
        
        magnitude_raw = properties.get("mag")
        if magnitude_raw is None:
            logger.debug("Skipping event with null magnitude [usgs_event_id=%s]", usgs_event_id)
            return None
            
        magnitude = to_decimal(magnitude_raw)
        if magnitude is None:
            logger.debug("Skipping event with invalid magnitude [usgs_event_id=%s]", usgs_event_id)
            return None
        
        # Extract coordinates (GeoJSON format: [longitude, latitude, depth])
        if not geometry or len(coordinates) < 2:
            logger.warning("Event %s missing valid coordinates, skipping", usgs_event_id)
            return None
        
        longitude = coordinates[0]
        latitude = coordinates[1]
        depth_raw = coordinates[2] if len(coordinates) >= 3 else None  # USGS provides depth in km
        depth_km = to_decimal(depth_raw)
        
        # Validate coordinate bounds
        if not (23.0 <= latitude <= 38.0 and 60.0 <= longitude <= 78.0):
            logger.debug("Event %s outside Pakistan bounds, skipping", usgs_event_id)
            return None
        
        # Convert USGS unix milliseconds to datetime
        earthquake_time_ms = properties.get("time")
        if earthquake_time_ms is None:
            logger.warning("Event %s missing time, skipping", usgs_event_id)
            return None
        
        earthquake_time = self._convert_usgs_time(earthquake_time_ms)
        
        # Extract optional fields
        magnitude_type = properties.get("magType")
        usgs_place = properties.get("place")
        usgs_event_url = properties.get("url")
        felt_reports = properties.get("felt")
        cdi = to_decimal(properties.get("cdi"))
        mmi = to_decimal(properties.get("mmi"))
        tsunami_flag = properties.get("tsunami", 0) == 1
        usgs_alert_level = properties.get("alert")
        significance = properties.get("sig")
        station_count = properties.get("nst")
        azimuthal_gap_deg = to_decimal(properties.get("gap"))
        rms_seconds = to_decimal(properties.get("rms"))
        
        # contributing_networks is often a comma-separated string like ",us,ak,ci," or just "us"
        sources_str = properties.get("sources", "")
        contributing_networks = [s.strip() for s in sources_str.split(",") if s.strip()] if sources_str else None
        
        data_quality = self._map_status_to_quality(properties.get("status", "automatic"))
        usgs_last_updated_at = self._convert_usgs_time(properties.get("updated")) if properties.get("updated") else None
        # Classify magnitude and depth
        magnitude_class = self._classify_magnitude(magnitude)
        depth_class = self._classify_depth(depth_km)
        
        # Resolve nearest Pakistan location using DB
        nearest_location_dict, distance_km = await self.seismic_repo.find_nearest_location(longitude, latitude)
        
        resolved_district = nearest_location_dict.get("district") if nearest_location_dict else None
        resolved_province = nearest_location_dict.get("province") if nearest_location_dict else None
        nearest_location_id = nearest_location_dict.get("location_id") if nearest_location_dict else None
        
        # Create event object
        event = SeismicEventBase(
            usgs_event_id=usgs_event_id,
            usgs_event_url=usgs_event_url,
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
            station_count=station_count,
            azimuthal_gap_deg=azimuthal_gap_deg,
            rms_seconds=rms_seconds,
            contributing_networks=contributing_networks,
            data_quality=data_quality,
            earthquake_time=earthquake_time,
            usgs_last_updated_at=usgs_last_updated_at,
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

    def evaluate_breach(self, event: SeismicEventBase) -> tuple[str | None, Any | None]:
        """Evaluate if earthquake magnitude crosses threshold without creating breach record.
        
        Args:
            event: Seismic event to check.
        
        Returns:
            Tuple of (breach_severity, threshold).
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
            return None, None
        
        # Check if magnitude breaches threshold
        severity = self.breach_service.check_breach(
            value=event.magnitude,
            threshold=threshold,
        )
        
        return severity, threshold

    # ── Event Processing ──────────────────────────────────────────

    async def process_events(
        self, 
        events: list[SeismicEventBase], 
        cycle_id: UUID | None = None
    ) -> dict[str, int]:
        """Process parsed events: check breaches and UPSERT to database.
        
        Args:
            events: List of parsed seismic events.
        
        Returns:
            Dictionary with processing statistics.
        """
        stats = {
            "events_processed": 0,
            "events_upserted": 0,  # total events successfully processed
            "events_inserted": 0,  # new events
            "events_updated": 0,   # existing events updated
            "breaches_detected": 0,
            "errors": 0,
        }
        error_details = {}
        
        for event in events:
            try:
                # Evaluate breach
                if event.magnitude >= 4.0:
                    breach_severity, threshold = self.evaluate_breach(event)
                else:
                    breach_severity, threshold = None, None
                    
                has_breach = breach_severity is not None
                
                event.has_breach = has_breach
                event.breach_severity = breach_severity
                if threshold:
                    event.threshold_id = threshold.threshold_id
                
                # UPSERT event to database
                event_id, was_inserted = await self.seismic_repo.upsert_event(event, cycle_id=cycle_id)
                stats["events_upserted"] += 1
                if was_inserted:
                    stats["events_inserted"] += 1
                else:
                    stats["events_updated"] += 1
                
                # Create breach record if one was detected, linking to the new event_id
                if has_breach and threshold:
                    try:
                        stats["breaches_detected"] += 1
                        await self.breach_service.create_breach(
                            source_api="usgs",
                            disaster_kind="earthquake",
                            metric_name="magnitude",
                            observed_value=event.magnitude,
                            threshold=threshold,
                            severity=breach_severity,
                            observation_time=event.earthquake_time,
                            location_name=event.usgs_place,
                            district=event.resolved_district,
                            province=event.resolved_province,
                            latitude=event.latitude,
                            longitude=event.longitude,
                            seismic_event_id=event_id,
                        )
                    except Exception as breach_e:
                        logger.error(
                            "Failed to create breach for event %s (M%.1f): %s",
                            event.usgs_event_id,
                            event.magnitude,
                            str(breach_e),
                        )
                        # Best effort: don't abort event processing
                        stats["breaches_detected"] -= 1
                
                logger.debug(
                    "Upserted earthquake: %s (M%.1f, %s, breach=%s)",
                    event.usgs_event_id,
                    event.magnitude,
                    event.usgs_place,
                    has_breach,
                )
                
                stats["events_processed"] += 1
                
            except Exception as e:
                error_msg = str(e)
                logger.error(
                    "DB write failed for event %s: %s",
                    event.usgs_event_id,
                    error_msg,
                    exc_info=True,
                )
                stats["errors"] += 1
                error_details[event.usgs_event_id] = error_msg
                continue
        
        logger.info(
            "Processed %d events: %d inserted, %d updated, %d breaches, %d errors",
            stats["events_processed"],
            stats["events_inserted"],
            stats["events_updated"],
            stats["breaches_detected"],
            stats["errors"],
        )
        
        stats["error_details"] = error_details
        return stats
