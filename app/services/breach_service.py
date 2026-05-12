"""
ClimaSync Collection Service — Breach Detection Service

Critical service used by ALL three collectors (USGS, Open-Meteo, Flood Hub).
Detects when observed values cross disaster thresholds and creates breach alerts.

Key responsibilities:
  - Priority-based threshold lookup (district > province > national)
  - Season-aware threshold selection
  - Breach level determination (watch/warning/emergency/extreme)
  - Duplicate suppression with metric-specific windows
  - Breach record creation via BreachRepository
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions import BreachDetectionError
from app.core.logger import get_logger
from app.models.breach_models import ThresholdBreachLogBase
from app.models.reference_models import DisasterThreshold
from app.repositories.breach_repository import BreachRepository

logger = get_logger(__name__)

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")

# Metric-specific duplicate suppression windows (minutes)
_SUPPRESSION_WINDOWS = {
    "earthquake": 0,      # Each seismic event is unique by usgs_event_id
    "temperature": 180,   # 3 hours — heatwave persists
    "rainfall": 120,      # 2 hours — rain event developing
    "wind": 60,           # 1 hour — storm passing through
    "cape": 60,           # 1 hour — severe storm building
    "flood_gauge": 60,    # 1 hour — river level updating
}

# Season definitions for Pakistan (month ranges)
_SEASONS = {
    "monsoon": (7, 9),       # July-September
    "pre_monsoon": (4, 6),   # April-June
    "summer": (3, 6),        # March-June
    "winter": (12, 2),       # December-February (wraps year boundary)
}


class BreachService:
    """Detects threshold breaches and creates breach alerts.
    
    Initialized with preloaded thresholds for fast lookup.
    All three collectors (USGS, Open-Meteo, Flood Hub) use this service.
    """

    def __init__(
        self,
        thresholds: list[DisasterThreshold],
        breach_repository: BreachRepository,
    ) -> None:
        """Initialize with preloaded thresholds and breach repository.
        
        Args:
            thresholds: All active disaster thresholds from database.
            breach_repository: Repository for creating breach records.
        """
        self._thresholds = thresholds
        self._breach_repo = breach_repository
        
        # O(1) Lookup cache: (metric_name, disaster_kind, province, district, season) -> DisasterThreshold
        self._cache: dict[tuple[str, str, str | None, str | None, str | None], DisasterThreshold | None] = {}
        
        logger.info("BreachService initialized with %d thresholds", len(thresholds))

    # ── Season Detection ──────────────────────────────────────────

    def _get_current_season(self) -> str | None:
        """Determine current season from PKT date.
        
        Returns:
            Season name ('monsoon', 'pre_monsoon', 'summer', 'winter') or None.
        """
        now_pkt = datetime.now(_PKT)
        month = now_pkt.month

        if month in (7, 8, 9):      return 'monsoon'
        if month in (4, 5, 6):      return 'pre_monsoon'
        if month in (3,):           return 'summer'
        if month in (10, 11):       return None  # post-monsoon
        if month in (12, 1, 2):     return 'winter'

        return None

    # ── Threshold Lookup ──────────────────────────────────────────

    def find_applicable_threshold(
        self,
        metric_name: str,
        disaster_kind: str,
        province: str | None = None,
        district: str | None = None,
    ) -> DisasterThreshold | None:
        """Find the most specific applicable threshold.
        
        Priority order (most specific to least specific):
          1. District + Season
          2. District + Year-round
          3. Province + Season
          4. Province + Year-round
          5. National + Season
          6. National + Year-round
        
        Args:
            metric_name: Metric being checked (e.g., 'temp_max_c', 'magnitude').
            disaster_kind: Type of disaster (e.g., 'heatwave', 'earthquake').
            province: Pakistan province (e.g., 'punjab', 'sindh').
            district: Pakistan district (e.g., 'Lahore', 'Karachi').
        
        Returns:
            Most specific matching threshold, or None if no match found.
        """
        current_season = self._get_current_season()
        cache_key = (metric_name, disaster_kind, province, district, current_season)
        
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build candidate list in priority order
        candidates: list[tuple[int, DisasterThreshold]] = []

        for threshold in self._thresholds:
            # Must match metric and disaster kind
            if threshold.metric_name != metric_name:
                continue
            if threshold.disaster_kind != disaster_kind:
                continue

            # Determine priority score (higher = more specific)
            priority = 0

            # Geographic specificity
            if threshold.district is not None:
                if threshold.district == district:
                    priority += 100  # District match
                else:
                    continue  # District specified but doesn't match
            elif threshold.province is not None:
                if threshold.province == province:
                    priority += 50  # Province match
                else:
                    continue  # Province specified but doesn't match
            else:
                priority += 0  # National default

            # Season specificity
            if threshold.applies_season is not None:
                if threshold.applies_season == current_season:
                    priority += 10  # Season match
                else:
                    continue  # Season specified but doesn't match
            else:
                priority += 0  # Year-round

            candidates.append((priority, threshold))

        if not candidates:
            logger.debug(
                "No threshold found for metric=%s, disaster=%s, province=%s, district=%s, season=%s",
                metric_name, disaster_kind, province, district, current_season,
            )
            self._cache[cache_key] = None
            return None

        # Return highest priority threshold
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = candidates[0][1]

        logger.debug(
            "Selected threshold: metric=%s, disaster=%s, scope=%s/%s, season=%s, priority=%d",
            metric_name, disaster_kind,
            selected.province or "national",
            selected.district or "all",
            selected.applies_season or "year-round",
            candidates[0][0],
        )

        self._cache[cache_key] = selected
        return selected

    # ── Breach Level Detection ────────────────────────────────────

    def check_breach(
        self,
        value: float,
        threshold: DisasterThreshold,
    ) -> Literal["watch", "warning", "emergency", "extreme"] | None:
        """Determine breach severity level by comparing value to threshold.
        
        Args:
            value: Observed or forecasted value.
            threshold: Applicable threshold with watch/warning/emergency/extreme levels.
        
        Returns:
            Breach severity level, or None if no breach.
        """
        direction = threshold.breach_direction

        # Determine which threshold levels are crossed
        levels_crossed = []

        if direction == "above":
            # Value exceeding threshold triggers breach (heat, rain, flood)
            if threshold.extreme_threshold is not None and value >= threshold.extreme_threshold:
                levels_crossed.append(("extreme", threshold.extreme_threshold))
            if threshold.emergency_threshold is not None and value >= threshold.emergency_threshold:
                levels_crossed.append(("emergency", threshold.emergency_threshold))
            if threshold.warning_threshold is not None and value >= threshold.warning_threshold:
                levels_crossed.append(("warning", threshold.warning_threshold))
            if threshold.watch_threshold is not None and value >= threshold.watch_threshold:
                levels_crossed.append(("watch", threshold.watch_threshold))

        elif direction == "below":
            # Value dropping below threshold triggers breach (cold wave, drought)
            if threshold.extreme_threshold is not None and value <= threshold.extreme_threshold:
                levels_crossed.append(("extreme", threshold.extreme_threshold))
            if threshold.emergency_threshold is not None and value <= threshold.emergency_threshold:
                levels_crossed.append(("emergency", threshold.emergency_threshold))
            if threshold.warning_threshold is not None and value <= threshold.warning_threshold:
                levels_crossed.append(("warning", threshold.warning_threshold))
            if threshold.watch_threshold is not None and value <= threshold.watch_threshold:
                levels_crossed.append(("watch", threshold.watch_threshold))

        else:
            raise BreachDetectionError(
                f"Invalid breach_direction: {direction}. Must be 'above' or 'below'."
            )

        if not levels_crossed:
            return None

        # Return the most severe level crossed
        severity_order = ["extreme", "emergency", "warning", "watch"]
        for severity in severity_order:
            if any(level == severity for level, _ in levels_crossed):
                return severity  # type: ignore

        return None

    # ── Duplicate Suppression ─────────────────────────────────────

    async def check_duplicate(
        self,
        location_id: UUID | None,
        metric_name: str,
        metric_category: str,
        seismic_event_id: UUID | None = None,
        severity: str | None = None,
        is_forecast_breach: bool = False,
    ) -> UUID | None:
        """Check if a similar breach was recently created (duplicate suppression).
        
        Args:
            location_id: Location where breach occurred (None for seismic events).
            metric_name: Metric that breached (e.g., 'temp_max_c', 'magnitude').
            metric_category: Category for suppression window lookup
                            ('earthquake', 'temperature', 'rainfall', 'wind', 'flood_gauge').
            seismic_event_id: Event ID for earthquakes.
            severity: Severity level to check escalation for earthquakes.
            is_forecast_breach: Filter for forecast vs current breaches.
        
        Returns:
            UUID of duplicate breach if found, None otherwise.
        """
        # Earthquake events use severity-based deduplication
        if metric_category == "earthquake":
            if seismic_event_id and severity:
                duplicate_breach_id = await self._breach_repo.find_recent_seismic_breach(
                    seismic_event_id, severity
                )
                if duplicate_breach_id:
                    logger.debug(
                        "Duplicate seismic breach suppressed: event_id=%s, severity=%s",
                        seismic_event_id, severity,
                    )
                return duplicate_breach_id
            return None

        suppression_window_mins = _SUPPRESSION_WINDOWS.get(metric_category, 60)

        if suppression_window_mins == 0:
            return None

        # Query recent breaches for this location and metric
        cutoff_time = datetime.now(_PKT) - timedelta(minutes=suppression_window_mins)

        duplicate_breach_id = await self._breach_repo.find_recent_breach(
            location_id=location_id,
            metric_name=metric_name,
            since=cutoff_time,
            is_forecast_breach=is_forecast_breach,
            severity=severity,
        )

        if duplicate_breach_id:
            logger.debug(
                "Duplicate breach suppressed: location=%s, metric=%s, window=%d mins",
                location_id, metric_name, suppression_window_mins,
            )

        return duplicate_breach_id

    # ── Breach Creation ───────────────────────────────────────────

    async def create_breach(
        self,
        source_api: Literal["usgs", "open_meteo", "google_flood_hub"],
        disaster_kind: Literal["earthquake", "flood", "flash_flood", "heatwave", "cyclone", "heavy_rain", "drought", "landslide", "dust_storm", "cold_wave"],
        metric_name: str,
        observed_value: float,
        threshold: DisasterThreshold,
        severity: Literal["watch", "warning", "emergency", "extreme"],
        observation_time: datetime,
        location_name: str | None = None,
        district: str | None = None,
        province: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        weather_location_id: UUID | None = None,
        seismic_event_id: UUID | None = None,
        gauge_id: UUID | None = None,
        is_forecast_breach: bool = False,
        forecast_horizon_h: int | None = None,
    ) -> UUID | None:
        """Create a breach record after detecting a threshold crossing.
        
        Args:
            source_api: Which API detected this breach.
            disaster_kind: Type of disaster.
            metric_name: Which metric breached.
            observed_value: The actual measured/forecasted value.
            threshold: The threshold that was crossed.
            severity: Breach severity level.
            observation_time: When the measurement was taken.
            location_name: Human-readable location name.
            district: Pakistan district.
            province: Pakistan province.
            latitude: Latitude coordinate.
            longitude: Longitude coordinate.
            weather_location_id: Foreign key to pakistan_locations (for weather).
            seismic_event_id: Foreign key to seismic_events (for earthquakes).
            gauge_id: Foreign key to flood_gauge_registry (for floods).
            is_forecast_breach: Whether this is a future forecast breach.
            forecast_horizon_h: Hours until forecasted breach occurs.
        
        Returns:
            UUID of created breach, or None if suppressed as duplicate.
        """
        # Determine metric category for suppression window
        metric_category = self._categorize_metric(metric_name)

        # Check for duplicate
        duplicate_of = await self.check_duplicate(
            location_id=weather_location_id or gauge_id,
            metric_name=metric_name,
            metric_category=metric_category,
            seismic_event_id=seismic_event_id,
            severity=severity,
        )

        # Compute excess amount and percentage
        threshold_value = self._get_threshold_value(threshold, severity)
        excess_amount = abs(observed_value - threshold_value)
        excess_pct = (excess_amount / threshold_value * 100) if threshold_value != 0 else 0

        # Build breach record
        breach = ThresholdBreachLogBase(
            source_api=source_api,
            threshold_id=threshold.threshold_id,
            weather_location_id=weather_location_id,
            seismic_event_id=seismic_event_id,
            gauge_id=gauge_id,
            disaster_kind=disaster_kind,
            metric_name=metric_name,
            location_name=location_name,
            district=district,
            province=province,
            latitude=latitude,
            longitude=longitude,
            observed_value=observed_value,
            threshold_value=threshold_value,
            breach_severity=severity,
            excess_amount=excess_amount,
            excess_pct=excess_pct,
            observation_time=observation_time,
            is_forecast_breach=is_forecast_breach,
            forecast_horizon_h=forecast_horizon_h,
        )

        # Insert breach record
        breach_id = await self._breach_repo.insert_breach(
            breach=breach,
            is_duplicate=duplicate_of is not None,
            duplicate_of_breach_id=duplicate_of,
            suppression_window_used_m=_SUPPRESSION_WINDOWS.get(metric_category, 60),
        )

        if duplicate_of:
            logger.info(
                "Breach suppressed as duplicate: breach_id=%s, duplicate_of=%s",
                breach_id, duplicate_of,
            )
        else:
            if source_api == "open_meteo":
                logger.info(
                    "Weather breach: %s %s=%.2f at %s (forecast=%s, horizon=%dh)",
                    severity, metric_name, observed_value, location_name or "unknown",
                    is_forecast_breach, forecast_horizon_h or 0
                )
            elif disaster_kind == "earthquake":
                logger.info(
                    "Breach detected: %s earthquake M%.1f near %s",
                    severity,
                    observed_value,
                    location_name or "unknown",
                )
            else:
                logger.info(
                    "Breach created: breach_id=%s, severity=%s, metric=%s, value=%.2f, threshold=%.2f",
                    breach_id, severity, metric_name, observed_value, threshold_value,
                )

        return breach_id if not duplicate_of else None

    # ── Helper Methods ────────────────────────────────────────────

    def _categorize_metric(self, metric_name: str) -> str:
        """Determine metric category for suppression window lookup.
        
        Args:
            metric_name: Metric name (e.g., 'temp_max_c', 'magnitude').
        
        Returns:
            Category name ('earthquake', 'temperature', 'rainfall', 'wind', 'flood_gauge').
        """
        if metric_name == "magnitude":
            return "earthquake"
        elif "temp" in metric_name or "feels_like" in metric_name:
            return "temperature"
        elif "precip" in metric_name or "rain" in metric_name:
            return "rainfall"
        elif "wind" in metric_name:
            return "wind"
        elif "cape" in metric_name:
            return "cape"
        elif "gauge" in metric_name or "level" in metric_name or "pct_of" in metric_name:
            return "flood_gauge"
        else:
            # Default to 60 minutes
            return "unknown"

    def _get_threshold_value(
        self,
        threshold: DisasterThreshold,
        severity: Literal["watch", "warning", "emergency", "extreme"],
    ) -> float:
        """Extract the specific threshold value for the given severity level.
        
        Args:
            threshold: Threshold object.
            severity: Severity level.
        
        Returns:
            Threshold value for that severity level.
        
        Raises:
            BreachDetectionError: If threshold value is None for the severity level.
        """
        if severity == "watch":
            value = threshold.watch_threshold
        elif severity == "warning":
            value = threshold.warning_threshold
        elif severity == "emergency":
            value = threshold.emergency_threshold
        elif severity == "extreme":
            value = threshold.extreme_threshold
        else:
            raise BreachDetectionError(f"Invalid severity level: {severity}")

        if value is None:
            raise BreachDetectionError(
                f"Threshold {threshold.threshold_id} has no {severity} level defined"
            )

        return value
