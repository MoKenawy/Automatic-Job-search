"""US3 — company blacklist with automatic rejection.

Covers the suppression pass, born-rejected new postings, and the web toggle.
In-memory SQLite, matching the other web/pipeline tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
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
from app.pipeline.suppress_stage import run_suppress
from app.services.blacklist import reject_employer_postings
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


# --- suppression pass -------------------------------------------------------


def test_suppress_rejects_all_postings_of_blacklisted_employer(factory):
    with factory() as s:
        emp = _employer_with_postings(s, "Spammer", suppressed=True)
        n = run_suppress(s)
        assert n == 2
        postings = s.query(Posting).filter(Posting.employer_id == emp.id).all()
        assert all(p.status == STATUS_REJECTED for p in postings)
        assert all(p.published is False for p in postings)


def test_suppress_is_idempotent(factory):
    with factory() as s:
        _employer_with_postings(s, "Spammer", suppressed=True)
        assert run_suppress(s) == 2
        assert run_suppress(s) == 0  # nothing left to change


def test_suppress_leaves_other_employers_untouched(factory):
    with factory() as s:
        _employer_with_postings(s, "Spammer", suppressed=True)
        good = _employer_with_postings(s, "Good", suppressed=False)
        run_suppress(s)
        good_postings = s.query(Posting).filter(Posting.employer_id == good.id).all()
        assert all(p.status == STATUS_NEW for p in good_postings)


def test_postings_are_preserved_not_deleted(factory):
    """'Preserved' means retained with status Rejected (D9)."""
    with factory() as s:
        _employer_with_postings(s, "Spammer", suppressed=True)
        run_suppress(s)
        assert s.query(Posting).count() == 2  # still present


# --- born rejected via normalise -------------------------------------------


def test_new_posting_from_blacklisted_employer_is_born_rejected(factory):
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
        assert posting.status == STATUS_REJECTED
        assert posting.published is False


# --- web toggle -------------------------------------------------------------


@pytest.fixture
def client(factory):
    with factory() as seed:
        _employer_with_postings(seed, "Spammer", suppressed=False,
                                statuses=[STATUS_NEW, STATUS_SHORTLIST])

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_blacklist_endpoint_suppresses_and_rejects(client, factory):
    r = client.post("/employers/1/blacklist", data={"return_to": "/blacklist"},
                    follow_redirects=False)
    assert r.status_code == 303
    with factory() as s:
        emp = s.get(Employer, 1)
        assert emp.suppressed is True
        postings = s.query(Posting).filter(Posting.employer_id == 1).all()
        assert all(p.status == STATUS_REJECTED for p in postings)


def test_unblacklist_stops_future_but_does_not_reinstate(client, factory):
    client.post("/employers/1/blacklist", data={}, follow_redirects=False)
    client.post("/employers/1/unblacklist", data={}, follow_redirects=False)
    with factory() as s:
        emp = s.get(Employer, 1)
        assert emp.suppressed is False
        # Previously rejected postings stay rejected (FR-011)
        postings = s.query(Posting).filter(Posting.employer_id == 1).all()
        assert all(p.status == STATUS_REJECTED for p in postings)


def test_blacklist_page_lists_suppressed_employers(client):
    client.post("/employers/1/blacklist", data={}, follow_redirects=False)
    html = client.get("/blacklist").text
    assert "Spammer" in html


def test_suppress_employer_targeted(factory):
    with factory() as s:
        emp = _employer_with_postings(s, "Spammer", suppressed=True)
        assert reject_employer_postings(s, emp.id) == 2
