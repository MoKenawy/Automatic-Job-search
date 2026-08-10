"""Run orchestration (US4).

One place that opens a run, tracks it to a terminal status, resolves the
effective configuration once, and drives the stages — used by the CLI
(`run-all`), the scheduler (per profile), and the web "run now". Keeps
configuration and run-tracking consistent across all three.

Combines what were previously pipeline/run.py (run tracking) and
pipeline/orchestrate.py (stage sequencing) — the two were never used
independently of one another (refactor-plan.md §7.1).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import RunConfig
from app.db import session_scope
from app.db.models import Run, SearchProfile
from app.pipeline.collect_stage import run_collect
from app.pipeline.normalise_stage import run_normalise
from app.pipeline.suppress_stage import run_suppress
from app.services import profiles

log = logging.getLogger(__name__)


@contextmanager
def track_run(session) -> Iterator[Run]:
    """Open a run record, and close it with a terminal status either way.

    On success the status is 'success'; on exception it is 'failed' with the
    error retained, and the exception re-raised. A run left at 'running' means
    the process died outright, which is itself the signal.
    """
    run = Run(status="running")
    session.add(run)
    session.commit()
    log.info("run %d started", run.id)

    try:
        yield run
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.finished_at = datetime.now(UTC)
        session.commit()
        log.exception("run %d failed", run.id)
        raise
    else:
        run.status = "success"
        run.finished_at = datetime.now(UTC)
        session.commit()
        log.info(
            "run %d finished: collected=%d deduplicated=%d by_site=%s",
            run.id, run.collected_count, run.deduplicated_count, run.counts_by_site,
        )


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
