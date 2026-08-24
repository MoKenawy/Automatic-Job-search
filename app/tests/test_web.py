"""Triage interface tests.

Run against an in-memory SQLite database rather than the container's PostgreSQL,
so the suite stays runnable without Docker. The queries used by the interface are
plain SQLAlchemy and portable; the JSONB columns degrade to JSON under SQLite.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_SHORTLIST,
    Base,
    Employer,
    Posting,
    Run,
)
from app.web.app import app, get_db


@pytest.fixture
def client():
    # StaticPool keeps a single connection, so the in-memory database persists
    # across the sessions opened by the dependency override. Without it each
    # connection gets its own empty database.
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with factory() as seed:
        run = Run(
            status="success",
            collected_count=53,
            deduplicated_count=36,
            counts_by_site={"indeed": 30, "linkedin": 23},
        )
        employer = Employer(name="PwC", normalised_name="pwc")
        seed.add_all([run, employer])
        seed.flush()

        seed.add_all(
            [
                Posting(
                    fingerprint="a" * 64,
                    employer_id=employer.id,
                    title="ETIC, Data Engineer, Senior Associate",
                    normalised_title="etic data engineer senior associate",
                    location_raw="القاهرة, C, EG",
                    country_code="EG",
                    sources={
                        "indeed": {"url": "https://eg.indeed.com/x"},
                        "linkedin": {"url": "https://linkedin.com/y"},
                    },
                    score=78,
                    rationale="Strong overlap",
                    matched_skills=["SQL"],
                    gaps=["Scala"],
                    published=True,
                    status=STATUS_NEW,
                ),
                Posting(
                    fingerprint="b" * 64,
                    employer_id=employer.id,
                    title="Junior Data Developer",
                    normalised_title="junior data developer",
                    sources={"linkedin": {"url": "https://linkedin.com/z"}},
                    status=STATUS_REJECTED,
                ),
                Posting(
                    fingerprint="c" * 64,
                    employer_id=employer.id,
                    title="Remote Analytics Engineer",
                    normalised_title="remote analytics engineer",
                    location_raw="Egypt",
                    country_code="EG",
                    is_remote=True,
                    sources={"indeed": {"url": "https://indeed.com/w"}},
                    status=STATUS_NEW,
                ),
            ]
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


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Overview" in r.text


def test_index_shows_source_counts(client):
    """Source health is the §7.4 review surface; it must show per-source data."""
    r = client.get("/")
    assert "indeed" in r.text
    assert "linkedin" in r.text


def test_postings_list(client):
    r = client.get("/postings")
    assert r.status_code == 200
    assert "ETIC, Data Engineer, Senior Associate" in r.text
    assert "Junior Data Developer" in r.text


def test_status_filter(client):
    r = client.get("/postings?status=rejected")
    assert "Junior Data Developer" in r.text
    assert "ETIC" not in r.text


def test_search_filter(client):
    r = client.get("/postings?q=junior")
    assert "Junior Data Developer" in r.text
    assert "ETIC" not in r.text


def test_country_filter(client):
    r = client.get("/postings?country=EG")
    assert "ETIC" in r.text
    assert "Remote Analytics Engineer" in r.text
    assert "Junior Data Developer" not in r.text


def test_unknown_country_filter(client):
    """Junior Data Developer has no location_raw, so its country never resolved
    (normalise/country.py returns None rather than guessing)."""
    r = client.get("/postings?country=unknown")
    assert "Junior Data Developer" in r.text
    assert "ETIC" not in r.text
    assert "Remote Analytics Engineer" not in r.text


def test_remote_filter(client):
    r = client.get("/postings?country=remote")
    assert "Remote Analytics Engineer" in r.text
    assert "ETIC" not in r.text
    assert "Junior Data Developer" not in r.text


def test_source_filter(client):
    r = client.get("/postings?source=linkedin")
    assert "ETIC" in r.text
    assert "Junior Data Developer" in r.text
    assert "Remote Analytics Engineer" not in r.text


def test_source_filter_excludes_non_matching(client):
    r = client.get("/postings?source=indeed")
    assert "ETIC" in r.text
    assert "Remote Analytics Engineer" in r.text
    assert "Junior Data Developer" not in r.text


def test_multi_board_posting_shows_both_sources(client):
    """The cross-board merge is the point of §7.3; it must be visible."""
    r = client.get("/postings")
    assert "indeed" in r.text and "linkedin" in r.text


def test_detail_shows_score_and_rationale(client):
    r = client.get("/postings/1")
    assert r.status_code == 200
    assert "78" in r.text
    assert "Strong overlap" in r.text
    assert "SQL" in r.text
    assert "Scala" in r.text


def test_detail_unscored_posting(client):
    """Stage 3 has not run for this posting; the view must not break."""
    r = client.get("/postings/2")
    assert r.status_code == 200
    assert "Not scored yet" in r.text


def test_detail_missing_returns_404(client):
    assert client.get("/postings/999").status_code == 404


def test_status_transition_via_htmx(client):
    r = client.post(
        "/postings/1/status",
        data={"status": STATUS_SHORTLIST},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert STATUS_SHORTLIST in r.text
    assert client.get("/postings?status=shortlist").text.count("ETIC") >= 1


def test_status_transition_without_htmx_redirects(client):
    """Progressive enhancement: the plain form must work if HTMX never loads."""
    r = client.post("/postings/1/status", data={"status": STATUS_SHORTLIST}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/postings/1"


def test_unknown_status_rejected(client):
    r = client.post("/postings/1/status", data={"status": "banana"})
    assert r.status_code == 400


def test_runs_view(client):
    r = client.get("/runs")
    assert r.status_code == 200
    assert "53" in r.text and "36" in r.text


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
