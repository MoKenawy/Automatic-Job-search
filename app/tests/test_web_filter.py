"""The filter through the web surfaces (ADR-0016, FR-013/FR-016/FR-017).

What the operator can actually see: the queue without the postings the filter
withheld, the review bucket with them, and a detail page that still reaches a
withheld posting and names the criterion that withheld it.

Two-sided throughout — an admitted posting must be present in every assertion
that a withheld one is absent — because a predicate that hides everything would
satisfy absence-only tests. Same in-memory SQLite pattern as the other web tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    STATUS_NEW,
    STATUS_SHORTLIST,
    Base,
    Employer,
    Posting,
    Run,
)
from app.web.app import app, get_db

# The corpus every test in this module reads. One posting per interesting
# (verdict x status) combination, named so a failure says which one.
ADMITTED = "Admitted Engineer"
WITHHELD = "Withheld Director"
TRIAGED_REJECTED = "Shortlisted Director"
UNJUDGED = "Unjudged Analyst"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with factory() as seed:
        employer = Employer(name="Acme", normalised_name="acme")
        seed.add(employer)
        seed.flush()

        rows = [
            # title, status, title_ok, experience_ok, job_level
            (ADMITTED, STATUS_NEW, True, True, "entry level"),
            (WITHHELD, STATUS_NEW, True, False, "director"),
            (TRIAGED_REJECTED, STATUS_SHORTLIST, True, False, "director"),
            # Never filtered: the state every posting is in until the stage runs,
            # and the one a careless predicate would hide (ADR-0016).
            (UNJUDGED, STATUS_NEW, None, None, None),
        ]
        for i, (title, status, title_ok, experience_ok, job_level) in enumerate(rows):
            seed.add(
                Posting(
                    fingerprint=chr(97 + i) * 64,
                    employer_id=employer.id,
                    title=title,
                    normalised_title=title.lower(),
                    sources={"linkedin": {"url": "https://x"}},
                    score=90 - i,
                    status=status,
                    title_filter_passed=title_ok,
                    experience_filter_passed=experience_ok,
                    job_level=job_level,
                )
            )
        seed.commit()

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _posting_id(client: TestClient, title: str) -> int:
    """The id of a seeded posting, read the way the operator would reach it."""
    body = client.get("/postings?verdict=rejected").text
    if title not in body:
        body = client.get("/postings").text
    marker = "/postings/"
    for chunk in body.split(marker)[1:]:
        ident, _, rest = chunk.partition('"')
        if title in rest.split("</a>")[0]:
            return int(ident)
    raise AssertionError(f"{title} not found in either listing")


# --- the queue --------------------------------------------------------------


def test_the_queue_omits_a_withheld_posting(client):
    body = client.get("/postings").text
    assert WITHHELD not in body
    assert ADMITTED in body


def test_the_queue_keeps_a_posting_with_no_verdict(client):
    """The keystone, at the level the operator sees. Every posting is in this
    state before the filter runs and stays in it while no criteria are set, so
    a predicate written `== False` would empty the queue (SC-006)."""
    assert UNJUDGED in client.get("/postings").text


def test_the_queue_keeps_a_rejected_posting_the_operator_has_triaged(client):
    """A criteria change must not withdraw the operator's own judgement."""
    assert TRIAGED_REJECTED in client.get("/postings").text


def test_the_totals_count_what_the_queue_shows(client):
    """The figures over `postings` carry the same predicates as the listing, or
    the dashboard describes a queue the operator does not have."""
    body = client.get("/").text
    # 4 seeded, 1 withheld.
    assert ">3<" in body


# --- the review bucket (FR-017) --------------------------------------------


def test_the_bucket_contains_what_the_filter_turned_away(client):
    body = client.get("/postings?verdict=rejected").text
    assert WITHHELD in body
    assert ADMITTED not in body
    assert UNJUDGED not in body


def test_the_bucket_also_contains_a_rejected_posting_already_triaged(client):
    """Deliberately not the complement of the hide rule: a posting rejected
    after the operator shortlisted it is the clearest evidence a criterion is
    too aggressive, and a bucket of "everything hidden" would conceal it
    (SC-002, contracts/filter-seam.md)."""
    assert TRIAGED_REJECTED in client.get("/postings?verdict=rejected").text


