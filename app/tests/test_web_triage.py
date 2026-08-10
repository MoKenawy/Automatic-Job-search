"""US1 + US2 — quick and bulk triage from the list page.

Reuses the in-memory SQLite pattern from test_web.py.
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
)
from app.web.app import app, get_db


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
        for i in range(4):
            seed.add(
                Posting(
                    fingerprint=chr(97 + i) * 64,
                    employer_id=employer.id,
                    title=f"Data Engineer {i}",
                    normalised_title=f"data engineer {i}",
                    sources={"linkedin": {"url": "https://x"}},
                    score=90 - i,
                    status=STATUS_NEW,
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


# --- US1 -------------------------------------------------------------------


def test_list_renders_inline_status_control_per_row(client):
    """Each row must carry the inline control, not a read-only pill (FR-001)."""
    html = client.get("/postings").text
    # The row control posts with variant=row for every posting
    assert html.count('name="variant" value="row"') >= 4


def test_quick_status_change_from_list_returns_row_fragment(client):
    r = client.post(
        "/postings/1/status",
        data={"status": STATUS_SHORTLIST, "variant": "row"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert 'id="status-1"' in r.text
    assert STATUS_SHORTLIST in r.text
    # It changed in the database
    assert client.get("/postings?status=shortlist").text.count("Data Engineer 0") == 1


def test_quick_status_change_without_htmx_redirects_to_list(client):
    """Progressive enhancement: plain form post redirects to /postings (FR-002)."""
    r = client.post(
        "/postings/1/status",
        data={"status": STATUS_SHORTLIST, "variant": "row"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/postings"


def test_detail_variant_still_redirects_to_detail(client):
    """The detail control must keep its own redirect target (regression guard)."""
    r = client.post(
        "/postings/1/status",
        data={"status": STATUS_SHORTLIST, "variant": "detail"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/postings/1"


# --- US2 -------------------------------------------------------------------


def test_bulk_status_change_sets_all_selected(client):
    r = client.post(
        "/postings/status",
        data={"ids": [1, 2, 3], "status": STATUS_REJECTED},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    # All three now rejected, dropped from the default (implicit) view is not
    # asserted here; assert via the rejected filter instead.
    rejected = client.get("/postings?status=rejected").text
    for i in (0, 1, 2):
        assert f"Data Engineer {i}" in rejected
    # The fourth was untouched
    assert "Data Engineer 3" not in rejected


def test_bulk_rejects_unknown_status(client):
    r = client.post("/postings/status", data={"ids": [1], "status": "banana"})
    assert r.status_code == 400


def test_bulk_rejects_empty_selection(client):
    r = client.post("/postings/status", data={"ids": [], "status": STATUS_REJECTED})
    assert r.status_code == 400


def test_list_has_select_all_and_bulk_controls(client):
    html = client.get("/postings").text
    assert 'id="selall"' in html
    assert 'id="bulkapply"' in html
    assert 'name="ids"' in html


# --- Pagination --------------------------------------------------------------


def test_pagination_splits_results_across_pages(client, monkeypatch):
    from app.services import queries

    monkeypatch.setattr(queries, "PAGE_SIZE", 2)
    r = client.get("/postings")
    assert "Page 1 of 2" in r.text
    assert "Data Engineer 0" in r.text
    assert "Data Engineer 1" in r.text
    assert "Data Engineer 2" not in r.text

    r2 = client.get("/postings?page=2")
    assert "Data Engineer 2" in r2.text
    assert "Data Engineer 3" in r2.text
    assert "Data Engineer 0" not in r2.text


def test_pagination_clamps_out_of_range_page(client, monkeypatch):
    from app.services import queries

    monkeypatch.setattr(queries, "PAGE_SIZE", 2)
    r = client.get("/postings?page=99")
    assert "Page 2 of 2" in r.text


def test_bulk_status_change_preserves_filter_and_page(client, monkeypatch):
    from app.services import queries

    monkeypatch.setattr(queries, "PAGE_SIZE", 2)
    r = client.post(
        "/postings/status",
        data={
            "ids": [3],
            "status": STATUS_SHORTLIST,
            "page": 2,
        },
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Page 2 of 2" in r.text


# --- Rejected default ordering ------------------------------------------------


def test_rejected_filter_orders_by_status_changed_at_desc(client):
    """Rejected is a log, not a ranking: most recently rejected sorts first."""
    client.post("/postings/1/status", data={"status": STATUS_REJECTED})
    client.post("/postings/3/status", data={"status": STATUS_REJECTED})
    client.post("/postings/2/status", data={"status": STATUS_REJECTED})

    html = client.get("/postings?status=rejected").text
    pos0 = html.index("Data Engineer 1")  # rejected last -> first
    pos1 = html.index("Data Engineer 2")
    pos2 = html.index("Data Engineer 0")  # rejected first -> last
    assert pos0 < pos1 < pos2
