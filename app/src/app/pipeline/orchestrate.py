"""Run orchestration (US4).

One place that opens a run, resolves the effective configuration once, and
drives the stages — used by the CLI (`run-all`), the scheduler (per profile),
and the web "run now". Keeps configuration and run-tracking consistent across
all three.
"""

import logging

from app.config import RunConfig
from app.db import session_scope
from app.db.models import SearchProfile
from app.pipeline.collect_stage import run_collect
from app.pipeline.normalise_stage import run_normalise
from app.pipeline.run import track_run
from app.pipeline.suppress_stage import run_suppress
from app.settings_store import profiles

log = logging.getLogger(__name__)


def _run(session, run, specs) -> dict:
    """Drive the stages for a set of specs against an open run.

    `config` is resolved once here — a frozen snapshot for the whole run,
    rather than the previous `apply_to_settings()` overlay onto the process-wide
    `Settings` singleton (refactor-plan.md §3). Two runs can now hold different
    configurations, and nothing here mutates global state.
    """
    config = RunConfig.resolve(session)
    collected = run_collect(session, run, specs, config)
    raw_count, distinct = run_normalise(session, run)
    suppressed = run_suppress(session)
    return {
        "run_id": run.id,
        "collected": collected,
        "raw": raw_count,
        "distinct": distinct,
        "suppressed": suppressed,
    }


def run_all_profiles() -> dict:
    """Run every enabled profile's searches in a single run (manual `run-all`)."""
    with session_scope() as session, track_run(session) as run:
        specs = profiles.enabled_specs(session) or None
        return _run(session, run, specs)


def run_one_profile(profile_id: int) -> dict:
    """Run a single profile's search (scheduler tick / web run-now).

    The run is tagged with the profile id for attribution (§7.4 preserved).
    """
    with session_scope() as session, track_run(session) as run:
        profile = session.get(SearchProfile, profile_id)
        if profile is None:
            raise ValueError(f"profile {profile_id} not found")
        run.profile_id = profile_id
        specs = [profiles.to_spec(profile)]
        result = _run(session, run, specs)
        log.info("profile %r run complete: %s", profile.name, result)
        return result