def test_the_bucket_names_the_criterion(client):
    """SC-005 — one interaction to see that the filter withheld it and why."""
    body = client.get("/postings?verdict=rejected").text
    assert "Turned away on" in body
    assert "experience" in body


def test_the_bucket_survives_paging(client):
    """The bucket is part of the active filter state, so a pager link stays in
    it. Omit it from `active` and page 2 of "filtered out" is page 2 of
    everything."""
    body = client.get("/postings?verdict=rejected&page=1").text
    assert WITHHELD in body
    assert ADMITTED not in body


def test_a_bulk_action_from_the_bucket_lands_back_in_the_bucket(client):
    """The bulk form echoes the list state back; the bucket has to be part of
    that echo or the operator is bounced to the unfiltered list."""
    posting_id = _posting_id(client, WITHHELD)
    response = client.post(
        "/postings/status",
        data={"ids": [posting_id], "status": STATUS_SHORTLIST, "verdict": "rejected"},
    )
    assert response.status_code == 200
    # Still the bucket: the posting is rejected, so it stays listed even though
    # it has just been triaged.
    assert "Turned away on" in response.text
    assert WITHHELD in response.text


# --- the detail page (FR-013, FR-016) --------------------------------------


def test_a_withheld_posting_is_still_reachable(client):
    """The deliberate opt-out from the seam: this is the one page where a
    withheld posting can be read at all."""
    posting_id = _posting_id(client, WITHHELD)
    response = client.get(f"/postings/{posting_id}")
    assert response.status_code == 200
    assert WITHHELD in response.text


def test_the_detail_page_says_the_filter_withheld_it_and_why(client):
    posting_id = _posting_id(client, WITHHELD)
    body = client.get(f"/postings/{posting_id}").text
    assert "filtered out" in body
    assert "experience" in body
    assert "director" in body  # the board's label, which is why it was rejected
    assert "withheld from the queue" in body


def test_the_detail_page_of_a_triaged_rejection_says_it_is_still_visible(client):
    """The operator needs to know the difference between "we are hiding this"
    and "this would be hidden if you had not already judged it"."""
    posting_id = _posting_id(client, TRIAGED_REJECTED)
    body = client.get(f"/postings/{posting_id}").text
    assert "filtered out" in body
    assert "already triaged" in body


def test_an_admitted_posting_has_no_filter_banner(client):
    posting_id = _posting_id(client, ADMITTED)
    body = client.get(f"/postings/{posting_id}").text
    assert "filtered out" not in body


def test_the_detail_page_shows_both_criteria_separately(client):
    """Two criteria, two rows, each tri-state. A dash means "did not apply", not
    "passed" — conflating them is how the old single row read as blank forever."""
    posting_id = _posting_id(client, UNJUDGED)
    body = client.get(f"/postings/{posting_id}").text
    assert "Title filter" in body
    assert "Experience filter" in body


# --- the run funnel (FR-015) ------------------------------------------------


@pytest.fixture
def runs_client():
    """A client over two runs: one the filter has touched, one it has not."""
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with factory() as seed:
        seed.add(
            Run(
                status="success",
                collected_count=34,
                deduplicated_count=32,
                counts_by_site={"linkedin": 34},
            )
        )
        seed.add(
            Run(
                status="success",
                collected_count=26,
                deduplicated_count=25,
                filter_passed_count=11,
                filter_rejected_count=14,
                counts_by_site={"linkedin": 26},
            )
        )
        seed.commit()

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_runs_view_shows_the_filter_columns(runs_client):
    body = runs_client.get("/runs").text
    assert "Passed" in body
    assert "Rejected" in body
    assert ">11<" in body.replace(" ", "").replace("\n", "")
    assert ">14<" in body.replace(" ", "").replace("\n", "")


def test_a_run_the_filter_never_touched_reads_as_unknown_not_zero(runs_client):
    """Zero is a claim that the filter admitted nothing. A run that predates the
    stage has made no such claim, and rendering it as 0 manufactures exactly the
    false alarm the per-stage counts exist to raise honestly
    (reports-implementation-plan.md R5, amended by ADR-0016)."""
    body = runs_client.get("/runs").text
    row = [line for line in body.splitlines() if "34" in line or "—" in line]
    assert any("—" in line for line in row)
