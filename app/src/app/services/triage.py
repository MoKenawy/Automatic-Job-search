"""Posting triage — status transitions (US1, US2).

Extracted from web/app.py route bodies so the same transition logic is
callable from a future CLI command, not only from an HTTP handler. The
validity rule itself (which statuses exist, that Rejected un-publishes) lives
on `Posting.transition_to` — this module is the thin, session-owning wrapper
around it.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import STATUSES, Posting


class UnknownStatusError(ValueError):
    """Raised when `status` is not one of the four known triage states."""


def set_status(
    session: Session, posting_id: int, status: str, *, reason: str | None = None
) -> Posting | None:
    """Transition one posting. Returns None if it does not exist.

    `SELECT ... FOR UPDATE` locks the row for the rest of this transaction,
    so a second, concurrent triage request for the same posting blocks until
    this one commits or rolls back rather than racing it — without the lock,
    two operators clicking different statuses within the same instant could
    each read the same starting `status`, and whichever commits last would
    silently clobber the other's transition and its history row.
    """
    if status not in STATUSES:
        raise UnknownStatusError(status)

    posting = session.scalar(select(Posting).where(Posting.id == posting_id).with_for_update())
    if posting is None:
        return None

    posting.transition_to(status, now=datetime.now(UTC), actor="operator", reason=reason)
    session.commit()
    return posting


def set_status_bulk(session: Session, posting_ids: list[int], status: str) -> int:
    """Apply one status to several postings at once (US2).

    Locks every targeted row up front (ordered by id, avoiding deadlock
    against another bulk update over an overlapping id set) and updates in a
    single transaction so every changed row — and its history entry — is
    committed together, or none are if any step fails. Returns the number of
    postings updated.
    """
    if status not in STATUSES:
        raise UnknownStatusError(status)

    now = datetime.now(UTC)
    stmt = (
        select(Posting)
        .where(Posting.id.in_(posting_ids))
        .order_by(Posting.id)
        .with_for_update()
    )
    updated = 0
    for posting in session.scalars(stmt).all():
        posting.transition_to(status, now=now, actor="operator")
        updated += 1
    session.commit()
    return updated
