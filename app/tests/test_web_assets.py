"""Static assets and the local-first guards (spec 004, SC-005, SC-007, SC-009; ADR-0021).

Vendored files are served by the app itself, the pages never name a third-party origin
for a script, stylesheet or font, templates carry no literal colours, and the first-load
payload stays under the budget.
"""

import base64
import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.web.app import app, get_db

WEB = Path(__file__).resolve().parents[1] / "src" / "app" / "web"
STATIC = WEB / "static"
TEMPLATES = WEB / "templates"

HTMX = "/static/vendor/htmx-2.0.3.min.js"
# research R4; also the `integrity=` value in base.html.
HTMX_SHA384 = "0895/pl2MU10Hqc6jd4RvrthNlDiE9U1tWmX7WRESftEDRosgxNsQG/Ze9YMRzHq"
FIRST_LOAD_BUDGET = 150 * 1024  # SC-009

PAGES = ["/", "/postings", "/reports", "/blacklist", "/profiles", "/settings", "/runs"]

# Templates that still carry colour literals, emptied as each page is renovated
# (tasks T028, Phases 4-11; the set is deleted in T063).
PENDING_LITERALS: set[str] = set()


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

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


class _ExternalRefs(HTMLParser):
    """Collects script/stylesheet/font references that point off-origin."""

    def __init__(self):
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        url = a.get("src") if tag == "script" else None
        if tag == "link" and (a.get("rel") or "").lower() in {
            "stylesheet",
            "preload",
            "icon",
            "modulepreload",
        }:
            url = a.get("href")
        if url and re.match(r"(https?:)?//", url):
            self.found.append(url)


def test_htmx_is_served_and_matches_pin(client):
    response = client.get(HTMX)
    assert response.status_code == 200
    digest = base64.b64encode(hashlib.sha384(response.content).digest()).decode()
    assert digest == HTMX_SHA384


@pytest.mark.parametrize(
    "path",
    [
        "/static/icons.svg",
        "/static/fonts/inter-latin-wght-normal.woff2",
        "/static/fonts/inter-latin-ext-wght-normal.woff2",
    ],
)
def test_vendored_assets_are_served(client, path):
    assert client.get(path).status_code == 200


COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(")


def test_templates_have_no_colour_literals():
    """SC-007, FR-005: colours come from the token stylesheet only."""
    offenders = {}
    for path in TEMPLATES.rglob("*.html"):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel in PENDING_LITERALS:
            continue
        hits = COLOUR_LITERAL.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders[rel] = hits[:3]
    assert not offenders


@pytest.mark.parametrize("path", PAGES)
def test_pages_load_nothing_from_other_origins(client, path):
    """SC-005, constitution II."""
    parser = _ExternalRefs()
    parser.feed(client.get(path).text)
    assert parser.found == []


def test_first_load_assets_fit_the_budget():
    """SC-009: stylesheet, latin font, sprite and htmx together are <= 150 KB."""
    files = [
        STATIC / "css" / "app.css",
        STATIC / "fonts" / "inter-latin-wght-normal.woff2",
        STATIC / "icons.svg",
        STATIC / "vendor" / "htmx-2.0.3.min.js",
    ]
    total = sum(f.stat().st_size for f in files if f.exists())
    assert total <= FIRST_LOAD_BUDGET
