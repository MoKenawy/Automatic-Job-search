"""Employer blacklist (US3).

Blacklisting is an operator action, not a pipeline stage: it happens once, at
the moment an employer is flagged, and its immediate sweep is scoped to that
one employer. The bulk, whole-corpus sweep that also catches stale blacklists
is `app.pipeline.suppress_stage.run_suppress`, run after every normalisation.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import STATUS_REJECTED, Employer, Posting

log = logging.getLogger(__name__)


class EmployerNotFoundError(ValueError):
    """Raised when the given employer id does not exist."""


def reject_employer_postings(session: Session, employer_id: int) -> int:
    """Reject all not-yet-rejected postings of one employer immediately.

    Does not itself set the suppressed flag — callers do that first — so this
    is also safe to call as a targeted re-sweep.
    """
    now = datetime.now(UTC)
    stmt = select(Posting).where(
        Posting.employer_id == employer_id, Posting.status != STATUS_REJECTED
    )
    count = sum(1 for posting in session.scalars(stmt) if posting.reject_for_suppression(now=now))

    session.commit()
    log.info("suppression: rejected %d posting(s) for employer %d", count, employer_id)
    return count


def blacklist(session: Session, employer_id: int) -> int:
    """Blacklist an employer and immediately reject their postings (US3).

    Rejected postings are retained, never deleted (D9). Returns the number of
    postings newly rejected.
    """
    employer = session.get(Employer, employer_id)
    if employer is None:
        raise EmployerNotFoundError(employer_id)

    employer.blacklist()
    session.commit()
    return reject_employer_postings(session, employer_id)


def lift(session: Session, employer_id: int) -> None:
    """Remove a blacklist.

    Future postings are no longer auto-rejected; previously rejected postings
    are NOT reinstated (US3, FR-011).
    """
    employer = session.get(Employer, employer_id)
    if employer is None:
        raise EmployerNotFoundError(employer_id)

    employer.lift_blacklist()
    session.commit()
