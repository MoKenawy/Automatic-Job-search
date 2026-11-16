"""The visibility seam in isolation (ADR-0015, ADR-0016).

Two predicates live in one module, so their tests do too: a developer who finds
one is guaranteed to find the other.

**Suppression** (ADR-0015, contracts/visibility-seam.md). Three cases: a normal
employer's posting is selected; a suppressed employer's posting is rejected; and
— the keystone — a suppressed employer's posting whose `status` is still `new` is
rejected too. That last case is the assertion that feature exists to make true:
under the old materialised model, "suppressed but still new" was a state the
system could not represent.

**The filter** (ADR-0016, 003/contracts/filter-seam.md). Its own keystone is the
NULL-verdict posting, because that is the case a predicate written `== False`
gets catastrophically wrong: under three-valued logic the negation evaluates to
NULL, the row is not selected, and the entire corpus vanishes while a suite that
only asserts absences stays green. Every test below is therefore two-sided — a
withheld posting absent **and** a visible one present — over a corpus holding
NULL, True and False verdicts against all four triage statuses.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    STATUS_APPLIED,
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_SHORTLIST,
    Base,
    Employer,
    Posting,
)
from app.db.visibility import filter_rejected, hidden_by_filter, not_suppressed


def _factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _posting(session, employer, name, status=STATUS_NEW, *, title_ok=None, experience_ok=None):
    posting = Posting(
        fingerprint=name.ljust(64, "0")[:64],
        employer_id=employer.id,
        title=name,
        normalised_title=name.lower(),
        sources={"linkedin": {"url": "https://x"}},
        status=status,
        title_filter_passed=title_ok,
        experience_filter_passed=experience_ok,
    )
    session.add(posting)
    session.commit()
    return posting


def _employer(session, name="Acme", suppressed=False):
    employer = Employer(name=name, normalised_name=name.lower(), suppressed=suppressed)
    session.add(employer)
    session.flush()
    return employer


# --- the filter predicates (ADR-0016) ---------------------------------------


def test_a_posting_with_no_verdict_is_visible():
    """The keystone, and the one a careless predicate gets catastrophically
    wrong. Every posting is in this state until the filter has run, and it stays
    in it for as long as no criteria are set (SC-006) — so a predicate written
    `== False` would hide the whole corpus."""
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        posting = _posting(s, employer, "Unjudged")

        assert posting in s.scalars(select(Posting).where(~hidden_by_filter())).all()
        assert s.scalars(select(Posting).where(hidden_by_filter())).all() == []


def test_an_admitted_posting_is_visible():
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        posting = _posting(s, employer, "Admitted", title_ok=True, experience_ok=True)

        assert posting in s.scalars(select(Posting).where(~hidden_by_filter())).all()


def test_a_posting_rejected_on_title_grounds_is_withheld():
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        withheld = _posting(s, employer, "QA Analyst", title_ok=False)
        visible = _posting(s, employer, "Web Developer", title_ok=True)

        rows = s.scalars(select(Posting).where(~hidden_by_filter())).all()
        assert withheld not in rows
        assert visible in rows


def test_a_posting_rejected_on_experience_grounds_is_withheld():
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        withheld = _posting(s, employer, "Director", experience_ok=False)
        visible = _posting(s, employer, "Graduate", experience_ok=True)

        rows = s.scalars(select(Posting).where(~hidden_by_filter())).all()
        assert withheld not in rows
        assert visible in rows


@pytest.mark.parametrize("status", [STATUS_SHORTLIST, STATUS_APPLIED, STATUS_REJECTED])
def test_a_triaged_posting_is_never_withheld_however_it_was_judged(status):
    """The spec's edge case, and the whole reason `hidden_by_filter()` carries a
    status term: a tightening of the criteria must not reach back and withdraw a
    posting the operator has already acted on. Measured on the live corpus, 10 of
    the filter's first 14 rejections were in this state."""
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        posting = _posting(s, employer, "Director", status, experience_ok=False)

        assert posting in s.scalars(select(Posting).where(~hidden_by_filter())).all()


