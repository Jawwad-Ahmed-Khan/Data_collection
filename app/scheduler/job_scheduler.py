"""
ClimaSync Collection Service — Job Scheduler

Manages all scheduled collection and maintenance jobs using APScheduler.

All 7 required jobs:
  1. USGS earthquake collection (every 5m)
  2. Open-Meteo weather collection (every 2h)
  3. Google Flood Hub current readings (every 1h)
  4. Google Flood Hub forecasts (every 6h)
  5. Breach dispatch to main system (every 30s)
  6. Threshold cache reload (every 1h)
  7. Daily cleanup of expired data (00:05 PKT)

Key features:
  - Error isolation: one job failure doesn't stop others
  - Misfire grace time: 30s on all jobs
  - Graceful shutdown: waits up to 30s for running jobs
  - Max instances: prevents job overlap
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class JobScheduler:
    """Manages all scheduled collection and maintenance jobs.
    
    Wraps APScheduler with error isolation and graceful shutdown.
    """

    def __init__(self):
        """Initialize the job scheduler."""
        # Configure scheduler with AsyncIO executor
        executors = {
            "default": AsyncIOExecutor(),
        }
        
        job_defaults = {
            "coalesce": True,  # Combine missed runs into one
            "max_instances": 1,  # Prevent job overlap
            "misfire_grace_time": 30,  # Allow 30s delay before considering missed
        }
        
        self.scheduler = AsyncIOScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone=_PKT,
        )
        
        # Job references (set during add_jobs)
        self.usgs_collector = None
        self.openmeteo_collector = None
        self.floodhub_collector = None
        self.dispatch_service = None
        self.cache_reload_func = None
        self.cleanup_func = None
        
        logger.info("JobScheduler initialized")

    # ── Job Wrappers (Error Isolation) ───────────────────────────

    async def _safe_job_wrapper(
        self,
        job_name: str,
        job_func: Callable,
        *args,
        **kwargs,
    ) -> None:
        """Wrap job execution with error isolation.
        
        Ensures one job failure doesn't crash the scheduler or affect other jobs.
        
        Args:
            job_name: Human-readable job name for logging.
            job_func: Async function to execute.
            *args: Positional arguments for job_func.
            **kwargs: Keyword arguments for job_func.
        """
        try:
            logger.debug("Starting job: %s", job_name)
            result = await job_func(*args, **kwargs)
            logger.debug("Completed job: %s", job_name)
            return result
        except Exception as e:
            logger.error("Job %s failed: %s", job_name, str(e), exc_info=True)
            # Don't re-raise — let other jobs continue

    # ── Job Functions ─────────────────────────────────────────────

    async def _run_usgs_collection(self) -> None:
        """Job 1: USGS earthquake collection."""
        if self.usgs_collector:
            await self._safe_job_wrapper(
                "USGS Collection",
                self.usgs_collector.collect,
            )

    async def _run_weather_collection(self) -> None:
        """Job 2: Open-Meteo weather collection."""
        if self.openmeteo_collector:
            await self._safe_job_wrapper(
                "Weather Collection",
                self.openmeteo_collector.collect,
            )

    async def _run_flood_current(self) -> None:
        """Job 3: Google Flood Hub current readings (every 1h)."""
        if self.floodhub_collector:
            await self._safe_job_wrapper(
                "Flood Hub Current",
                self.floodhub_collector.collect_current,
            )

    async def _run_flood_forecast(self) -> None:
        """Job 4: Google Flood Hub forecasts (every 6h)."""
        if self.floodhub_collector:
            await self._safe_job_wrapper(
                "Flood Hub Forecast",
                self.floodhub_collector.collect_forecast,
            )
    async def _run_breach_dispatch(self) -> None:
        """Job 5: Breach dispatch to main system."""
        if self.dispatch_service:
            await self._safe_job_wrapper(
                "Breach Dispatch",
                self.dispatch_service.run_dispatch_batch,
            )

    async def _run_threshold_reload(self) -> None:
        """Job 6: Reload threshold cache from database."""
        if self.cache_reload_func:
            await self._safe_job_wrapper(
                "Threshold Reload",
                self.cache_reload_func,
            )

    async def _run_daily_cleanup(self) -> None:
        """Job 7: Daily cleanup of expired data."""
        if self.cleanup_func:
            await self._safe_job_wrapper(
                "Daily Cleanup",
                self.cleanup_func,
            )

    # ── Scheduler Management ──────────────────────────────────────

    def add_jobs(
        self,
        usgs_collector=None,
        openmeteo_collector=None,
        floodhub_collector=None,
        dispatch_service=None,
        cache_reload_func=None,
        cleanup_func=None,
    ) -> None:
        """Add all 7 jobs to the scheduler.
        
        Args:
            usgs_collector: USGS collector instance.
            openmeteo_collector: Open-Meteo collector instance.
            floodhub_collector: Flood Hub collector instance.
            dispatch_service: Dispatch service instance.
            cache_reload_func: Function to reload cache from database.
            cleanup_func: Function to clean up expired data.
        """
        # Store references
        self.usgs_collector = usgs_collector
        self.openmeteo_collector = openmeteo_collector
        self.floodhub_collector = floodhub_collector
        self.dispatch_service = dispatch_service
        self.cache_reload_func = cache_reload_func
        self.cleanup_func = cleanup_func
        
        # Job 1: USGS earthquake collection (every 5m)
        if usgs_collector:
            self.scheduler.add_job(
                self._run_usgs_collection,
                trigger=IntervalTrigger(seconds=settings.usgs_poll_interval_seconds),
                id="usgs_collection",
                name="USGS Earthquake Collection",
                replace_existing=True,
                next_run_time=datetime.now(timezone.utc),
            )
            logger.info("✓ Job 1/7: USGS collection (every %ds)", settings.usgs_poll_interval_seconds)
        
        # Job 2: Open-Meteo weather collection (every 2h)
        if openmeteo_collector:
            self.scheduler.add_job(
                self._run_weather_collection,
                trigger=IntervalTrigger(minutes=settings.openmeteo_poll_interval_minutes),
                id="weather_collection",
                name="Open-Meteo Weather Collection",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=60,
                next_run_time=datetime.now(timezone.utc),
            )
            logger.info("✓ Job 2/7: Weather collection (every %dmin)", settings.openmeteo_poll_interval_minutes)
        
        # Job 3: Flood Hub current readings (every 1h)
        if floodhub_collector:
            self.scheduler.add_job(
                self._run_flood_current,
                trigger=IntervalTrigger(minutes=settings.flood_current_interval_minutes),
                next_run_time=datetime.now(timezone.utc),
                id="flood_current",
                name="Flood Hub Current Readings",
                replace_existing=True,
            )
            logger.info("✓ Job 3/7: Flood Hub current (every %dmin)", settings.flood_current_interval_minutes)
        
        # Job 4: Flood Hub forecasts (every 6h)
        if floodhub_collector:
            self.scheduler.add_job(
                self._run_flood_forecast,
                trigger=IntervalTrigger(hours=settings.flood_forecast_interval_hours),
                next_run_time=datetime.now(timezone.utc),
                id="flood_forecast",
                name="Flood Hub Forecasts",
                replace_existing=True,
            )
            logger.info("✓ Job 4/7: Flood Hub forecast (every %dh)", settings.flood_forecast_interval_hours)
        
        # Job 5: Breach dispatch (every 30s)
        if dispatch_service:
            self.scheduler.add_job(
                self._run_breach_dispatch,
                trigger=IntervalTrigger(seconds=settings.breach_dispatch_interval_seconds),
                id="breach_dispatch",
                name="Breach Dispatch",
                replace_existing=True,
            )
            logger.info("✓ Job 5/7: Breach dispatch (every %ds)", settings.breach_dispatch_interval_seconds)
        
        # Job 6: Threshold cache reload (every 1h)
        if cache_reload_func:
            self.scheduler.add_job(
                self._run_threshold_reload,
                trigger=IntervalTrigger(hours=settings.threshold_reload_interval_hours),
                id="threshold_reload",
                name="Threshold Cache Reload",
                replace_existing=True,
            )
            logger.info("✓ Job 6/7: Threshold reload (every %dh)", settings.threshold_reload_interval_hours)
        
        # Job 7: Daily cleanup (00:05 PKT)
        if cleanup_func:
            self.scheduler.add_job(
                self._run_daily_cleanup,
                trigger=CronTrigger(
                    hour=settings.cleanup_hour_pkt,
                    minute=settings.cleanup_minute_pkt,
                    timezone=_PKT,
                ),
                id="daily_cleanup",
                name="Daily Data Cleanup",
                replace_existing=True,
            )
            logger.info(
                "✓ Job 7/7: Daily cleanup (at %02d:%02d PKT)",
                settings.cleanup_hour_pkt,
                settings.cleanup_minute_pkt,
            )

    def start(self) -> None:
        """Start the scheduler.
        
        All jobs will begin executing according to their schedules.
        """
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started — all jobs active")
        else:
            logger.warning("Scheduler already running")

    async def stop(self, wait: bool = True) -> None:
        """Stop the scheduler gracefully.
        
        Args:
            wait: If True, wait for running jobs to complete (up to 30s).
        """
        if self.scheduler.running:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown(wait=wait)
            
            if wait:
                # Give jobs up to 30s to complete
                for i in range(30):
                    if not self.scheduler.running:
                        break
                    await asyncio.sleep(1)
            
            logger.info("Scheduler stopped")
        else:
            logger.warning("Scheduler not running")

    def get_job_status(self) -> dict[str, Any]:
        """Get status of all scheduled jobs.
        
        Returns:
            Dictionary with job information.
        """
        jobs = self.scheduler.get_jobs()
        
        return {
            "scheduler_running": self.scheduler.running,
            "total_jobs": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
                for job in jobs
            ],
        }
