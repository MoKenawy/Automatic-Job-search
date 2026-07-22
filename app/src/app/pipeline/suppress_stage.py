"""Employer blacklist suppression (US3).

An operator can blacklist an employer (`employers.suppressed`). Every posting from
a suppressed employer is set to Rejected and un-published, but **retained** — never
deleted (design D9). Rejected already carries the "never resurfaces" guarantee, so
no separate posting flag is needed.

This runs as an idempotent pass: after normalisation in `run-all`, and immediately
when an employer is blacklisted, so existing postings are caught at once and
mid-run additions are caught on the next pass.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import STATUS_REJECTED, Employer, Posting

log = logging.getLogger(__name__)


def run_suppress(session: Session) -> int:
    """Reject all not-yet-rejected postings of every suppressed employer.

    Returns the number of postings newly rejected. Idempotent: a second call over
    unchanged data rejects nothing.
    """
    stmt = (
        select(Posting)
        .join(Employer, Employer.id == Posting.employer_id)
        .where(Employer.suppressed.is_(True), Posting.status != STATUS_REJECTED)
    )
    count = 0
    for posting in session.scalars(stmt):
        posting.status = STATUS_REJECTED
        posting.published = False
        count += 1

    session.commit()
    if count:
        log.info("suppression: rejected %d posting(s) from blacklisted employers", count)
    return count


def suppress_employer(session: Session, employer_id: int) -> int:
    """Reject all postings of one employer immediately (called on blacklist).

    Does not itself set the suppressed flag — the caller does that first — so this
    is safe to call for a targeted re-sweep.
    """
    stmt = select(Posting).where(
        Posting.employer_id == employer_id, Posting.status != STATUS_REJECTED
    )
    count = 0
    for posting in session.scalars(stmt):
        posting.status = STATUS_REJECTED
        posting.published = False
        count += 1

    session.commit()
    log.info("suppression: rejected %d posting(s) for employer %d", count, employer_id)
    return count
