"""Report pages (ADR-0008).

Route-level rendering only — the aggregation itself is covered by
`test_reports.py`. Mirrors `test_web.py`'s in-memory SQLite + StaticPool setup;
the fixture is deliberately local rather than shared via `conftest.py`, since
lifting `test_web.py`'s fixture would mean editing that file for no benefit here.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Employer,
    Posting,
    RawPosting,
    RawPostingNormalization,
    Run,
    SearchProfile,
)
from app.web.app import app, get_db

SAME_RUN = "2026-07-20T06:00:00+00:00"


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
        seed.add(
            Run(
                status="success",
                collected_count=12,
                deduplicated_count=9,
                counts_by_site={"indeed": 7, "linkedin": 5},
            )
        )
        acme = Employer(name="Acme", normalised_name="acme")
        blacklisted = Employer(
            name="Blacklisted Corp", normalised_name="blacklisted corp", suppressed=True
        )
        profile = SearchProfile(name="backend", term="backend engineer")
        seed.add_all([acme, blacklisted, profile])
        seed.flush()

        data_eng = Posting(
            fingerprint="a" * 64,
            employer_id=acme.id,
            title="Data Engineer",
            normalised_title="data engineer",
            sources={
                "indeed": {"url": "https://i/1", "first_seen": SAME_RUN},
                "linkedin": {"url": "https://l/1", "first_seen": SAME_RUN},
            },
        )
        seed.add_all(
            [
                data_eng,
                Posting(
                    fingerprint="b" * 64,
                    employer_id=blacklisted.id,
                    title="Junior Dev",
                    normalised_title="junior dev",
                    sources={"linkedin": {"url": "https://l/2", "first_seen": SAME_RUN}},
                ),
            ]
        )
        seed.flush()

        profile_run = Run(profile_id=profile.id, status="success")
        seed.add(profile_run)
        seed.flush()

        raw = RawPosting(run_id=profile_run.id, site="indeed", payload={})
        seed.add(raw)
        seed.flush()

        seed.add(RawPostingNormalization(raw_posting_id=raw.id, posting_id=data_eng.id))
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


def test_reports_index_lists_the_available_reports(client):
    r = client.get("/reports")
    assert r.status_code == 200
    assert "Employer hiring activity" in r.text
    assert "Source coverage and overlap" in r.text
    assert "Triage status per search profile" in r.text


def test_reports_reachable_from_the_nav(client):
    assert 'href="/reports"' in client.get("/").text


def test_employer_report_renders(client):
    r = client.get("/reports/employers")
    assert r.status_code == 200
    assert "Acme" in r.text


def test_employer_report_hides_blacklisted_employers_by_default(client):
    assert "Blacklisted Corp" not in client.get("/reports/employers").text


def test_employer_report_shows_blacklisted_employers_on_request(client):
    assert "Blacklisted Corp" in client.get("/reports/employers?show_suppressed=true").text


def test_source_report_renders(client):
    r = client.get("/reports/sources")
    assert r.status_code == 200
    assert "indeed" in r.text and "linkedin" in r.text


def test_source_report_shows_the_recently_queried_boards(client):
    """The coverage figures are only comparable across boards that were asked;
    the run's per-board counts are the evidence for that caveat."""
    assert "Boards queried recently" in client.get("/reports/sources").text


def test_profile_report_renders(client):
    r = client.get("/reports/profiles")
    assert r.status_code == 200
    assert "backend" in r.text


def test_profile_report_shows_status_counts_for_its_postings(client):
    assert "new" in client.get("/reports/profiles").text


def test_profile_report_shows_a_percentage_alongside_each_status_count(client):
    """backend's one posting is 'new', so that status is 100% of its total."""
    assert "100%" in client.get("/reports/profiles").text


# --- The caveats are an admission condition, not decoration (ADR-0008 §1) -----


@pytest.mark.parametrize("path", ["/reports/employers", "/reports/sources", "/reports/profiles"])
def test_every_report_states_that_it_is_not_a_market_measurement(client, path):
    assert "measurement of the job market" in client.get(path).text


def test_employer_report_states_its_own_bias(client):
    assert "not of everything these employers are hiring for" in (
        client.get("/reports/employers").text
    )


def test_source_report_states_that_coverage_is_confounded_by_configuration(client):
    assert "the board list is set per profile" in client.get("/reports/sources").text


def test_profile_report_states_postings_can_be_double_counted(client):
    assert "counted under each of them" in client.get("/reports/profiles").text
