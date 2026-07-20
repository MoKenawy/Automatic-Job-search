"""Daily scheduling.

The design record specifies cron at 06:00, but the deployment host is Windows,
where cron does not exist. Scheduling therefore lives inside the app container
(tech stack T2), which keeps it in-language and portable via docker-compose.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

log = logging.getLogger(__name__)


def build_scheduler(job) -> BlockingScheduler:
    """Return a scheduler that runs `job` once daily at the configured time."""
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(
        job,
        trigger=CronTrigger(
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone=settings.timezone,
        ),
        id="daily_pipeline",
        name="Daily job discovery pipeline",
        # A missed window (host asleep, container restarting) should still run
        misfire_grace_time=3600,
        # Never let two runs overlap; a slow run must not be joined by the next
        max_instances=1,
        coalesce=True,
    )
    return scheduler
