"""The visibility seam — two reasons a posting may be withheld.

Suppression is a property of an employer, never stamped on a posting, so
every read of `postings` that must respect the blacklist applies
`not_suppressed()`. If you are writing a query over postings and not using
it, that is a decision to be justified in a comment, not an omission — see
`specs/002-employer-suppression-derived/contracts/read-path-inventory.md`
for the closed set of current queries and their verdicts.

A filter verdict is a statement about criteria, never about the operator's
judgement, so every read of `postings` that must respect the filter applies
`~hidden_by_filter()` (ADR-0016). The same obligation, in the same words, for
the same reason: an unexamined read path is the failure mode, and an examined
one that declines the predicate is a decision.

The two predicates here answer different questions and are not
interchangeable. `filter_rejected()` is the verdict — did a criterion turn this
posting away? `hidden_by_filter()` is the consequence — is the filter
withholding it *now*? The difference is a triage term, and
`specs/003-collect-stage-filtering/contracts/filter-seam.md` records why the
review bucket is built on the first and the read paths on the second.
"""

from sqlalchemy import ColumnElement, select

from app.db.models import STATUS_NEW, Employer, Posting


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


def filter_rejected() -> ColumnElement[bool]:
    """True for postings a filter criterion turned away (ADR-0016, FR-016).

    The verdict alone, with no reference to triage state — so it still answers
    for a posting the operator has since shortlisted, which is exactly the case
    FR-017 needs it to answer for.

    **`.is_(False)`, never `== False`.** Every verdict is NULL until the filter
    has run, and NULL is the normal steady state when no criteria are set. Under
    three-valued logic `NOT (NULL = FALSE)` is NULL, and a row whose WHERE clause
    evaluates to NULL is not selected — so the obvious spelling of the negation
    would hide the **entire corpus**, while a suite that only asserts absences
    stays green. 002's contract names that failure for the other predicate; this
    is the same trap one column to the left.

    `IS FALSE` on a plain Boolean compiles identically under SQLite and
    PostgreSQL, so no dialect split is needed here — unlike `queries._has_source`,
    which needed one for JSON. That contrast is the concrete argument for having
    promoted `job_level` to a column at all.
    """
    return Posting.title_filter_passed.is_(False) | Posting.experience_filter_passed.is_(False)


def hidden_by_filter() -> ColumnElement[bool]:
    """True for postings the filter is withholding from the operator's views.

    A rejected posting **that the operator has not triaged**. The status term is
    the whole difference from `filter_rejected()`, and it is a requirement rather
    than a nicety: a posting already shortlisted or applied to must not be
    removed from view by a later tightening of the criteria (spec 003, edge
    cases). Triage is the operator's own judgement, and a criteria change must
    not reach back and withdraw something they have acted on.

    Measured on the live corpus when the filter first ran: 10 of its 14
    rejections were already triaged, so this term is load-bearing rather than
    defensive.

    A plain boolean expression over `postings` columns — no join, no subquery —
    so it composes with statements that never reach `employers` (`totals`,
    `facets`) and cannot change a row count on its own. Correctness does not
    depend on any index.
    """
    return filter_rejected() & (Posting.status == STATUS_NEW)