def test_the_verdict_still_answers_for_a_triaged_posting():
    """`filter_rejected()` has no status term, which is what lets the review
    bucket show a posting rejected *after* the operator shortlisted it — the
    clearest evidence a criterion is too aggressive (FR-017, SC-002)."""
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        shortlisted = _posting(s, employer, "Director", STATUS_SHORTLIST, experience_ok=False)
        untriaged = _posting(s, employer, "Executive", STATUS_NEW, experience_ok=False)
        admitted = _posting(s, employer, "Graduate", STATUS_NEW, experience_ok=True)

        rows = s.scalars(select(Posting).where(filter_rejected())).all()
        assert shortlisted in rows
        assert untriaged in rows
        assert admitted not in rows


def test_hidden_and_visible_partition_the_corpus():
    """Every (verdict x status) combination, counted once. The bucket and the
    hide rule are deliberately different sets, so they can drift apart silently;
    this is what would catch it."""
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        statuses = (STATUS_NEW, STATUS_SHORTLIST, STATUS_APPLIED, STATUS_REJECTED)
        verdicts = (None, True, False)
        for status in statuses:
            for title_ok in verdicts:
                for experience_ok in verdicts:
                    _posting(
                        s,
                        employer,
                        f"{status}-{title_ok}-{experience_ok}",
                        status,
                        title_ok=title_ok,
                        experience_ok=experience_ok,
                    )

        total = len(s.scalars(select(Posting)).all())
        hidden = len(s.scalars(select(Posting).where(hidden_by_filter())).all())
        visible = len(s.scalars(select(Posting).where(~hidden_by_filter())).all())
        rejected = len(s.scalars(select(Posting).where(filter_rejected())).all())

        assert total == len(statuses) * len(verdicts) * len(verdicts)
        assert hidden + visible == total

        # The overlap, named rather than left to be rediscovered: of the five
        # rejected combinations per status, all five are rejected but only the
        # `new` ones are hidden. The other three statuses' rejections appear in
        # both the normal list and the review bucket.
        assert rejected == 5 * len(statuses)
        assert hidden == 5
        assert rejected - hidden == 5 * (len(statuses) - 1)


def test_withholding_is_not_deletion():
    """No invisibility assertion can tell "withheld" from "gone", so the row's
    survival — with its triage status intact — needs its own test (FR-013,
    FR-014)."""
    factory = _factory()
    with factory() as s:
        employer = _employer(s)
        posting = _posting(s, employer, "Director", STATUS_SHORTLIST, experience_ok=False)
        posting_id = posting.id

        assert s.scalars(select(Posting).where(hidden_by_filter())).all() == []
        survivor = s.get(Posting, posting_id)
        assert survivor is not None
        assert survivor.status == STATUS_SHORTLIST
        assert survivor.experience_filter_passed is False


def test_the_two_seams_are_independent():
    """Suppression and the filter are separate reasons to withhold, so each must
    withhold on its own. A read path that applies only one is still wrong, which
    is why `queries._visible()` returns them as a pair."""
    factory = _factory()
    with factory() as s:
        clean = _employer(s, "Clean")
        blacklisted = _employer(s, "Spammer", suppressed=True)

        filtered_only = _posting(s, clean, "Director", experience_ok=False)
        suppressed_only = _posting(s, blacklisted, "Blacklisted Graduate", experience_ok=True)
        fine = _posting(s, clean, "Clean Graduate", experience_ok=True)

        rows = s.scalars(select(Posting).where(not_suppressed(), ~hidden_by_filter())).all()
        assert fine in rows
        assert filtered_only not in rows
        assert suppressed_only not in rows


def test_normal_employers_posting_is_selected():
    factory = _factory()
    with factory() as s:
        emp = Employer(name="Good", normalised_name="good", suppressed=False)
        s.add(emp)
        s.flush()
        posting = _posting(s, emp, "Role")

        rows = s.scalars(select(Posting).where(not_suppressed())).all()
        assert posting in rows


def test_suppressed_employers_posting_is_rejected():
    factory = _factory()
    with factory() as s:
        emp = Employer(name="Spammer", normalised_name="spammer", suppressed=True)
        s.add(emp)
        s.flush()
        _posting(s, emp, "Role")

        rows = s.scalars(select(Posting).where(not_suppressed())).all()
        assert rows == []


def test_suppressed_employers_new_posting_is_rejected():
    """The keystone case: suppressed but status is still `new`."""
    factory = _factory()
    with factory() as s:
        emp = Employer(name="Spammer", normalised_name="spammer", suppressed=True)
        s.add(emp)
        s.flush()
        _posting(s, emp, "Role", status=STATUS_NEW)

        rows = s.scalars(select(Posting).where(not_suppressed())).all()
        assert rows == []
