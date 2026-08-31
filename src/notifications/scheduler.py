"""
Background Scheduling Service.
Periodically checks for upcoming IPOs, dispatches T-2 alerts and reminders,
and polls for new filings and market sentiment updates.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from src.common.config import settings
from src.common.logging import logger
from src.common.timezone import IST
from src.database.connection import AsyncSessionLocal
from src.discovery.engine import DiscoveryEngine


class SystemScheduler:
    """Manages recurring automated jobs."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=str(IST))

    def setup_jobs(self) -> None:
        """Register periodic discovery and monitoring tasks."""
        # 1. IPO Discovery every 4 hours during market days
        self.scheduler.add_job(
            self._job_discovery,
            trigger=IntervalTrigger(hours=4),
            id="job_ipo_discovery",
            name="Periodic IPO Discovery",
            replace_existing=True,
        )

        # 2. Daily morning alert check at 09:00 IST
        self.scheduler.add_job(
            self._job_morning_alert_check,
            trigger=CronTrigger(hour=9, minute=0, timezone=str(IST)),
            id="job_morning_alerts",
            name="Daily Morning T-2 Alert Dispatch",
            replace_existing=True,
        )

        logger.info("Configured automated scheduler jobs.")

    async def start(self) -> None:
        """Start scheduler."""
        if settings.enable_automated_scheduler:
            self.setup_jobs()
            self.scheduler.start()
            logger.info("System Scheduler started successfully.")

    async def shutdown(self) -> None:
        """Stop scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("System Scheduler shut down.")

    @staticmethod
    async def _job_discovery() -> None:
        logger.info("[CRON] Running scheduled IPO discovery cycle...")
        async with AsyncSessionLocal() as session:
            engine = DiscoveryEngine(session)
            await engine.run_discovery()

    @staticmethod
    async def _job_morning_alert_check() -> None:
        logger.info("[CRON] Running morning T-2 alert dispatch check...")
