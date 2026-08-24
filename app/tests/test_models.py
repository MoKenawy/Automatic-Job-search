"""ORM model behaviour — the invariants moved onto Posting/Employer from
web/app.py and pipeline/normalise_stage.py (refactor-plan.md §4.1).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
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

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def _employer(suppressed=False) -> Employer:
    e = Employer(name="Acme", normalised_name="acme", suppressed=suppressed)
    e.id = 1  # normally assigned by the DB; set directly for unit-level tests
    return e


# --- Posting.create — born-rejected rule (FR-007) ---------------------------


def test_posting_is_born_new_for_an_unsuppressed_employer():
    posting = Posting.create(
        fingerprint="f" * 64,
        employer=_employer(suppressed=False),
        title="Data Engineer",
        normalised_title="data engineer",
        location_raw="Cairo, Egypt",
        country_code="EG",
        is_remote=False,
        description=None,
        date_posted=None,
        job_type=None,
        site="linkedin",
        provenance={"url": "https://x", "job_id": "1", "first_seen": NOW.isoformat()},
    )
    assert posting.status == STATUS_NEW


def test_posting_is_born_new_for_a_suppressed_employer():
    """Born `new` even under a suppressed employer (ADR-0015) — visibility is
    derived at read time, never stamped at creation."""
    posting = Posting.create(
        fingerprint="f" * 64,
        employer=_employer(suppressed=True),
        title="Data Engineer",
        normalised_title="data engineer",
        location_raw=None,
        country_code=None,
        is_remote=False,
        description=None,
        date_posted=None,
        job_type=None,
        site="linkedin",
        provenance={"url": "https://x", "job_id": "1", "first_seen": NOW.isoformat()},
    )
    assert posting.status == STATUS_NEW


def test_create_truncates_title_and_normalised_title_to_column_width():
    posting = Posting.create(
        fingerprint="f" * 64,
        employer=_employer(),
        title="x" * 600,
        normalised_title="y" * 600,
        location_raw=None,
        country_code=None,
        is_remote=False,
        description=None,
        date_posted=None,
        job_type=None,
        site="linkedin",
        provenance={},
    )
    assert len(posting.title) == 512
    assert len(posting.normalised_title) == 512


# --- Posting.observe — merge provenance, backfill description ---------------


def test_observe_adds_a_new_source_without_disturbing_existing_ones():
    posting = Posting(sources={"linkedin": {"url": "https://old", "job_id": "1"}})
    posting.observe(
        site="indeed",
        provenance={"url": "https://new", "job_id": "2", "first_seen": NOW.isoformat()},
        description=None,
        now=NOW,
    )
    assert set(posting.sources) == {"linkedin", "indeed"}
    assert posting.sources["linkedin"]["url"] == "https://old"  # untouched


def test_observe_updates_the_url_for_an_already_seen_source():
    posting = Posting(sources={"linkedin": {"url": "https://old", "job_id": "1"}})
    posting.observe(
        site="linkedin",
        provenance={"url": "https://new", "job_id": "1", "first_seen": NOW.isoformat()},
        description=None,
        now=NOW,
    )
    assert posting.sources["linkedin"]["url"] == "https://new"


def test_observe_stamps_last_retrieved_at():
    posting = Posting(sources={})
    posting.observe(site="indeed", provenance={}, description=None, now=NOW)
    assert posting.last_retrieved_at == NOW


def test_observe_backfills_a_missing_description():
    posting = Posting(sources={}, description=None)
    posting.observe(site="indeed", provenance={}, description="a role", now=NOW)
    assert posting.description == "a role"


def test_observe_never_overwrites_an_existing_description():
    posting = Posting(sources={}, description="original")
    posting.observe(site="indeed", provenance={}, description="from another board", now=NOW)
    assert posting.description == "original"


# --- Posting.transition_to — any status to any other (confirmed, non-terminal) --


@pytest.mark.parametrize(
    "start,target",
    [
        (STATUS_NEW, STATUS_SHORTLIST),
        (STATUS_SHORTLIST, STATUS_APPLIED),
        (STATUS_APPLIED, STATUS_REJECTED),
        (STATUS_REJECTED, STATUS_NEW),  # Rejected is explicitly NOT terminal
        (STATUS_REJECTED, STATUS_SHORTLIST),
    ],
)
def test_transition_to_allows_any_status_to_any_other(start, target):
    posting = Posting(status=start, published=(start != STATUS_REJECTED))
    posting.transition_to(target, now=NOW)
    assert posting.status == target


def test_transition_to_rejects_an_unknown_status():
    posting = Posting(status=STATUS_NEW)
    with pytest.raises(ValueError, match="unknown status"):
        posting.transition_to("banana", now=NOW)


def test_transition_to_rejected_unpublishes():
    posting = Posting(status=STATUS_NEW, published=True)
    posting.transition_to(STATUS_REJECTED, now=NOW)
    assert posting.published is False


def test_transition_to_stamps_status_changed_at_but_not_last_retrieved_at():
    """status_changed_at and last_retrieved_at are separate facts (ADR-0012)
    — a triage transition must not look like a board re-surfacing."""
    posting = Posting(status=STATUS_NEW, last_retrieved_at=None)
    posting.transition_to(STATUS_SHORTLIST, now=NOW)
    assert posting.status_changed_at == NOW
    assert posting.last_retrieved_at is None


# --- Posting.transition_to — history recording -------------------------------


def test_transition_to_appends_a_history_row():
    posting = Posting(status=STATUS_NEW, published=True)
    posting.transition_to(STATUS_SHORTLIST, now=NOW, actor="operator")
    assert len(posting.status_history) == 1
    entry = posting.status_history[0]
    assert entry.previous_status == STATUS_NEW
    assert entry.new_status == STATUS_SHORTLIST
    assert entry.changed_at == NOW
    assert entry.actor == "operator"
    assert entry.reason is None


def test_transition_to_records_a_reason_when_given():
    posting = Posting(status=STATUS_NEW)
    posting.transition_to(STATUS_REJECTED, now=NOW, actor="operator", reason="not a fit")
    assert posting.status_history[-1].reason == "not a fit"


def test_transition_to_appends_history_even_on_a_rejected_unknown_status_is_not_recorded():
    """An unknown status raises before mutating anything — no partial history."""
    posting = Posting(status=STATUS_NEW)
    with pytest.raises(ValueError):
        posting.transition_to("banana", now=NOW)
    assert posting.status_history == []


def test_multiple_transitions_accumulate_history_in_order():
    posting = Posting(status=STATUS_NEW)
    posting.transition_to(STATUS_SHORTLIST, now=NOW)
    posting.transition_to(STATUS_APPLIED, now=NOW)
    assert [h.new_status for h in posting.status_history] == [STATUS_SHORTLIST, STATUS_APPLIED]
    assert posting.status_history[1].previous_status == STATUS_SHORTLIST


# --- Employer.enrich_from / blacklist / lift_blacklist -----------------------


def test_enrich_from_fills_a_gap():
    employer = Employer(name="Acme", normalised_name="acme")
    employer.enrich_from({"company_url": "https://acme.example"})
    assert employer.url == "https://acme.example"


def test_enrich_from_never_overwrites_a_value_already_held():
    employer = Employer(name="Acme", normalised_name="acme", url="https://original")
    employer.enrich_from({"company_url": "https://from-another-board"})
    assert employer.url == "https://original"


def test_blacklist_and_lift_toggle_suppressed():
    employer = Employer(name="Acme", normalised_name="acme", suppressed=False)
    employer.blacklist()
    assert employer.suppressed is True
    employer.lift_blacklist()
    assert employer.suppressed is False


# --- last_retrieved_at vs. updated_at, at the ORM layer (ADR-0012) ----------
#
# Two columns, deliberately kept apart: `last_retrieved_at` means "a board
# last confirmed this posting exists" and is written only by `observe()`;
# `updated_at` means "this row was last written to, for any reason" and is
# generic bookkeeping, same as SearchProfile.updated_at / AppSetting.updated_at.
# A column `onupdate` fires when SQLAlchemy emits the UPDATE, not when a
# Python attribute is merely mutated, so a detached `Posting()` never
# triggers it — only a flush reveals whether a column actually moves.

# Naive on purpose: SQLite has no native datetime, so DateTime(timezone=True)
# round-trips without a tzinfo and a tz-aware constant would never compare equal.
OBSERVED = datetime(2020, 1, 1)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s


def test_transition_does_not_advance_last_retrieved_at_through_a_flush(session):
    """A triage transition is not an observation and must not look like one
    (ADR-0012) — only `observe()` may move `last_retrieved_at`."""
    employer = Employer(name="Acme", normalised_name="acme")
    session.add(employer)
    session.flush()

    posting = Posting(
        fingerprint="f" * 64,
        employer_id=employer.id,
        title="Data Engineer",
        normalised_title="data engineer",
        sources={},
        first_seen_at=OBSERVED,
        last_retrieved_at=OBSERVED,
    )
    session.add(posting)
    session.commit()

    posting.transition_to(STATUS_SHORTLIST, now=NOW)
    session.commit()
    session.refresh(posting)

    assert posting.last_retrieved_at == OBSERVED


def test_transition_advances_updated_at_through_a_flush(session):
    """The opposite invariant, on the other column: `updated_at` is generic
    row-modified bookkeeping and is *supposed* to move on any write, a
    triage transition included — restored deliberately (ADR-0012) after this
    session's first pass mistakenly stripped it from the (then only) column
    doing both jobs at once."""
    employer = Employer(name="Acme", normalised_name="acme")
    session.add(employer)
    session.flush()

    posting = Posting(
        fingerprint="f" * 64,
        employer_id=employer.id,
        title="Data Engineer",
        normalised_title="data engineer",
        sources={},
        first_seen_at=OBSERVED,
        updated_at=OBSERVED,
    )
    session.add(posting)
    session.commit()

    posting.transition_to(STATUS_SHORTLIST, now=NOW)
    session.commit()
    session.refresh(posting)

    assert posting.updated_at != OBSERVED


def test_observe_advances_last_retrieved_at_through_a_flush(session):
    """The other half of the `last_retrieved_at` invariant: a real
    re-observation *must* move it, so the fix above cannot be 'never write
    the column'."""
    employer = Employer(name="Acme", normalised_name="acme")
    session.add(employer)
    session.flush()

    posting = Posting(
        fingerprint="f" * 64,
        employer_id=employer.id,
        title="Data Engineer",
        normalised_title="data engineer",
        sources={},
        first_seen_at=OBSERVED,
        last_retrieved_at=OBSERVED,
    )
    session.add(posting)
    session.commit()

    posting.observe(
        site="indeed",
        provenance={"url": "https://x", "job_id": "1"},
        description=None,
        now=datetime(2026, 7, 27, 9, 0),
    )
    session.commit()
    session.refresh(posting)

    assert posting.last_retrieved_at == datetime(2026, 7, 27, 9, 0)
