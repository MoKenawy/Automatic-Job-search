"""Run tracking.

Per-run, per-stage counts are the mechanism by which silent collection decay
becomes visible (design §7.4). The dominant failure is not an exception but a run
that exits successfully while returning progressively less, so a run record is
written even when a stage fails.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import Run

log = logging.getLogger(__name__)


@contextmanager
def track_run(session: Session) -> Iterator[Run]:
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
