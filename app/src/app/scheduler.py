"""Per-profile scheduling (US4, ADR-0005).

The design record specified a single cron job at 06:00. After ADR-0005 each
enabled search profile has its own schedule, so the scheduler registers one job
per enabled profile at its configured time. Cron does not exist on the Windows
host, so scheduling lives in the app container (tech stack T2).

`web` and `scheduler` run as separate containers from one image
(docker-compose.yml), so a profile edited through the UI cannot notify this
process directly — there is no shared memory to signal. Instead a recurring job
polls for a change in `SearchProfile.updated_at` and re-registers when it moves.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import session_scope
from app.services import profiles

log = logging.getLogger(__name__)

_RELOAD_JOB_ID = "__reload_profiles__"
_RELOAD_INTERVAL_MINUTES = 5


def _profile_job_id(profile_id: int) -> str:
    return f"profile-{profile_id}"


def _register_jobs(scheduler, run_profile_job) -> int:
    """(Re)register one job per enabled profile. Returns the count.

    Removes only jobs it owns (`profile-*`), so a caller running this from the
    recurring reload job does not remove that job out from under itself.
    """
    for job in scheduler.get_jobs():
        if job.id.startswith("profile-"):
            scheduler.remove_job(job.id)

    with session_scope() as session:
        enabled = profiles.list_enabled(session)
        specs = [(p.id, p.name, p.schedule_hour, p.schedule_minute) for p in enabled]

    for profile_id, name, hour, minute in specs:
        scheduler.add_job(
            run_profile_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=settings.timezone),
            args=[profile_id],
            id=_profile_job_id(profile_id),
            name=f"Search profile: {name}",
            misfire_grace_time=3600,
            max_instances=1,
            coalesce=True,
        )
    log.info("scheduler: registered %d profile job(s)", len(specs))
    return len(specs)


def _profile_signature(session) -> frozenset[tuple[int, str]]:
    """A value that changes whenever an enabled profile's schedule or
    membership changes — cheap to compare, no separate 'last checked' state."""
    return frozenset(
        (p.id, p.updated_at.isoformat()) for p in profiles.list_enabled(session)
    )


def build_scheduler(
    run_profile_job, reload_interval_minutes: int = _RELOAD_INTERVAL_MINUTES
) -> BlockingScheduler:
    """Return a scheduler running each enabled profile on its own schedule.

    `run_profile_job` is called with a single argument, the profile id. A
    recurring job polls every `reload_interval_minutes` and re-registers the
    profile jobs when a schedule, an enabled flag, or profile membership has
    changed since the last check (see module docstring).
    """
    scheduler = BlockingScheduler(timezone=settings.timezone)
    state: dict[str, frozenset] = {}

    def _reload_if_changed() -> None:
        with session_scope() as session:
            signature = _profile_signature(session)
        if signature != state.get("signature"):
            state["signature"] = signature
            _register_jobs(scheduler, run_profile_job)

    _reload_if_changed()
    scheduler.add_job(
        _reload_if_changed,
        trigger="interval",
        minutes=reload_interval_minutes,
        id=_RELOAD_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
