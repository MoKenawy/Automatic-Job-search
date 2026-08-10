"""Suppression sweep (US3) — the bulk pipeline stage.

An operator can blacklist an employer (`employers.suppressed`). Every posting from
a suppressed employer is set to Rejected and un-published, but **retained** — never
deleted (design D9). Rejected already carries the "never resurfaces" guarantee, so
no separate posting flag is needed.

This is the idempotent, whole-corpus pass run after normalisation in `run-all`,
catching any posting a mid-run addition or a stale blacklist might have missed.
The single-employer, blacklist-time sweep lives in `app.services.blacklist`
instead — it is a business operation triggered by an operator action, not a
pipeline stage, and `services/` must not be a dependency of `pipeline/`
(refactor-plan.md §7.2).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import STATUS_REJECTED, Employer, Posting

log = logging.getLogger(__name__)


def run_suppress(session: Session) -> int:
    """Reject all not-yet-rejected postings of every suppressed employer.

    Returns the number of postings newly rejected. Idempotent: a second call over
    unchanged data rejects nothing.
    """
    now = datetime.now(UTC)
    stmt = (
        select(Posting)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(Employer.suppressed.is_(True), Posting.status != STATUS_REJECTED)
    )
    count = sum(1 for posting in session.scalars(stmt) if posting.reject_for_suppression(now=now))

    session.commit()
    if count:
        log.info("suppression: rejected %d posting(s) from blacklisted employers", count)
    return count
