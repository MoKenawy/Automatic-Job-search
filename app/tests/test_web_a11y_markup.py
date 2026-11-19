"""Structural accessibility checks over every GET page (spec 004 T023; constitution VI).

Only `html.parser`: no browser. Pages that are not renovated yet are listed in PENDING and
xfail (non-strict); each page phase removes its own entry, and T063 deletes the set.
"""

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Employer, Posting, Run
from app.web.app import app, get_db

PAGES = [
    "/",
    "/postings",
    "/postings/1",
    "/reports",
    "/reports/employers",
    "/reports/sources",
    "/reports/profiles",
    "/blacklist",
    "/profiles",
    "/settings",
    "/runs",
]

# Pages whose own phase has not landed yet (tasks Phases 4-11).
PENDING = set(PAGES)


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
        employer = Employer(name="PwC", normalised_name="pwc")
        seed.add_all([employer, Run(status="success", counts_by_site={"indeed": 3})])
        seed.flush()
        seed.add(
            Posting(
                fingerprint="a" * 64,
                employer_id=employer.id,
                title="Data Engineer",
                normalised_title="data engineer",
                sources={"indeed": {"url": "https://eg.indeed.com/x"}},
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


class _Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.problems: list[str] = []
        self.current = 0
        self.skip_link = False
        self.live = 0
        self.h1 = 0
        self.title = ""
        self._in_title = False
        self._in_thead = False
        self.label_for: set[str] = set()
        self.controls: list[dict] = []
        self.wrap_issues = 0
        self._svg_stack: list[bool] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("aria-current") == "page":
            self.current += 1
        if tag == "a" and a.get("href") == "#main" and "skip-link" in (a.get("class") or ""):
            self.skip_link = True
        if "aria-live" in a:
            self.live += 1
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self._in_title = True
        if tag == "thead":
            self._in_thead = True
        if tag == "th" and self._in_thead and "scope" not in a:
            self.problems.append("thead th without scope")
        if tag == "label" and a.get("for"):
            self.label_for.add(a["for"])
        if tag in {"input", "select", "textarea"} and a.get("type") not in {"hidden", "submit"}:
            self.controls.append(a)
        if (
            tag == "svg"
            and a.get("aria-hidden") != "true"
            and not (a.get("aria-label") or a.get("aria-labelledby") or a.get("role") == "img")
        ):
            self.problems.append("svg without aria-hidden or name")
        if "table-wrap" in (a.get("class") or "").split() and not (
            a.get("tabindex") == "0" and a.get("aria-label")
        ):
            self.problems.append("table-wrap without tabindex=0 and aria-label")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "thead":
            self._in_thead = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


@pytest.mark.parametrize("path", PAGES)
def test_page_markup(client, path):
    if path in PENDING:
        pytest.xfail("page not renovated yet")  # replaced by real checks as phases land
    response = client.get(path)
    assert response.status_code == 200
    audit = _Audit()
    audit.feed(response.text)
    assert audit.current == 1, "exactly one aria-current=page"
    assert audit.skip_link, "skip link to #main"
    assert audit.live == 1, "one aria-live region"
    assert audit.h1 == 1, "exactly one h1"
    assert audit.title.strip() and audit.title.strip() != "Job discovery", "page-specific title"
    for c in audit.controls:
        assert c.get("aria-label") or c.get("id") in audit.label_for, f"unlabelled control {c}"
    assert not audit.problems, audit.problems


@pytest.mark.parametrize("path", PAGES)
def test_shell_markup(client, path):
    """Checks every page already meets through base.html, renovated or not."""
    response = client.get(path)
    audit = _Audit()
    audit.feed(response.text)
    assert audit.skip_link
    assert audit.live == 1
    assert audit.title.strip() != "Job discovery"
    assert audit.current == 1
