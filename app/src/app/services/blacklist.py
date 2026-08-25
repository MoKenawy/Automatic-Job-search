"""Employer blacklist (ADR-0015).

Blacklisting is an operator action: a single-row flag flip on `employers`.
Suppression is never written to a posting — whether a posting is out of play
because of its employer is answered at read time by
`app.db.visibility.not_suppressed()`, applied by every read path that must
respect the blacklist.
"""

import logging

from sqlalchemy.orm import Session

from app.db.models import Employer

log = logging.getLogger(__name__)


class EmployerNotFoundError(ValueError):
    """Raised when the given employer id does not exist."""


def blacklist(session: Session, employer_id: int) -> None:
    """Blacklist an employer (ADR-0015).

    One row, one commit, atomically visible to every reader through the
    visibility seam. Postings are untouched — suppression is a property of
    the employer, never stamped onto a posting.
    """
    employer = session.get(Employer, employer_id)
    if employer is None:
        raise EmployerNotFoundError(employer_id)

    employer.blacklist()
    session.commit()


def lift(session: Session, employer_id: int) -> None:
    """Remove a blacklist (ADR-0015, FR-012).

    Nothing was overwritten, so nothing needs restoring: the employer's
    postings return to visibility through the seam with their prior triage
    status intact.
    """
    employer = session.get(Employer, employer_id)
    if employer is None:
        raise EmployerNotFoundError(employer_id)

    employer.lift_blacklist()
    session.commit()
