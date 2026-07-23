"""Posting triage — status transitions (US1, US2).

Extracted from web/app.py route bodies so the same transition logic is
callable from a future CLI command, not only from an HTTP handler. The
validity rule itself (which statuses exist, that Rejected un-publishes) lives
on `Posting.transition_to` — this module is the thin, session-owning wrapper
around it.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import STATUSES, Posting


class UnknownStatusError(ValueError):
    """Raised when `status` is not one of the four known triage states."""


def set_status(session: Session, posting_id: int, status: str) -> Posting | None:
    """Transition one posting. Returns None if it does not exist."""
    if status not in STATUSES:
        raise UnknownStatusError(status)

    posting = session.get(Posting, posting_id)
    if posting is None:
        return None

    posting.transition_to(status, now=datetime.now(UTC))
    session.commit()
    return posting


def set_status_bulk(session: Session, posting_ids: list[int], status: str) -> int:
    """Apply one status to several postings at once (US2).

    Updates in a single transaction so every changed row is reflected
    together. Returns the number of postings updated.
    """
    if status not in STATUSES:
        raise UnknownStatusError(status)

    now = datetime.now(UTC)
    updated = 0
    for posting in session.query(Posting).filter(Posting.id.in_(posting_ids)).all():
        posting.transition_to(status, now=now)
        updated += 1
    session.commit()
    return updated
