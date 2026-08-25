"""The suppression visibility seam (ADR-0015, FR-010).

Suppression is a property of an employer, never stamped on a posting, so
every read of `postings` that must respect the blacklist applies
`not_suppressed()`. If you are writing a query over postings and not using
it, that is a decision to be justified in a comment, not an omission — see
`specs/002-employer-suppression-derived/contracts/read-path-inventory.md`
for the closed set of current queries and their verdicts.
"""

from sqlalchemy import ColumnElement, select

from app.db.models import Employer, Posting


def not_suppressed() -> ColumnElement[bool]:
    """True for postings whose employer is not blacklisted.

    A correlated `NOT EXISTS` over `employers` — composes with any statement
    referencing `Posting`, including ones that select straight from
    `postings` with no join to `Employer` (`totals`, `facets`). It is a
    boolean test, so it can only ever remove rows, never multiply them.
    """
    return ~(
        select(Employer.id)
        .where(Employer.id == Posting.employer_id, Employer.suppressed.is_(True))
        .correlate(Posting)
        .exists()
    )
