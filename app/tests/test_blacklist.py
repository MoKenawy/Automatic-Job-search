"""US1/US3/US4 — employer blacklist, derived at read time (ADR-0015).

Covers born-`new` postings from a blacklisted employer, the web toggle, the
visibility seam adopted per read path, and the detail-page route back out.
In-memory SQLite, matching the other web/pipeline tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    STATUS_APPLIED,
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_SHORTLIST,
    Base,
    Employer,
    Posting,
    RawPosting,
    Run,
)
from app.pipeline.normalise_stage import run_normalise
from app.services import queries
from app.web.app import app, get_db


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _employer_with_postings(session: Session, name, suppressed=False, statuses=None):
    emp = Employer(name=name, normalised_name=name.lower(), suppressed=suppressed)
    session.add(emp)
    session.flush()
    statuses = statuses or [STATUS_NEW, STATUS_NEW]
    for i, st in enumerate(statuses):
        session.add(
            Posting(
                fingerprint=f"{name}{i}".ljust(64, "0"),
                employer_id=emp.id,
                title=f"Role {i}",
                normalised_title=f"role {i}",
                sources={"linkedin": {"url": "https://x"}},
                status=st,
                published=(st != STATUS_REJECTED),
            )
        )
    session.commit()
    return emp


# --- US2: covers postings not yet collected, with no pass having run -------


def test_new_posting_from_blacklisted_employer_is_born_new_and_invisible(factory):
    """ADR-0015 §Decision 1: covers postings not yet seen, satisfied
    structurally — no sweep runs, and yet the posting is invisible."""
    with factory() as s:
        emp = Employer(name="Spammer", normalised_name="spammer", suppressed=True)
        run = Run(status="running")
        s.add_all([emp, run])
        s.flush()
        s.add(
            RawPosting(
                run_id=run.id,
                site="linkedin",
                payload={
                    "company": "Spammer",
                    "title": "Data Engineer",
                    "location": "Cairo, Egypt",
                    "job_url": "https://x",
                },
            )
        )
        s.commit()

        run_normalise(s, run)
        posting = s.query(Posting).one()
        assert posting.status == STATUS_NEW

        page = queries.list_postings(s)
        assert page.total == 0


# --- web toggle -------------------------------------------------------------


@pytest.fixture
def client(factory):
    with factory() as seed:
        _employer_with_postings(
            seed,
            "Spammer",
            suppressed=False,
            statuses=[STATUS_NEW, STATUS_SHORTLIST, STATUS_APPLIED, STATUS_REJECTED],
        )

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_blacklist_endpoint_sets_flag_and_leaves_statuses_untouched(client, factory):
    with factory() as s:
        before = {p.id: p.status for p in s.query(Posting).filter(Posting.employer_id == 1)}

    r = client.post(
        "/employers/1/blacklist", data={"return_to": "/blacklist"}, follow_redirects=False
    )
    assert r.status_code == 303
    with factory() as s:
        emp = s.get(Employer, 1)
        assert emp.suppressed is True
        after = {p.id: p.status for p in s.query(Posting).filter(Posting.employer_id == 1)}
        assert after == before  # untouched (ADR-0015) ...
        page = queries.list_postings(s)  # ... but invisible
        assert page.total == 0


def test_blacklist_then_lift_restores_visibility_with_prior_status_intact(client, factory):
    """The visible behaviour change (FR-012, SC-003): a lift is a restore, not
    a partial one — every one of the four statuses comes back exactly as it
    was, across the whole employer, not just the ones triaged after ADR-0015."""
    with factory() as s:
        before = {p.id: p.status for p in s.query(Posting).filter(Posting.employer_id == 1)}

    client.post("/employers/1/blacklist", data={}, follow_redirects=False)
    client.post("/employers/1/unblacklist", data={}, follow_redirects=False)
    with factory() as s:
        emp = s.get(Employer, 1)
        assert emp.suppressed is False
        after = {p.id: p.status for p in s.query(Posting).filter(Posting.employer_id == 1)}
        assert after == before
        page = queries.list_postings(s)
        assert page.total == len(before)


def test_blacklist_page_lists_suppressed_employers(client):
    client.post("/employers/1/blacklist", data={}, follow_redirects=False)
    html = client.get("/blacklist").text
    assert "Spammer" in html


def test_blacklist_page_renders_the_fr013_standing_note(client):
    html = client.get("/blacklist").text
    assert "FR-013" in html


# --- US1: the seam, adopted per read path (ADR-0015) ------------------------
#
# Every case here is two-sided: a suppressed employer's posting is absent
# *and* a normal employer's posting is present. An absence-only test would
# also pass against a `not_suppressed()` that hid everything.


def test_list_postings_hides_suppressed_employers_new_posting(factory):
    with factory() as s:
        _employer_with_postings(s, "Spammer", suppressed=True, statuses=[STATUS_NEW])
        _employer_with_postings(s, "Good", suppressed=False, statuses=[STATUS_NEW])

        page = queries.list_postings(s)
        titles = {p.title for p, _ in page.rows}
        assert "Role 0" in titles
        assert page.total == 1
        assert len(page.rows) == 1


def test_list_postings_published_only_hides_suppressed_employer(factory):
    with factory() as s:
        emp_bad = _employer_with_postings(
            s, "Spammer", suppressed=True, statuses=[STATUS_SHORTLIST]
        )
        emp_good = _employer_with_postings(s, "Good", suppressed=False, statuses=[STATUS_SHORTLIST])
        for emp in (emp_bad, emp_good):
            posting = s.query(Posting).filter(Posting.employer_id == emp.id).one()
            posting.published = True
        s.commit()

        page = queries.list_postings(s, published_only=True)
        employer_ids = {p.employer_id for p, _ in page.rows}
        assert employer_ids == {emp_good.id}


def test_totals_exclude_suppressed_employers_postings(factory):
    with factory() as s:
        emp_bad = _employer_with_postings(
            s, "Spammer", suppressed=True, statuses=[STATUS_NEW, STATUS_SHORTLIST]
        )
        for p in s.query(Posting).filter(Posting.employer_id == emp_bad.id):
            p.published = True
            p.score = 5
        emp_good = _employer_with_postings(s, "Good", suppressed=False, statuses=[STATUS_NEW])
        for p in s.query(Posting).filter(Posting.employer_id == emp_good.id):
            p.published = True
            p.score = 5
        s.commit()

        t = queries.totals(s)
        assert t.postings == 1
        assert t.published == 1
        assert t.scored == 1
        assert t.by_status == {STATUS_NEW: 1}


def test_totals_employers_excludes_blacklisted(factory):
    with factory() as s:
        _employer_with_postings(s, "Spammer", suppressed=True)
        _employer_with_postings(s, "Good", suppressed=False)

        t = queries.totals(s)
        assert t.employers == 1


def test_facets_countries_excludes_suppressed_employers_only_country(factory):
    with factory() as s:
        emp_bad = _employer_with_postings(s, "Spammer", suppressed=True, statuses=[STATUS_NEW])
        s.query(Posting).filter(Posting.employer_id == emp_bad.id).update({"country_code": "EG"})
        emp_good = _employer_with_postings(s, "Good", suppressed=False, statuses=[STATUS_NEW])
        s.query(Posting).filter(Posting.employer_id == emp_good.id).update({"country_code": "US"})
        s.commit()

        f = queries.facets(s)
        assert f.countries == ["US"]
        assert f.unknown_country is False


def test_postings_of_suppressed_employer_are_retained_not_deleted(factory):
    """Invisibility is not retention (FR-014, D9)."""
    with factory() as s:
        _employer_with_postings(s, "Spammer", suppressed=True, statuses=[STATUS_NEW])

        page = queries.list_postings(s)
        assert page.total == 0  # invisible...
        assert s.query(Posting).count() == 1  # ...but still present on disk


# --- US4: the way back out stays reachable (ADR-0015, FR-015) ---------------


def test_detail_route_loads_for_suppressed_employers_posting(factory):
    with factory() as s:
        emp = _employer_with_postings(s, "Spammer", suppressed=True, statuses=[STATUS_NEW])
        posting_id = s.query(Posting).filter(Posting.employer_id == emp.id).first().id

    def override():
        sess = factory()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = override
    try:
        r = TestClient(app).get(f"/postings/{posting_id}")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert "employer blacklisted" in r.text
    assert "Remove from blacklist" in r.text
