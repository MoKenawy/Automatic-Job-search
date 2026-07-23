"""ORM model behaviour — the invariants moved onto Posting/Employer from
web/app.py and pipeline/normalise_stage.py (refactor-plan.md §4.1).
"""

from datetime import UTC, datetime

import pytest

from app.db.models import (
    STATUS_APPLIED,
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_SHORTLIST,
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


def test_posting_is_born_rejected_for_a_suppressed_employer():
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
    assert posting.status == STATUS_REJECTED


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


def test_observe_stamps_last_seen_at():
    posting = Posting(sources={})
    posting.observe(site="indeed", provenance={}, description=None, now=NOW)
    assert posting.last_seen_at == NOW


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


def test_transition_to_stamps_status_changed_at_but_not_last_seen_at():
    """status_changed_at and last_seen_at are separate facts (refactor-plan.md
    §5) — a triage transition must not look like a board re-surfacing."""
    posting = Posting(status=STATUS_NEW, last_seen_at=None)
    posting.transition_to(STATUS_SHORTLIST, now=NOW)
    assert posting.status_changed_at == NOW
    assert posting.last_seen_at is None


# --- Posting.reject_for_suppression — idempotent -----------------------------


def test_reject_for_suppression_changes_a_non_rejected_posting():
    posting = Posting(status=STATUS_NEW, published=True)
    assert posting.reject_for_suppression(now=NOW) is True
    assert posting.status == STATUS_REJECTED
    assert posting.published is False


def test_reject_for_suppression_is_a_noop_when_already_rejected():
    posting = Posting(status=STATUS_REJECTED, published=False, status_changed_at=None)
    assert posting.reject_for_suppression(now=NOW) is False
    assert posting.status_changed_at is None  # untouched — nothing changed


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
