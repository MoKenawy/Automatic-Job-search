"""Per-profile scheduling (US4, ADR-0005).

The design record specified a single cron job at 06:00. After ADR-0005 each
enabled search profile has its own schedule, so the scheduler registers one job
per enabled profile at its configured time. On profile change the jobs are
reloaded. Cron does not exist on the Windows host, so scheduling lives in the app
container (tech stack T2).
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import session_scope
from app.settings_store import profiles

log = logging.getLogger(__name__)


def _register_jobs(scheduler, run_profile_job) -> int:
    """(Re)register one job per enabled profile. Returns the count."""
    scheduler.remove_all_jobs()
    with session_scope() as session:
        enabled = profiles.list_enabled(session)
        specs = [(p.id, p.name, p.schedule_hour, p.schedule_minute) for p in enabled]

    for profile_id, name, hour, minute in specs:
        scheduler.add_job(
            run_profile_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=settings.timezone),
            args=[profile_id],
            id=f"profile-{profile_id}",
            name=f"Search profile: {name}",
            misfire_grace_time=3600,
            max_instances=1,
            coalesce=True,
        )
    log.info("scheduler: registered %d profile job(s)", len(specs))
    return len(specs)


def build_scheduler(run_profile_job) -> BlockingScheduler:
    """Return a scheduler running each enabled profile on its own schedule.

    `run_profile_job` is called with a single argument, the profile id.
    """
    scheduler = BlockingScheduler(timezone=settings.timezone)
    _register_jobs(scheduler, run_profile_job)
    return scheduler
